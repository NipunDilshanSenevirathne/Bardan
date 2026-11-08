"""Judge sandbox: one isolated, synthetic world per visitor (finalsystem.md §32.11).

Each sandbox holds its own operational store (ledger), clinical store, consent
store, audit log and AI trace. Sandboxes reset every hour, are capped in number
(least recently used is dropped) and contain no personal data.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any

from . import clock, content, policy
from .audit import AuditLog
from .clinical import ClinicalStore
from .consent import ConsentStore
from .ledger import Ledger
from .scenario import REPLAY_DAY, SCENES, TZ, build_world
from ..forecast import service as forecast_service
from ..planner import certificate as cert
from ..planner.optimiser import changes_vs_draft, solve
from ..planner.twin import draft_to_plan, grid, simulate, slot_label

RESET_AFTER_S = 3600
DRILL_MAX_S = 4 * 3600       # a drill sandbox stays while it is in use, up to four hours
FORECAST_MAX_AGE_H = 24
MAX_SANDBOXES = 300


class DrillRunning(Exception):
    """The scenario clock cannot be moved by hand while an observed drill runs in real time."""


class Sandbox:
    def __init__(self, sid: str) -> None:
        self.id = sid
        self.created = time.time()
        self.last_seen = self.created
        self.world = build_world()
        self.ledger = Ledger()
        self.clinical = ClinicalStore()
        self.clinical.seed(self.world["workers"])
        self.consent = ConsentStore()
        self.consent.seed()
        self.audit = AuditLog()
        self.trace: list[dict[str, Any]] = []
        self.agent_runs: list[dict[str, Any]] = []
        self.checkins: list[dict[str, Any]] = []
        self.reports: list[dict[str, Any]] = []
        self.emergencies: list[dict[str, Any]] = []
        self.plans: dict[str, dict[str, Any]] = {}
        self.active_plan_id: str | None = None
        self.tightened: dict[str, dict[str, Any]] = {}
        self.sync_acks: dict[str, dict[str, Any]] = {}
        self.device_clock: dict[str, str] = {}     # last trusted device time per device (T55)
        self.copilot_log: list[dict[str, Any]] = []
        self.policy_drafts: dict[str, dict[str, Any]] = {}
        self.review_tasks: list[dict[str, Any]] = []
        self.exports: list[dict[str, Any]] = []
        self.tour_steps: set[str] = set()
        self.intake_drafts: dict[str, dict[str, Any]] = {}
        self.live_clock: dict[str, Any] | None = None   # set while an observed drill runs in real time
        self.drills: Any = None                          # DrillSeries, for a drill sandbox (core/drill.py)
        self.lock = threading.RLock()
        self.audit.append(at=self.now(), actor="system", role="system", action="sandbox.created",
                          resource=f"sandbox:{sid}", category="security",
                          detail={"label": self.world["label"]})

    # ----------------------------------------------------------------- clock
    def now(self) -> str:
        lc = self.live_clock
        if lc is not None:
            return (lc["scene0"] + timedelta(seconds=int(clock.wall() - lc["wall0"]))).isoformat()
        return self.world["clock"]

    def go_live(self) -> None:
        """Run the scenario clock in real time from where it stands (observed drills)."""
        if self.live_clock is None:
            self.live_clock = {"scene0": datetime.fromisoformat(self.world["clock"]), "wall0": clock.wall()}

    def freeze(self) -> None:
        if self.live_clock is not None:
            self.world["clock"] = self.now()
            self.live_clock = None

    def drill_running(self) -> bool:
        return bool(self.drills is not None and self.drills.running())

    def expired(self, now_s: float) -> bool:
        """Judge sandboxes reset every hour. A drill sandbox is kept while people are using it (up to four hours),
        so a drill series is not lost halfway through."""
        age = now_s - self.created
        if self.drills is not None and now_s - self.last_seen < RESET_AFTER_S:
            return age > DRILL_MAX_S
        return age > RESET_AFTER_S

    def set_scene(self, scene_id: str, actor: str = "system") -> dict[str, Any]:
        scene = next((s for s in SCENES if s["id"] == scene_id), None)
        if not scene:
            raise KeyError(scene_id)
        if self.drill_running():
            raise DrillRunning("A drill is running in real time. End it before changing the scene.")
        prev = self.world["clock"]
        self.world["clock"] = scene["at"]
        self.world["scene"] = scene_id
        notes = []
        if scene["at"][:10] == REPLAY_DAY and not self.active_plan():
            notes.append(self._precondition_activate())
        if scene["at"] > prev:
            notes.append(self._background_activity(scene["at"]))
        self.ledger.tick(self.now())
        self.audit.append(at=self.now(), actor=actor, role="system", action="scenario.scene", resource=scene_id,
                          category="security", detail={"notes": notes})
        return {"scene": scene, "notes": [n for n in notes if n]}

    def advance(self, minutes: int) -> str:
        if self.drill_running():
            raise DrillRunning("A drill is running in real time. End it before moving the clock.")
        t = datetime.fromisoformat(self.now()) + timedelta(minutes=minutes)
        self.world["clock"] = t.isoformat()
        self.ledger.tick(self.now())
        return self.now()

    def _precondition_activate(self) -> str:
        """Scenario script: if a judge jumps straight to the shift, run the planning step on behalf of the
        synthetic supervisor so the day is coherent. Recorded as a scenario precondition in the audit log."""
        target = self.world["clock"]
        self.world["clock"] = next(s["at"] for s in SCENES if s["id"] == "evening")  # planning is an evening step
        try:
            sc = self.optimise(actor="S01 (scenario script)")
            if sc.get("status") in ("OPTIMAL", "FEASIBLE"):
                self.approve_plan(sc["scenario_id"], actor="S01 (scenario script)")
                self.activate_plan(sc["scenario_id"], actor="S01 (scenario script)", force_basis=True)
                msg = ("Scenario script ran the evening-before planning step: the optimised plan for 19 Aug was "
                       "approved and activated at 18:00 on 18 Aug.")
            else:
                msg = "No plan could be activated."
        finally:
            self.world["clock"] = target
        return msg

    def _background_activity(self, until: str) -> str | None:
        """Scenario script for scene jumps: the synthetic supervisor's routine morning, so a judge who jumps
        ahead does not land on a site where nobody accepted the day's plan tasks. Only routine plan tasks are
        touched (never worker reports or disputes), and every step is labelled in the evidence and audit log."""
        from .ledger import ALLOWED, LedgerError
        actor = "S01 (scenario script)"
        scope = "Scenario script: routine step simulated because the scene jumped ahead"
        day = REPLAY_DAY
        n = 0
        for t in list(self.ledger.tasks.values()):
            if t["source"] != "plan_activation" or t["action_code"] == "TRAINING_DUE":
                continue
            c = datetime.fromisoformat(t["created_at"])
            iso = lambda m: (c + timedelta(minutes=m)).isoformat()  # noqa: E731
            steps: list[tuple[str, str, dict[str, Any] | None]] = [("accepted", iso(10), None)]
            code = t["action_code"]
            if code == "ENHANCED_SCHEDULE":
                steps.append(("in_progress", iso(15), None))
            elif code == "NEW_WORKER_REVIEW":
                steps += [("in_progress", iso(15), None),
                          ("reported_complete", f"{day}T07:00:00{TZ}", {"kind": "review_record", "scope": scope}),
                          ("verified", f"{day}T07:05:00{TZ}", None)]
            elif code == "SHADE_EXTEND":
                steps += [("in_progress", f"{day}T11:15:00{TZ}", None),
                          ("reported_complete", f"{day}T11:35:00{TZ}", {"kind": "capacity_record", "scope": scope}),
                          ("verified", f"{day}T11:40:00{TZ}", None)]
            for state, when, ev in steps:
                if when > until:
                    break
                if state not in ALLOWED.get(t["state"], set()):
                    continue
                try:
                    self.ledger.transition(t["id"], state, actor=actor, role="supervisor", at=when, evidence=ev,
                                           reason="scenario script (scene jump)")
                    n += 1
                except LedgerError:
                    break
        if n:
            self.audit.append(at=until, actor=actor, role="system", action="scenario.background_activity",
                              resource="ledger", category="security", detail={"steps": n})
            return f"Scenario script recorded {n} routine supervisor steps for the time skipped (labelled)."
        return None

    # ---------------------------------------------------------------- lookups
    def worker(self, wid: str) -> dict[str, Any]:
        w = next((x for x in self.world["workers"] if x["id"] == wid), None)
        if not w:
            raise KeyError(wid)
        r = self.clinical.restrictions.get(wid)
        w["restriction"] = {"label": r["label"], "until": r["until"]} if r and r["label"] != "none" else None
        return w

    def sync_restrictions(self) -> None:
        """Copy the clinician's current operational labels (never reasons) onto the roster used for planning."""
        for w in self.world["workers"]:
            self.worker(w["id"])

    def active_plan(self) -> dict[str, Any] | None:
        return self.plans.get(self.active_plan_id) if self.active_plan_id else None

    def recent_symptoms(self, wid: str, window_min: int = 90) -> list[str]:
        now = datetime.fromisoformat(self.now())
        out = []
        for c in self.checkins:
            if c["worker_ref"] != wid or c.get("resolved"):
                continue
            age = (now - datetime.fromisoformat(c["at"])).total_seconds() / 60
            if 0 <= age <= window_min:
                out.extend(c.get("symptoms", []))
        for e in self.emergencies:
            if e["subject"] == wid and not e.get("closed"):
                out.extend(e.get("symptoms", []))
        return sorted(set(out))

    def water_status(self, zone: str) -> str:
        for t in self.ledger.tasks.values():
            if t["action_code"] == "WATER_RESTORE" and t["zone_id"] == zone and t["state"] not in ("verified",
                                                                                                "cancelled"):
                return "reported_empty"
        return "available"

    def exemption_for(self, task_id: str) -> dict[str, Any] | None:
        return next((e for e in self.world["exemptions"] if e["task"] == task_id and e.get("authorised")), None)

    # -------------------------------------------------------------- tighten
    def tighten(self, w: dict[str, Any], a: dict[str, Any], res: dict[str, Any], obs: dict[str, Any] | None):
        from .live import current_slot
        if w["id"] in self.tightened:
            return self.tightened[w["id"]]
        rec = {"worker": w["id"], "at": self.now(), "since_slot": current_slot(self.now()),
               "from_task": a["task"]["id"], "zone": a["zone"]["id"], "reasons": res["reasons"],
               "observation": {k: (obs or {}).get(k) for k in ("value", "unit", "observed_at", "instrument")}}
        self.tightened[w["id"]] = rec
        task = self.ledger.create(
            action_code="MOVE_TO_SHADED_TASK", zone=a["zone"]["id"], now=self.now(),
            rationale=(f"Live reading {rec['observation']['value']} W/m2 at {rec['observation']['observed_at'][11:16]} "
                       f"puts Zone {a['zone']['id']} in the buffer band. Workers in their first days stop heat work "
                       f"(AE-AD-HEAT). Live values govern; the plan tightened automatically."),
            rationale_ar=(f"قراءة مباشرة {rec['observation']['value']} واط/م² الساعة "
                          f"{rec['observation']['observed_at'][11:16]} تضع المنطقة {a['zone']['id']} في النطاق العازل. "
                          f"يتوقف العمال في أيامهم الأولى عن العمل في الحر (AE-AD-HEAT). القراءات المباشرة هي الحاكمة، "
                          f"وقد شُددت الخطة تلقائياً."),
            source="live_policy_engine", crew=w["crew"], affected=[w["id"]],
            extra={"worker_label": w["name"]})
        rec["task"] = task["id"]
        self.audit.append(at=self.now(), actor="policy-engine", role="system", action="plan.tightened_live",
                          resource=task["id"], subject=w["id"], detail={"reasons": res["reasons"]})
        self.ledger.notify(to_role="worker", to_actor=w["id"], at=self.now(), template="msg.new_worker_harsh",
                           slots={"name": w["name"].split()[0]})
        return rec

    # ------------------------------------------------------------- planning
    def forecast(self, mode: str = "scenario") -> dict[str, Any]:
        enabled = self.world["settings"].get("forecast_enabled", True)
        if mode == "live":
            return forecast_service.live_forecast(self.world["site"]["lat"], self.world["site"]["lon"],
                                                  enabled=enabled)
        fc = forecast_service.scenario_forecast(enabled=enabled)
        if fc.get("available"):
            age_h = (datetime.fromisoformat(self.now()) - datetime.fromisoformat(fc["issued_at"])).total_seconds() / 3600
            if age_h > FORECAST_MAX_AGE_H:
                # A stale forecast is never used for planning: "forecast unavailable" and the season's standard
                # plan (T14). Live readings still govern the day.
                return {**forecast_service.unavailable(fc["issued_at"], f"Forecast is {int(age_h)} hours old (stale, "
                                                                         f"limit {FORECAST_MAX_AGE_H} h)."),
                        "stale": True, "age_hours": round(age_h, 1)}
        return fc

    def _basis(self, fc: dict[str, Any]) -> dict[str, Any]:
        seats = {r["id"]: (r["seats"], r["working"], r["accessible"]) for r in self.world["rest_areas"]}
        restr = {k: v["label"] for k, v in self.clinical.restrictions.items()}
        return {"policy_versions": list(self.world["site"]["policy_packs"]),
                "forecast_issued_at": fc.get("issued_at"), "forecast_available": fc.get("available"),
                "resources_hash": _h(seats), "restrictions_hash": _h(restr)}

    def evaluate_draft(self, actor: str) -> dict[str, Any]:
        self.sync_restrictions()
        fc = self.forecast()
        g = grid(self.world, fc, REPLAY_DAY)
        plan = draft_to_plan(self.world)
        twin = simulate(self.world, g, plan)
        reval = cert.revalidate(self.world, g, plan, REPLAY_DAY)
        sid = f"plan_draft_{len(self.plans) + 1}"
        sc = {"scenario_id": sid, "kind": "draft", "for_date": REPLAY_DAY, "created_at": self.now(),
              "created_by": actor, "forecast_issued_at": fc.get("issued_at"),
              "forecast_label": fc.get("label"), "plan": plan, "metrics": twin["metrics"], "twin": twin,
              "revalidation": reval, "basis": self._basis(fc), "approval": {"state": "not_submitted"},
              "label": "SIMULATION", "grid": _grid_public(g)}
        sc["forecast_available"] = bool(fc.get("available"))
        if not fc.get("available"):
            # Without a forecast, heat-band metrics cannot be judged; nothing is relaxed (T71).
            sc["fallback"] = self._season_standard_plan()
            sc["message"] = content.TEMPLATES["msg.forecast_unavailable"]
        self.plans[sid] = sc
        self.audit.append(at=self.now(), actor=actor, role="supervisor", action="plan.evaluate_draft", resource=sid)
        return sc

    def optimise(self, actor: str, extra_seats: dict[str, int] | None = None,
                 task_overrides: dict[str, dict[str, Any]] | None = None, kind: str = "optimised") -> dict[str, Any]:
        self.sync_restrictions()
        fc = self.forecast()
        sid = f"plan_{kind}_{len(self.plans) + 1}"
        if not fc.get("available"):
            sc = {"scenario_id": sid, "kind": kind, "status": "FORECAST_UNAVAILABLE", "for_date": REPLAY_DAY,
                  "forecast_available": False,
                  "created_at": self.now(), "created_by": actor, "fallback": self._season_standard_plan(),
                  "message": content.TEMPLATES["msg.forecast_unavailable"], "label": "SIMULATION"}
            self.plans[sid] = sc
            return sc
        g = grid(self.world, fc, REPLAY_DAY)
        res = solve(self.world, g, extra_seats=extra_seats, task_overrides=task_overrides)
        draft = draft_to_plan(self.world)
        draft_twin = simulate(self.world, g, draft)
        if res["status"] not in ("OPTIMAL", "FEASIBLE"):
            sc = {"scenario_id": sid, "kind": kind, "status": res["status"], "for_date": REPLAY_DAY,
                  "created_at": self.now(), "created_by": actor, "solver": res["solver"],
                  "diagnosis": res.get("diagnosis"), "message": res.get("message"), "label": "SIMULATION",
                  "draft_metrics": draft_twin["metrics"]}
            self.plans[sid] = sc
            return sc
        plan = res["plan"]
        twin = simulate(self.world, g, plan)
        reval = cert.revalidate(self.world, g, plan, REPLAY_DAY)
        sc = {"scenario_id": sid, "kind": kind, "status": res["status"], "for_date": REPLAY_DAY,
              "forecast_available": True,
              "created_at": self.now(), "created_by": actor, "forecast_issued_at": fc.get("issued_at"),
              "forecast_label": fc.get("label"), "plan": plan, "solver": res["solver"], "stages": res["stages"],
              "metrics": twin["metrics"], "draft_metrics": draft_twin["metrics"], "twin": twin,
              "draft_twin": {k: draft_twin[k] for k in ("rest_conflicts", "missing_rest", "violations",
                                                        "unacclimatized")},
              "changes": changes_vs_draft(self.world, plan, g), "revalidation": reval,
              "basis": self._basis(fc), "approval": {"state": "pending", "required_role": "supervisor"},
              "label": "SIMULATION", "grid": _grid_public(g),
              "inputs": {"extra_seats": extra_seats or {}, "task_overrides": task_overrides or {}}}
        sc["certificate"] = cert.certificate(self.world, sc) if reval["result"] == "valid" else None
        sc["worker_messages"] = self._tomorrow_messages(sc)
        self.plans[sid] = sc
        self.audit.append(at=self.now(), actor=actor, role="supervisor", action="plan.optimise", resource=sid,
                          detail={"status": sc["status"], "revalidation": reval["result"]})
        return sc

    def approve_plan(self, sid: str, actor: str) -> dict[str, Any]:
        sc = self.plans[sid]
        if sc.get("revalidation", {}).get("result") != "valid":
            raise ValueError("Only a plan that passed independent re-validation can be approved.")
        sc["approval"] = {"state": "approved", "by": actor, "at": self.now(), "required_role": "supervisor"}
        for m in sc.get("worker_messages", []):
            n = self.ledger.notify(to_role="worker", to_actor=m["worker"], at=self.now(), template=m["template_id"],
                                   slots=m["slots"])
            n["slots_by_lang"] = m.get("slots_by_lang")
        self.audit.append(at=self.now(), actor=actor, role="supervisor", action="plan.approve", resource=sid)
        return sc

    def activate_plan(self, sid: str, actor: str, force_basis: bool = False) -> dict[str, Any]:
        sc = self.plans[sid]
        if sc.get("approval", {}).get("state") != "approved":
            raise ValueError("Activation needs supervisor approval first.")
        fc = self.forecast()
        now_basis = self._basis(fc)
        changed = [k for k in now_basis if now_basis[k] != sc["basis"].get(k)]
        if changed and not force_basis:
            sc["activation"] = {"state": "rejected", "at": self.now(), "changed": changed}
            self.audit.append(at=self.now(), actor=actor, role="supervisor", action="plan.activate",
                              resource=sid, decision="denied", reason="basis changed: " + ", ".join(changed))
            raise ValueError("Something changed since evaluation (" + ", ".join(changed) +
                             "). The old plan is invalidated; re-evaluate before activating.")
        # Supersede any older active plan, keeping it as history.
        if self.active_plan_id and self.active_plan_id != sid:
            self.plans[self.active_plan_id]["activation"]["state"] = "superseded"
        sc["activation"] = {"state": "active", "at": self.now(), "by": actor,
                            "rechecked": ["policy_versions", "forecast", "resources", "restrictions"]}
        self.active_plan_id = sid
        self._seed_day_tasks(sc)
        self.audit.append(at=self.now(), actor=actor, role="supervisor", action="plan.activate", resource=sid)
        return sc

    def _seed_day_tasks(self, sc: dict[str, Any]) -> None:
        """Required daily actions from the activated plan (ENHANCED_SCHEDULE, new-worker reviews, training, AC)."""
        if any(t["source"] == "plan_activation" for t in self.ledger.tasks.values()):
            return
        at = f"{REPLAY_DAY}T05:15:00{TZ}" if self.now() < f"{REPLAY_DAY}T05:15:00{TZ}" else self.now()
        for crew in ("C1", "C2", "C3"):
            self.ledger.create(action_code="ENHANCED_SCHEDULE", zone={"C1": "B", "C2": "A", "C3": "C"}[crew],
                               now=at, rationale="Forecast acclimatization and buffer bands: hourly shaded breaks "
                               "as staggered in the approved plan.", source="plan_activation", crew=crew,
                               rationale_ar="نطاقا التأقلم والعازل في التوقعات: استراحات مظللة كل ساعة وفق التوزيع "
                                            "في الخطة المعتمدة.",
                               plan_id=sc["scenario_id"])
        for w in self.world["workers"]:
            if w["acclimatization"] == "new":
                self.ledger.create(action_code="NEW_WORKER_REVIEW", zone=None, now=at,
                                   rationale=f"Day {w['day']} of the documented schedule "
                                   f"({policy.acclimatization_percent(w)}% heat time) with a buddy.",
                                   rationale_ar=f"اليوم {w['day']} من الجدول الموثق ({policy.acclimatization_percent(w)}% "
                                                f"من وقت الحر) مع زميل.",
                                   source="plan_activation", crew=w["crew"], affected=[w["id"]],
                                   plan_id=sc["scenario_id"], extra={"worker_label": w["name"]})
        n_new = sum(1 for w in self.world["workers"] if w["acclimatization"] == "new")
        self.ledger.create(action_code="TRAINING_DUE", zone=None, now=at,
                           rationale=f"CoP 11.0: heat training within 10 days of starting ({n_new} new workers).",
                           rationale_ar=f"مدونة الممارسات 11.0: تدريب على الحرارة خلال 10 أيام من البدء ({n_new} عمال جدد).",
                           source="plan_activation", plan_id=sc["scenario_id"])
        self.ledger.create(action_code="SHADE_EXTEND", zone="R1", now=at,
                           rationale="Midday shelter check: cooled canteen R3 opens 11:30 with 30 seats for 40 "
                                     "workers in two sittings.", source="plan_activation",
                           rationale_ar="فحص مظلة منتصف النهار: يفتح المقصف المكيف R3 الساعة 11:30 بثلاثين مقعداً "
                                        "لأربعين عاملاً على دفعتين.",
                           plan_id=sc["scenario_id"])

    def _season_standard_plan(self) -> dict[str, Any]:
        return {"label_en": self.world["site"]["fallback_plan"], "label_ar": self.world["site"]["fallback_plan_ar"],
                "source": "site fallback plan (approved by HSE)", "relaxes_anything": False}

    def _tomorrow_messages(self, sc: dict[str, Any]) -> list[dict[str, Any]]:
        """Evening messages in each worker's language. Slots are kept for both languages so the same message
        renders correctly whichever interface language the worker chooses."""
        out = []
        tasks = {t["crew"]: t for t in sc["plan"]["tasks"]}
        zones = {z["id"]: z for z in self.world["zones"]}
        dates = {"en": "19 Aug", "ar": "19 أغسطس"}
        for w in self.world["workers"]:
            t = tasks.get(w["crew"])
            if not t or not t["slots"]:
                continue
            lang = w["lang"]
            br = [b for b in sc["plan"]["breaks"] if w["crew"] in (b.get("crews") or [b["crew"]])][:3]
            br_txt = ", ".join(_q(b["start_q"]) for b in br)
            z = zones[t["zone"]]
            a = (sc["plan"].get("assignments") or {}).get(w["id"])
            by_lang: dict[str, dict[str, Any]] = {}
            if a is not None and w["acclimatization"] == "new":
                heat = a["heat_slots"]
                heat_txt = f"{slot_label(heat[0])}-{slot_label(heat[-1] + 1)}" if heat else "-"
                for lg in ("en", "ar"):
                    by_lang[lg] = {"date": dates[lg], "induction": "05:30-07:00",
                                   "task": t.get("name_ar") if lg == "ar" else t["name"], "heat": heat_txt}
                tid = "msg.tomorrow_new_worker"
            else:
                for lg in ("en", "ar"):
                    by_lang[lg] = {"date": dates[lg], "start": slot_label(t["slots"][0]),
                                   "place": z.get("name_ar") if lg == "ar" else z["name"],
                                   "breaks": (br_txt.replace(", ", "، ") if lg == "ar" else br_txt) or "-"}
                tid = "msg.tomorrow_start"
            out.append({"worker": w["id"], "lang": lang, "template_id": tid, "slots": by_lang[lang],
                        "slots_by_lang": by_lang, "text": content.render(tid, lang, **by_lang[lang])})
        return out

    # ------------------------------------------------------------- reporting
    def ai_enabled(self, capability: str | None = None) -> bool:
        s = self.world["settings"]
        if not s.get("ai_enabled", True):
            return False
        if capability and s.get("ai_capabilities", {}).get(capability) is False:
            return False
        return True

    def record_trace(self, run: dict[str, Any]) -> dict[str, Any]:
        run = {"id": f"run_{len(self.trace) + 1:04d}", "at": self.now(), **run}
        self.trace.append(run)
        if run.get("gate", {}).get("decision") == "blocked":
            self.audit.append(at=self.now(), actor=run.get("actor", "ai"), role="ai", action="ai.gate_blocked",
                              resource=run["id"], category="ai", decision="denied",
                              reason=",".join(r["rule"] for r in run["gate"].get("reasons", [])))
        return run


