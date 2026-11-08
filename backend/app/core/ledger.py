"""Protection tasks, evidence tiers, disputes and escalation (finalsystem.md §11, B.2, B.5, G20, G22).

A task is not proof of protection. The ledger records who must do what, by
when, and how strong the evidence is that it happened. Workers can dispute a
completion, and nothing is "verified" without the required evidence tier and
with an open dispute. Every change is an append-only event.
"""
from __future__ import annotations

import itertools
from datetime import datetime, timedelta
from typing import Any

from . import policy

TIERS = ["E0", "E1", "E2", "E3", "E4"]
TIER_TEXT = {"E0": "Requested", "E1": "Acknowledged", "E2": "Attested", "E3": "Observed", "E4": "Independently checked"}

ALLOWED: dict[str, set[str]] = {
    "assigned": {"accepted", "escalated", "cancelled"},
    "accepted": {"in_progress", "escalated"},
    "in_progress": {"reported_complete", "escalated"},
    "reported_complete": {"verified", "disputed"},
    "disputed": {"in_progress", "escalated"},
    "escalated": {"accepted"},
    "verified": {"reopened"},
    "reopened": {"assigned"},
    "cancelled": set(),
}
MANDATORY = {"WATER_RESTORE", "SHADE_EXTEND", "STOP_AFFECTED_WORK", "CHECK_WORKER", "ENHANCED_SCHEDULE",
             "MOVE_TO_SHADED_TASK", "NEW_WORKER_REVIEW", "TRAINING_DUE", "AC_FIX", "COOLING_FIX", "BREAK_ACCESS"}
EVIDENCE_KINDS = {
    "acknowledgement": "E1",
    "supervisor_attestation": "E2",
    "worker_confirmation": "E2",
    "review_record": "E2",
    "training_record": "E2",
    "photo": "E3",
    "water_point_check": "E3",
    "capacity_record": "E3",
    "instrument_record": "E3",
    "room_temperature_record": "E3",
    "independent_spot_check": "E4",
}
EVIDENCE_SCOPE = {  # which evidence kinds can support which action class (scope match, B.5)
    "WATER_RESTORE": {"supervisor_attestation", "photo", "water_point_check", "independent_spot_check",
                      "worker_confirmation"},
    "SHADE_EXTEND": {"supervisor_attestation", "photo", "capacity_record", "independent_spot_check",
                     "worker_confirmation"},
    "COOLING_FIX": {"supervisor_attestation", "photo", "instrument_record", "independent_spot_check"},
    "AC_FIX": {"supervisor_attestation", "photo", "room_temperature_record", "independent_spot_check"},
    "STOP_AFFECTED_WORK": {"supervisor_attestation", "photo", "independent_spot_check", "instrument_record"},
    "ENHANCED_SCHEDULE": {"supervisor_attestation", "worker_confirmation", "independent_spot_check"},
    "CHECK_WORKER": {"supervisor_attestation", "worker_confirmation"},
    "NEW_WORKER_REVIEW": {"review_record", "supervisor_attestation"},
    "TRAINING_DUE": {"training_record"},
    "MOVE_TO_SHADED_TASK": {"supervisor_attestation", "worker_confirmation", "independent_spot_check"},
    "BREAK_ACCESS": {"supervisor_attestation", "worker_confirmation", "independent_spot_check"},
    "HSE_REVIEW": {"review_record"},
    "CLINIC_TRANSPORT": {"supervisor_attestation", "worker_confirmation"},
    "CHECK_WORKER_EMERGENCY": {"supervisor_attestation"},
}
OWNER = {"WATER_RESTORE": "supervisor", "SHADE_EXTEND": "supervisor", "STOP_AFFECTED_WORK": "supervisor",
         "CHECK_WORKER": "supervisor", "ENHANCED_SCHEDULE": "supervisor", "NEW_WORKER_REVIEW": "supervisor",
         "AC_FIX": "hse", "TRAINING_DUE": "hse", "MOVE_TO_SHADED_TASK": "supervisor", "COOLING_FIX": "supervisor",
         "BREAK_ACCESS": "supervisor", "HSE_REVIEW": "hse", "CLINIC_TRANSPORT": "hse"}
