"""Observed drills: the same failure, the same people, two ways of working (finalsystem.md §29.7, §30).

This replaces the earlier simulated alert-only comparison, whose result followed from its own assumptions.
A facilitator runs short role-play drills in a dedicated sandbox. A water point runs dry (or the shaded rest
area is full) and the team restores it, once with its usual way of working ("current") and once with Bardan,
with the same people, resources and safety procedures. The order is counterbalanced (A B B A) and in each way of
working one drill, chosen at random and kept from the participants, includes a false report that the fix is done.

The observer records the same moments in both arms on the drill console: when the failure was reported, when the
fix started, when it was reported fixed, when the control was really back (seen by the observer) and when someone
other than the person who fixed it confirmed it. In the Bardan arm the ledger also records its own times, which
fill any moment the observer did not mark (the source of every time is kept).

Results are counts, medians and ranges from a handful of drills, shown drill by drill. They show the workflow
running with real people under drill conditions. They are not a site trial and not a health outcome.
"""
from __future__ import annotations

import hashlib
import json
import random
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from . import clock

SCHEMA = "bardan.drill-export@1"
ARMS = ("current", "bardan")
SCENARIOS: dict[str, dict[str, Any]] = {
    # Drill targets are agreed before the first drill and locked; they are drill targets, not legal limits.
    "water_out": {"control": "WATER_RESTORE", "intent": "RESOURCE_WATER_UNAVAILABLE", "deadline_min": 20,
                  "zone": "A"},
    "shade_full": {"control": "SHADE_EXTEND", "intent": "RESOURCE_SHADE_FULL", "deadline_min": 25, "zone": "A"},
}
MARKS = ("reported", "fix_started", "reported_fixed", "restored_seen", "independent_check", "false_report_caught")
OBSERVER_ONLY = {"restored_seen"}            # the ground truth is never taken from the system
CONFIRMING_KINDS = {"worker_confirmation", "independent_spot_check", "water_point_check", "photo", "capacity_record"}
TOLERANCE_S = 60       # a confirmation within a minute of the observer seeing the control back counts as after it
MAX_PER_ARM = 6
PARTICIPANT_ROLES = {"worker", "supervisor", "hse"}
CAP_MIN = 60           # a drill that runs this long is ended automatically

DEFINITIONS = {
    "restored_seen": "The observer saw the control really back (water at the point; a shaded seat free).",
    "independent_check": "Someone other than the person who fixed it confirmed it is back, in the way the "
                         "workflow allows (Bardan: the worker's confirmation or an HSE check; current: any "
                         "check the site normally does).",
    "minutes_to_verified": "Minutes from the start of the failure until the control was back and independently "
                           "confirmed (the later of the two). A confirmation more than a minute before the "
                           "control was really back is a false confirmation, not a verification.",
    "verified_by_deadline": "Restored and independently confirmed within the drill target agreed before the "
                            "first drill.",
    "false_report": "In one drill of each way of working, the person fixing it was asked in private to report it "
                    "fixed without fixing it. Caught means the workflow flagged it (Bardan: a worker dispute; "
                    "current: someone noticed and acted).",
    "timing": "Medians and ranges use the drills without a false report. Every drill is listed.",
}
LABEL = ("Observed drill results: a handful of role-play drills, shown drill by drill. Not a site trial and not a "
         "health outcome.")


class DrillError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code = code
        self.status = status


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def _minutes(a: str | None, b: str | None) -> float | None:
    if not a or not b:
        return None
    return round((_dt(b) - _dt(a)).total_seconds() / 60, 2)


def plan_order(per_arm: int, first: str) -> list[str]:
    """Counterbalanced order: A B B A A B B A ... with equal numbers in each arm."""
    second = ARMS[1] if first == ARMS[0] else ARMS[0]
    seq: list[str] = []
    while len(seq) < 2 * per_arm:
        seq += [first, second, second, first]
    return seq[: 2 * per_arm]


# ------------------------------------------------------------------------------------------- pure results
def outcome_from(marks: dict[str, dict[str, Any]], *, started_at: str, deadline_min: int, probe: bool,
                 early_confirmations: int = 0) -> dict[str, Any]:
    """One drill's result from its moments (real times). Pure, so a published export can be re-checked."""
    m = {k: _minutes(started_at, v["at"]) for k, v in marks.items() if k in MARKS}
    restored, ind = m.get("restored_seen"), m.get("independent_check")
    tol = TOLERANCE_S / 60
    early = early_confirmations > 0 or (ind is not None and (restored is None or ind < restored - tol))
    verified = max(restored, ind) if restored is not None and ind is not None and ind >= restored - tol else None
    caught = m.get("false_report_caught") if probe else None
    return {
        "minutes": m,
        "minutes_to_restored": restored,
        "minutes_to_verified": verified,
        "restored_by_deadline": restored is not None and restored <= deadline_min,
        "verified_by_deadline": verified is not None and verified <= deadline_min,
        "false_confirmation": bool(early),
        "probe": probe,
        "false_report_caught": (caught is not None) if probe else None,
        "minutes_to_caught": caught,
        "caught_by_deadline": (caught is not None and caught <= deadline_min) if probe else None,
        "sources": {k: v.get("source") for k, v in marks.items() if k in MARKS},
    }