def _h(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _q(q: int) -> str:
    t = 300 + 15 * q
    return f"{t // 60:02d}:{t % 60:02d}"


def _grid_public(g: dict[str, Any]) -> dict[str, Any]:
    return {"midday": g["midday"], "zones": {z: [{"time": r["time"], "band": r["band"], "wbgt_hi": r["wbgt_hi"],
                                                    "wbgt_point": r["wbgt_point"]} for r in rows]
                                             for z, rows in g["zones"].items()}}


class SandboxStore:
    def __init__(self) -> None:
        self._data: OrderedDict[str, Sandbox] = OrderedDict()
        self._lock = threading.Lock()
        self.stats = {"sessions": 0, "tour_steps": 0, "resets": 0}

    def create(self) -> Sandbox:
        sid = "sb_" + secrets.token_hex(6)
        sb = Sandbox(sid)
        with self._lock:
            self._data[sid] = sb
            self.stats["sessions"] += 1
            while len(self._data) > MAX_SANDBOXES:
                self._data.popitem(last=False)
        return sb

    def get(self, sid: str) -> tuple[Sandbox, bool]:
        """Return the sandbox and whether it was reset (hourly) on this access."""
        with self._lock:
            sb = self._data.get(sid)
            reset = False
            if sb is None or sb.expired(time.time()):
                sb = Sandbox(sid)
                self._data[sid] = sb
                reset = True
                self.stats["resets"] += 1
            self._data.move_to_end(sid)
            sb.last_seen = time.time()
            return sb, reset

    def peek(self, sid: str) -> Sandbox | None:
        """Look up a sandbox without creating, resetting or touching it."""
        with self._lock:
            sb = self._data.get(sid)
            return None if sb is None or sb.expired(time.time()) else sb

    def reset(self, sid: str) -> Sandbox:
        with self._lock:
            old = self._data.get(sid)
            if old is not None and old.drills is not None:
                raise DrillRunning("This is a drill sandbox, and a reset would lose the drill results. Export them "
                                   "on the drill console; for a fresh tour, choose a persona on the start page.")
            sb = Sandbox(sid)
            self._data[sid] = sb
            return sb


STORE = SandboxStore()