DEFAULT_DEADLINE_MIN = {"COOLING_FIX": 30, "BREAK_ACCESS": 15, "MOVE_TO_SHADED_TASK": 0, "HSE_REVIEW": 2880,
                        "CLINIC_TRANSPORT": 240}
DEFAULT_TIER = {"COOLING_FIX": "E3", "BREAK_ACCESS": "E2", "MOVE_TO_SHADED_TASK": "E2", "HSE_REVIEW": "E2"}
INDEPENDENT_ROLES = {"hse", "auditor"}   # outside the supervisor's line (§11.3)
MAX_EVIDENCE_AGE_MIN = 30                # older photos are not current evidence (T26)


class LedgerError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code = code
        self.status = status


class Ledger:
    def __init__(self) -> None:
        self.tasks: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self.notifications: list[dict[str, Any]] = []
        self._ids = itertools.count(1)
        self._ev = itertools.count(1)
        self._nid = itertools.count(1)
        self.idempotency: dict[str, Any] = {}
        self.offline_roles: set[str] = set()     # roles whose devices cannot be reached right now (T56)

    # ------------------------------------------------------------------ create
    def create(self, *, action_code: str, zone: str | None, now: str, rationale: str, source: str,
               plan_id: str = "plan_live", crew: str | None = None, affected: list[str] | None = None,
               reporter_hidden: bool = False, extra: dict[str, Any] | None = None,
               rationale_ar: str | None = None) -> dict[str, Any]:
        pack = policy.heat_pack()
        minutes = pack["task_deadlines_minutes"].get(action_code, DEFAULT_DEADLINE_MIN.get(action_code, 30))
        tier = pack["evidence_required"].get(action_code, DEFAULT_TIER.get(action_code, "E2"))
        tid = f"task_{next(self._ids):03d}"
        start_by = (datetime.fromisoformat(now) + timedelta(minutes=minutes)).isoformat()
        task = {
            "id": tid, "tenant_id": "tenant_demo", "site_id": "site_demo", "plan_id": plan_id,
            "policy_version": "AE-AD-HEAT@0.1.1-demo", "action_code": action_code, "zone_id": zone,
            "crew": crew, "affected_workers": affected or [], "owner_role": OWNER.get(action_code, "supervisor"),
            "escalation_role": "hse", "state": "assigned", "created_at": now, "start_by": start_by,
            "deadline_min": minutes, "required_minutes": None, "performed_start": None, "performed_end": None,
            "verified_at": None, "required_tier": tier, "achieved_tier": "E0", "open_disputes": 0,
            "evidence": [], "disputes": [], "history": [], "worker_dispute_allowed": True,
            "mandatory": action_code in MANDATORY, "rationale": rationale, "rationale_ar": rationale_ar or rationale,
            "source": source,
            "reporter_hidden": reporter_hidden, "escalated": False, "schema_version": "1", "version": 1,
            **(extra or {}),
        }
        self.tasks[tid] = task
        self._event(task, "created", actor="system", role="system", at=now, detail={"rationale": rationale})
        self.notify(to_role=task["owner_role"], at=now, template="msg.task_to_supervisor",
                    slots={"zone": zone or "-", "action": action_code, "minutes": minutes}, task=tid)
        return task

    # ------------------------------------------------------------- transitions
    def transition(self, task_id: str, new_state: str, *, actor: str, role: str, at: str,
                   evidence: dict[str, Any] | None = None, reason: str | None = None,
                   expected_version: int | None = None) -> dict[str, Any]:
        task = self.get(task_id)
        if expected_version is not None and task["version"] != expected_version:
            raise LedgerError("version_conflict", "The task changed since you opened it. Reload and try again.")
        if new_state not in ALLOWED.get(task["state"], set()):
            raise LedgerError("invalid_transition", f"A task cannot move from {task['state']} to {new_state}.")
        self._authorise(task, new_state, role)
        if new_state == "cancelled":
            if task["mandatory"]:
                raise LedgerError("mandatory_protection",
                                  "A mandatory protection cannot be cancelled. Supersede it with a recorded "
                                  "replacement instead.", 422)
            if not reason:
                raise LedgerError("reason_required", "Cancelling needs an authorised reason.", 422)
        if evidence:
            self._add_evidence(task, evidence, actor=actor, role=role, at=at)
        if new_state == "verified":
            if task["open_disputes"] > 0:
                raise LedgerError("open_dispute", "A disputed task cannot be verified until the dispute is resolved.",
                                  422)
            if TIERS.index(task["achieved_tier"]) < TIERS.index(task["required_tier"]):
                raise LedgerError("evidence_tier",
                                  f"Verification needs evidence tier {task['required_tier']} "
                                  f"({TIER_TEXT[task['required_tier']]}); this task has {task['achieved_tier']}.",
                                  422)
            if task.get("requires_independent") and role not in INDEPENDENT_ROLES:
                raise LedgerError("independence", "This verification must be done outside the supervisor's line.",
                                  422)
            task["verified_at"] = at
        if new_state == "in_progress" and not task["performed_start"]:
            task["performed_start"] = at
        if new_state == "reported_complete":
            task["performed_end"] = at
        if new_state == "accepted" and task["state"] in ("assigned", "escalated") and \
                TIERS.index(task["achieved_tier"]) < 1:
            task["achieved_tier"] = "E1"
        if new_state == "escalated":
            prev_owner = task["owner_role"]
            task["escalated"] = True
            task["owner_role"] = task["escalation_role"]
            n = self.notify(to_role=task["escalation_role"], at=at, template="msg.escalation",
                            slots={"zone": task["zone_id"] or "-", "action": task["action_code"]}, task=task_id)
            if n["state"] == "queued":
                # The escalation owner cannot be reached: the remote notice stays pending (never shown as sent)
                # and the previous owner gets a local reminder to keep the protection in place (T56).
                self.notify(to_role=prev_owner, at=at, template="msg.escalation_pending",
                            slots={"zone": task["zone_id"] or "-", "action": task["action_code"]}, task=task_id)
        if new_state == "reopened":
            task["verified_at"] = None
            task["achieved_tier"] = "E0"
        prev = task["state"]
        task["state"] = new_state
        task["version"] += 1
        self._event(task, new_state, actor=actor, role=role, at=at,
                    detail={"from": prev, "reason": reason, "evidence": evidence})
        return task

    def dispute(self, task_id: str, *, actor: str, role: str, at: str, text: str) -> dict[str, Any]:
        task = self.get(task_id)
        if task["state"] not in ("reported_complete", "verified", "in_progress", "accepted", "escalated"):
            raise LedgerError("dispute_state", "Only an active or completed task can be disputed.")
        dispute = {"id": f"dsp_{task_id}_{len(task['disputes']) + 1}", "raised_by_role": role,
                   "raised_at": at, "text": text, "open": True}
        # The worker's identity is kept for the record but never shown to the supervisor (§11.8).
        dispute["raised_by_ref"] = actor
        task["disputes"].append(dispute)
        task["open_disputes"] += 1
        self._event(task, "disputed_raised", actor=actor, role=role, at=at, detail={"dispute": dispute["id"]})
        if task["state"] == "reported_complete":
            self.transition(task_id, "disputed", actor=actor, role="system", at=at, reason="worker dispute")
            self.transition(task_id, "escalated", actor="system", role="system", at=at,
                            reason="disputed completion goes to the HSE owner")
        elif task["state"] == "verified":
            self.transition(task_id, "reopened", actor="system", role="system", at=at, reason="protection disputed")
            self.transition(task_id, "assigned", actor="system", role="system", at=at, reason="reopened")
        elif task["state"] in ("in_progress", "accepted"):
            self.transition(task_id, "escalated", actor="system", role="system", at=at, reason="worker dispute")
        return task

    def resolve_dispute(self, task_id: str, *, actor: str, role: str, at: str, reason: str) -> dict[str, Any]:
        """Audited resolution when the worker who disputed is not there to confirm (§11.8).

        Only someone outside the supervisor's line may resolve it, only with their own check (observed or
        independently checked) made after the worker raised the dispute, and only with a written finding. The
        worker is told what was checked and keeps the right to challenge again: a new dispute reopens the task.
        """
        task = self.get(task_id)
        open_ = [d for d in task["disputes"] if d["open"]]
        if not open_:
            raise LedgerError("no_open_dispute", "There is no open dispute on this task.", 422)
        if role not in INDEPENDENT_ROLES:
            raise LedgerError("independence", "Only someone outside the supervisor's line can resolve a worker's "
                                              "dispute.", 403)
        if not reason or len(reason.strip()) < 8:
            raise LedgerError("reason_required", "Write what you checked and what you found.", 422)
        latest = max(datetime.fromisoformat(d["raised_at"]) for d in open_)
        fresh = [e for e in task["evidence"] if e["actor_role"] in INDEPENDENT_ROLES and e["tier"] in ("E3", "E4")
                 and datetime.fromisoformat(e["observed_at"]) >= latest]
        if not fresh:
            raise LedgerError("evidence_after_dispute",
                              "A dispute can only be resolved with your own check (observed or independently "
                              "checked), made after the worker raised it.", 422)
        ev = fresh[-1]
        for d in open_:
            d.update(open=False, resolved_at=at, resolved_by="independent_check", resolver_role=role,
                     resolution={"reason": reason.strip(), "evidence": ev.get("id"), "evidence_kind": ev["kind"],
                                 "checked_at": ev["observed_at"]},
                     worker_can_challenge_again=True)
            self.notify(to_role="worker", to_actor=d.get("raised_by_ref"), at=at, template="msg.dispute_resolved",
                        slots={"action": task["action_code"], "time": ev["observed_at"][11:16],
                               "zone": task["zone_id"] or "-"}, task=task_id)
        task["open_disputes"] = 0
        task["version"] += 1
        self._event(task, "dispute_resolved", actor=actor, role=role, at=at,
                    detail={"disputes": [d["id"] for d in open_], "evidence": ev.get("id"), "reason": reason.strip()})
        return task

    def close_rehearsal(self, task_id: str, *, at: str, reason: str) -> dict[str, Any]:
        """Close a task that a drill created, so the next drill starts from a clean site. Only drill tasks can be
        closed this way (a real mandatory protection is never cancelled); its events and evidence are kept."""
        task = self.get(task_id)
        if not task.get("drill"):
            raise LedgerError("not_rehearsal", "Only a task created by a drill can be closed this way.", 422)
        if task["state"] in ("verified", "cancelled"):
            return task
        prev = task["state"]
        task["state"] = "cancelled"
        task["version"] += 1
        self._event(task, "rehearsal_closed", actor="drill", role="system", at=at,
                    detail={"from": prev, "reason": reason})
        return task

    # ---------------------------------------------------------------- evidence
    def _add_evidence(self, task: dict[str, Any], ev: dict[str, Any], *, actor: str, role: str, at: str) -> None:
        kind = ev.get("kind")
        if kind not in EVIDENCE_KINDS:
            raise LedgerError("evidence_kind", f"Unknown evidence type: {kind}", 422)
        if kind not in EVIDENCE_SCOPE.get(task["action_code"], set()):
            raise LedgerError("evidence_scope", f"{kind} does not support {task['action_code']}.", 422)
        tier = EVIDENCE_KINDS[kind]
        observed = ev.get("observed_at") or at
        if kind == "photo":
            age = (datetime.fromisoformat(at) - datetime.fromisoformat(observed)).total_seconds() / 60
            if age > MAX_EVIDENCE_AGE_MIN or not ev.get("in_app", True) or ev.get("zone") not in (None, task["zone_id"]):
                raise LedgerError("evidence_not_current",
                                  "This photo is old, from another zone or not taken in the app. It is not "
                                  "accepted as current evidence.", 422)
        if kind == "independent_spot_check" and role not in INDEPENDENT_ROLES:
            raise LedgerError("independence", "An independent check must come from outside the supervisor's line.",
                              422)
        if kind == "supervisor_attestation" and ev.get("with_photo"):
            # A supervisor's assertion is never upgraded just because it includes a photo (§11.2).
            tier = "E2"
        item = {"id": f"evd_{task['id'][5:]}_{len(task['evidence']) + 1}", "tier": tier, "kind": kind,
                "actor_role": role, "actor_ref": actor, "observed_at": observed,
                "received_at": at, "scope": ev.get("scope", ""), "quality": ev.get("quality", "ok")}
        task["evidence"].append(item)
        if TIERS.index(tier) > TIERS.index(task["achieved_tier"]):
            task["achieved_tier"] = tier

    def add_evidence(self, task_id: str, ev: dict[str, Any], *, actor: str, role: str, at: str) -> dict[str, Any]:
        task = self.get(task_id)
        self._add_evidence(task, ev, actor=actor, role=role, at=at)
        task["version"] += 1
        self._event(task, "evidence_added", actor=actor, role=role, at=at, detail={"kind": ev.get("kind")})
        return task

    # ------------------------------------------------------------------ timers
    def tick(self, now: str) -> list[str]:
        """Escalate tasks not accepted by their start-by deadline (§11.6)."""
        out = []
        for t in self.tasks.values():
            if t["state"] == "assigned" and t["start_by"] < now and t["deadline_min"] > 0:
                self.transition(t["id"], "escalated", actor="system", role="system", at=now,
                                reason="not accepted by the deadline")
                out.append(t["id"])
        return out

    # ------------------------------------------------------------------- utils
    def get(self, task_id: str) -> dict[str, Any]:
        if task_id not in self.tasks:
            raise LedgerError("not_found", "Task not found", 404)
        return self.tasks[task_id]

    def _authorise(self, task: dict[str, Any], new_state: str, role: str) -> None:
        if role == "system":
            return
        if new_state in ("accepted", "in_progress", "reported_complete"):
            if role not in (task["owner_role"], "supervisor", "hse"):
                raise LedgerError("forbidden", "Only the accountable owner can do this.", 403)
            if role == "worker":
                raise LedgerError("forbidden", "Workers confirm or dispute; they do not close tasks.", 403)
        if new_state == "verified" and role not in ("supervisor", "hse"):
            raise LedgerError("forbidden", "Your role cannot verify tasks.", 403)
        if new_state == "cancelled" and role not in ("hse",):
            raise LedgerError("forbidden", "Only the HSE lead can cancel a task, with a recorded reason.", 403)
        if new_state == "escalated" and role not in ("supervisor", "hse"):
            raise LedgerError("forbidden", "Your role cannot escalate tasks.", 403)

    def _event(self, task: dict[str, Any], kind: str, *, actor: str, role: str, at: str,
               detail: dict[str, Any] | None = None) -> None:
        ev = {"id": f"evt_{next(self._ev):05d}", "task": task["id"], "kind": kind, "actor_role": role,
              "actor_ref": actor, "at": at, "state_after": task["state"], "version": task["version"],
              "detail": detail or {}}
        task["history"].append({k: ev[k] for k in ("id", "kind", "actor_role", "at", "state_after")})
        self.events.append(ev)

    def notify(self, *, to_role: str, at: str, template: str, slots: dict[str, Any], task: str | None = None,
               to_actor: str | None = None, online: bool = True) -> dict[str, Any]:
        online = online and to_role not in self.offline_roles
        n = {"id": f"ntf_{next(self._nid):04d}", "to_role": to_role, "to_actor": to_actor, "template": template,
             "slots": slots, "task": task, "queued_at": at,
             "state": "delivered" if online else "queued", "delivered_at": at if online else None}
        self.notifications.append(n)
        return n

    def public(self, task: dict[str, Any], role: str) -> dict[str, Any]:
        """Role-scoped projection: supervisors never see who disputed or who reported missing protection
        (no retaliation signal, §7). Only HSE sees a reporter, and never for anonymous housing reports."""
        t = {k: v for k, v in task.items() if k not in ("history",)}
        t["history"] = task["history"]
        if role != "hse":
            t["disputes"] = [{k: v for k, v in d.items() if k != "raised_by_ref"} for d in task["disputes"]]
        if task.get("reporter_hidden") or role != "hse":
            t.pop("reporter_ref", None)
        t["tier_text"] = TIER_TEXT[task["achieved_tier"]]
        t["required_tier_text"] = TIER_TEXT[task["required_tier"]]
        # Delivery is judged by when the protection started, never by when someone verified it (T30).
        t["on_time"] = (task["performed_start"] <= task["start_by"]) if task.get("performed_start") else None
        return t