def _spread(xs: list[float]) -> dict[str, Any]:
    if not xs:
        return {"n": 0, "median": None, "min": None, "max": None, "values": []}
    return {"n": len(xs), "median": round(statistics.median(xs), 1), "min": round(min(xs), 1),
            "max": round(max(xs), 1), "values": [round(x, 1) for x in xs]}


def summary_from(drills: list[dict[str, Any]], deadline_min: int) -> dict[str, Any]:
    """Per way of working: counts, and medians with ranges for the drills without a false report."""
    arms: dict[str, Any] = {}
    for arm in ARMS:
        ended = [d for d in drills if d["arm"] == arm and d["state"] == "ended"]
        outs = [d["outcome"] for d in ended]
        timing = [d["outcome"] for d in ended if not d["probe"]]
        probes = [d["outcome"] for d in ended if d["probe"]]
        rest = [o["minutes_to_restored"] for o in timing if o["minutes_to_restored"] is not None]
        ver = [o["minutes_to_verified"] for o in timing if o["minutes_to_verified"] is not None]
        arms[arm] = {
            "drills_run": len(ended),
            "abandoned": sum(1 for d in drills if d["arm"] == arm and d["state"] == "abandoned"),
            "timing_drills": len(timing),
            "minutes_to_restored": _spread(rest),
            "minutes_to_verified": _spread(ver),
            "not_verified": sum(1 for o in timing if o["minutes_to_verified"] is None),
            "verified_by_deadline": {"k": sum(bool(o["verified_by_deadline"]) for o in outs), "n": len(outs)},
            "restored_by_deadline": {"k": sum(bool(o["restored_by_deadline"]) for o in outs), "n": len(outs)},
            "false_reports": {"n": len(probes), "caught": sum(bool(o["false_report_caught"]) for o in probes),
                              "caught_by_deadline": sum(bool(o["caught_by_deadline"]) for o in probes),
                              "minutes_to_caught": [o["minutes_to_caught"] for o in probes]},
            "false_confirmations": sum(bool(o["false_confirmation"]) for o in outs),
            "app_actions_in_current_arm": (sum(d.get("app_actions_in_current_arm") or 0 for d in ended)
                                           if arm == "current" else None),
        }
    planned = [d["arm"] for d in drills]
    run = [d["arm"] for d in sorted((x for x in drills if x.get("started_at")), key=lambda x: x["started_at"])]
    return {"arms": arms, "deadline_min": deadline_min, "order_planned": planned,
            "order_followed": run == planned[: len(run)], "label": LABEL}


def _digest(body: dict[str, Any]) -> str:
    clean = {k: v for k, v in body.items() if k not in ("sha256", "integrity", "published")}
    return hashlib.sha256(json.dumps(clean, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                          .encode()).hexdigest()


def check_export(body: dict[str, Any]) -> list[str]:
    """Problems with an exported series (empty when it is intact): schema, hash, and that every drill's result
    and the summary follow from the recorded moments."""
    problems = []
    if body.get("schema") != SCHEMA:
        problems.append("schema")
    if body.get("sha256") != _digest(body):
        problems.append("hash")
    dl = (body.get("series") or {}).get("deadline_min")
    for d in body.get("drills", []):
        if d.get("state") != "ended":
            continue
        again = outcome_from(d.get("effective_marks") or {}, started_at=d["started_at"], deadline_min=d["deadline_min"],
                             probe=bool(d.get("probe")), early_confirmations=d.get("early_confirmations") or 0)
        if again != d.get("outcome"):
            problems.append(f"outcome:{d.get('id')}")
    if dl is not None and summary_from(body.get("drills", []), dl) != body.get("summary"):
        problems.append("summary")
    return problems


# ------------------------------------------------------------------------------------------- the series
class DrillSeries:
    def __init__(self, *, label: str, scenario: str, per_arm: int, probes: bool, deadline_min: int | None,
                 people: int | None, setting: str, languages: list[str], created_by: str,
                 seed: int | None = None) -> None:
        if scenario not in SCENARIOS:
            raise DrillError("scenario", "Unknown drill scenario.", 422)
        if not 1 <= per_arm <= MAX_PER_ARM:
            raise DrillError("per_arm", f"Choose 1 to {MAX_PER_ARM} drills for each way of working.", 422)
        rng = random.Random(seed if seed is not None else int(clock.wall() * 1000))
        sc = SCENARIOS[scenario]
        self.id = "drs_" + hashlib.sha256(f"{clock.wall()}{rng.random()}".encode()).hexdigest()[:8]
        self.label = (label or "").strip()[:80]
        self.scenario = scenario
        self.per_arm = per_arm
        self.deadline_min = int(deadline_min or sc["deadline_min"])
        self.setting = setting if setting in ("role_play", "site_exercise") else "role_play"
        self.people = people
        self.languages = [x for x in languages if x in ("en", "ar")] or ["en"]
        self.created_at = clock.wall_iso()
        self.created_by = created_by
        order = plan_order(per_arm, rng.choice(ARMS))
        probe_at: set[int] = set()
        if probes:
            for arm in ARMS:
                probe_at.add(rng.choice([i for i, a in enumerate(order) if a == arm]))
        self.drills: list[dict[str, Any]] = [
            {"id": f"drl_{i + 1:02d}", "index": i + 1, "arm": arm, "scenario": scenario, "zone": sc["zone"],
             "control": sc["control"], "probe": i in probe_at, "deadline_min": self.deadline_min,
             "state": "planned", "started_at": None, "ended_at": None, "scene_started_at": None,
             "marks": {}, "task": None, "events_from": None, "audit_from": None, "notes": "",
             "abandon_reason": None,
             "app_actions_in_current_arm": 0, "ended_by": None}
            for i, arm in enumerate(order)]
        self.locked = False   # the target and the plan are fixed once the first drill starts

    # ------------------------------------------------------------------ state
    def running(self) -> dict[str, Any] | None:
        return next((d for d in self.drills if d["state"] == "running"), None)

    def get(self, drill_id: str) -> dict[str, Any]:
        d = next((x for x in self.drills if x["id"] == drill_id), None)
        if d is None:
            raise DrillError("not_found", "Drill not found.", 404)
        return d

    def next_planned(self) -> dict[str, Any] | None:
        return next((d for d in self.drills if d["state"] == "planned"), None)

    # ---------------------------------------------------------------- actions
    def start(self, sb, drill_id: str | None = None) -> dict[str, Any]:
        if self.running():
            raise DrillError("running", "A drill is already running. End it first.")
        d = self.get(drill_id) if drill_id else self.next_planned()
        if d is None:
            raise DrillError("done", "Every planned drill has been run.")
        if d["state"] != "planned":
            raise DrillError("state", "This drill has already been run.")
        self.locked = True
        sb.go_live()
        d.update(state="running", started_at=clock.wall_iso(), scene_started_at=sb.now(),
                 events_from=len(sb.ledger.events), audit_from=len(sb.audit.entries))
        sb.audit.append(at=sb.now(), actor=self.created_by, role="auditor", action="drill.started",
                        resource=d["id"], category="security",
                        detail={"arm": d["arm"], "scenario": d["scenario"], "series": self.id})
        return d

    def mark(self, sb, drill_id: str, mark: str, *, undo: bool = False) -> dict[str, Any]:
        d = self.get(drill_id)
        if mark not in MARKS:
            raise DrillError("mark", "Unknown drill moment.", 422)
        if d["state"] != "running" and not (d["state"] == "ended" and undo):
            raise DrillError("state", "Moments can only be recorded while the drill runs (a wrong one can be "
                                      "removed afterwards).")
        if undo:
            d["marks"].pop(mark, None)
        else:
            d["marks"][mark] = {"at": clock.wall_iso(), "source": "observer"}
        return d

    def end(self, sb, drill_id: str, *, notes: str = "", by: str = "observer") -> dict[str, Any]:
        d = self.get(drill_id)
        if d["state"] != "running":
            raise DrillError("state", "This drill is not running.")
        d.update(state="ended", ended_at=clock.wall_iso(), notes=(notes or "")[:300], ended_by=by)
        if d["arm"] == "current":
            # The current way of working must not use the app; any report or task action during it is reported.
            d["app_actions_in_current_arm"] = sum(
                1 for e in sb.audit.entries[d.get("audit_from") or 0:]
                if e["role"] in PARTICIPANT_ROLES and e["decision"] == "allowed"
                and e["action"].startswith(("report.", "task.", "checkin.", "emergency.")))
        self._close_task(sb, d, "drill ended")
        sb.freeze()
        sb.audit.append(at=sb.now(), actor=self.created_by, role="auditor", action="drill.ended",
                        resource=d["id"], category="security", detail={"by": by})
        return d

    def abandon(self, sb, drill_id: str, reason: str) -> dict[str, Any]:
        d = self.get(drill_id)
        if d["state"] not in ("running", "planned"):
            raise DrillError("state", "Only a planned or running drill can be stopped.")
        if not reason or len(reason.strip()) < 4:
            raise DrillError("reason", "Say briefly why the drill was stopped.", 422)
        if d["state"] == "running":
            self._close_task(sb, d, "drill stopped")
            sb.freeze()
            d["ended_at"] = clock.wall_iso()
        d.update(state="abandoned", abandon_reason=reason.strip()[:200])
        return d

    def _close_task(self, sb, d: dict[str, Any], reason: str) -> None:
        """A drill's task is closed when the drill ends, so the next drill starts from a clean site."""
        if d["task"] and d["task"] in sb.ledger.tasks:
            sb.ledger.close_rehearsal(d["task"], at=sb.now(), reason=reason)

    def auto_end(self, sb) -> None:
        d = self.running()
        if d and (clock.wall() - _dt(d["started_at"]).timestamp()) / 60 > CAP_MIN:
            self.end(sb, d["id"], notes=(d["notes"] + " Ended automatically at the time cap.").strip(),
                     by="time_cap")

    def link_task(self, task: dict[str, Any]) -> str | None:
        """Called when a worker report creates a task: the running Bardan drill claims it (same control)."""
        d = self.running()
        if d and d["arm"] == "bardan" and task["action_code"] == d["control"] and d["task"] is None:
            d["task"] = task["id"]
            return d["id"]
        return None

    def drill_for_task(self, task_id: str | None) -> dict[str, Any] | None:
        return next((d for d in self.drills if task_id and d["task"] == task_id), None)

    # ---------------------------------------------------------------- results
    def system_marks(self, sb, d: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], int]:
        """Moments the ledger recorded for the drill's task, in real time (Bardan arm), and how many independent
        confirmations came more than a minute before the observer saw the control back."""
        if d["arm"] != "bardan" or not d["task"] or d["task"] not in sb.ledger.tasks or not d["scene_started_at"]:
            return {}, 0
        t = sb.ledger.tasks[d["task"]]
        s0, w0 = _dt(d["scene_started_at"]), _dt(d["started_at"])

        def real(at: str) -> str:
            return (w0 + (_dt(at) - s0)).isoformat()

        events = [e for e in sb.ledger.events if e["task"] == t["id"]]
        first = lambda kinds: next((e for e in events if e["kind"] in kinds), None)  # noqa: E731
        out: dict[str, dict[str, Any]] = {"reported": {"at": real(t["created_at"]), "source": "system"}}
        e = first({"in_progress"}) or first({"reported_complete"})
        if e:
            out["fix_started"] = {"at": real(e["at"]), "source": "system"}
        e = first({"reported_complete"})
        if e:
            out["reported_fixed"] = {"at": real(e["at"]), "source": "system"}
        # Independent means: by someone who had not worked on the fix themselves by then.
        fix_steps = [x for x in events if x["kind"] in ("in_progress", "reported_complete")]
        confirms = [(ev, real(ev["received_at"])) for ev in t["evidence"]
                    if ev["kind"] in CONFIRMING_KINDS
                    and not any(x["actor_ref"] == ev["actor_ref"] and _dt(x["at"]) <= _dt(ev["received_at"])
                                for x in fix_steps)]
        restored = (d["marks"].get("restored_seen") or {}).get("at")
        floor = _dt(restored) - timedelta(seconds=TOLERANCE_S) if restored else None
        early = [x for x in confirms if floor is not None and _dt(x[1]) < floor]
        later = [x for x in confirms if floor is None or _dt(x[1]) >= floor]
        if later:
            ev, at = later[0]
            out["independent_check"] = {"at": at, "source": "system", "kind": ev["kind"], "role": ev["actor_role"]}
        e = first({"disputed_raised"})
        if e:
            out["false_report_caught"] = {"at": real(e["at"]), "source": "system"}
        return out, len(early)

    def feed(self, sb, d: dict[str, Any]) -> list[dict[str, Any]]:
        """The ledger events of the drill's task, minutes after the start (Bardan arm)."""
        if d["arm"] != "bardan" or not d["task"] or not d["scene_started_at"]:
            return []
        s0 = d["scene_started_at"]
        t = sb.ledger.tasks.get(d["task"]) or {}
        reported_by_worker = str(t.get("source", "")).startswith("worker_report")
        return [{"kind": e["kind"], "minute": _minutes(s0, e["at"]),
                 "role": "worker" if e["kind"] == "created" and reported_by_worker else e["actor_role"]}
                for e in sb.ledger.events if e["task"] == d["task"]]

    def effective(self, sb, d: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], int]:
        sysm, early = self.system_marks(sb, d)
        out = {k: v for k, v in sysm.items() if k not in OBSERVER_ONLY}
        out.update(d["marks"])                       # the observer's mark wins
        return out, early

    def outcome(self, sb, d: dict[str, Any]) -> dict[str, Any]:
        marks, early = self.effective(sb, d)
        return outcome_from(marks, started_at=d["started_at"], deadline_min=d["deadline_min"], probe=d["probe"],
                            early_confirmations=early)

    def drill_view(self, sb, d: dict[str, Any], *, facilitator: bool) -> dict[str, Any]:
        v = {k: d[k] for k in ("id", "index", "arm", "scenario", "zone", "control", "deadline_min", "state",
                               "started_at", "ended_at", "notes", "abandon_reason", "app_actions_in_current_arm",
                               "ended_by", "task")}
        if facilitator:
            # Sealed until it is the next drill: the facilitator then needs it to brief the fixer in private.
            nxt = self.next_planned()
            v["probe"] = d["probe"] if d["state"] != "planned" or (nxt and nxt["id"] == d["id"]) else None
            sysm, early = self.system_marks(sb, d)
            eff, _ = self.effective(sb, d)
            v.update(marks=d["marks"], system_marks=sysm, effective_marks=eff, early_confirmations=early,
                     feed=self.feed(sb, d), outcome=self.outcome(sb, d) if d["state"] == "ended" else None)
            if d["state"] == "running":
                v["elapsed_s"] = int(clock.wall() - _dt(d["started_at"]).timestamp())
        return v

    def summary(self, sb) -> dict[str, Any]:
        rows = []
        for d in self.drills:
            r = {k: d[k] for k in ("arm", "state", "probe", "started_at", "app_actions_in_current_arm")}
            r["outcome"] = self.outcome(sb, d) if d["state"] == "ended" else None
            rows.append(r)
        return summary_from(rows, self.deadline_min)

    def view(self, sb, *, facilitator: bool) -> dict[str, Any]:
        out = {"id": self.id, "label": self.label, "scenario": self.scenario, "per_arm": self.per_arm,
               "deadline_min": self.deadline_min, "setting": self.setting, "people": self.people,
               "languages": self.languages, "created_at": self.created_at, "locked": self.locked,
               "running": (self.running() or {}).get("id"),
               "drills": [self.drill_view(sb, d, facilitator=facilitator) for d in self.drills]}
        if facilitator:
            out["summary"] = self.summary(sb)
            out["definitions"] = DEFINITIONS
        return out

    def public_state(self) -> dict[str, Any]:
        """What every participant's screen may know: whether a drill runs and which way of working it uses."""
        d = self.running()
        return {"series": self.id, "running": bool(d), "arm": d["arm"] if d else None,
                "index": d["index"] if d else None}

    def export(self, sb, *, app_version: str, policy_version: str) -> dict[str, Any]:
        drills = []
        for d in self.drills:
            x = self.drill_view(sb, d, facilitator=True)
            x["probe"] = d["probe"]
            x.pop("elapsed_s", None)
            drills.append(x)
        body = {"schema": SCHEMA, "exported_at": clock.wall_iso(), "app_version": app_version,
                "policy_version": policy_version,
                "series": {k: getattr(self, k) for k in ("id", "label", "scenario", "per_arm", "deadline_min",
                                                          "setting", "people", "languages", "created_at")},
                "definitions": DEFINITIONS, "drills": drills,
                "summary": summary_from(drills, self.deadline_min)}
        body["sha256"] = _digest(body)
        return body


# ------------------------------------------------------------------------------------------- published results
def published_path() -> Path:
    from .policy import shared_dir
    return shared_dir() / "drills" / "published.json"


def load_published() -> dict[str, Any]:
    """Drill results published with this release. Each export is re-checked (hash, results recomputed from the
    recorded moments); a problem is shown, never hidden."""
    p = published_path()
    if not p.exists():
        return {"series": [], "note": "No observed drills published yet."}
    data = json.loads(p.read_text(encoding="utf-8"))
    out = []
    for s in data.get("series", []):
        problems = check_export(s)
        out.append({**s, "integrity": "verified" if not problems else "problem", "problems": problems})
    return {"series": out, "note": data.get("note", "")}
