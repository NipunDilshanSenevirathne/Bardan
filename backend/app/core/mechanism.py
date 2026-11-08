"""What each workflow does in the moments that decide whether protection really happens.

Scripted checks of the real code (the same ledger, evidence rules, emergency states and plan re-validation the
app uses), run each time the evaluation report is built. They show what the workflow does, never how much faster
people are: speed and timeliness come only from observed drills (core/drill.py).

The alert-only column describes the comparator by definition (finalsystem.md glossary): the same alerts at the
same thresholds, with no tasks, evidence tiers, disputes, capacity check or acknowledgement step. It is not
measured, and no number is derived from it.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable

from .ledger import Ledger, LedgerError

T0 = "2025-08-19T10:00:00+04:00"


def _at(minutes: float) -> str:
    return (datetime.fromisoformat(T0) + timedelta(minutes=minutes)).isoformat()


def _refused(fn: Callable[[], Any], code: str) -> bool:
    try:
        fn()
    except LedgerError as e:
        return e.code == code
    return False


def _water(L: Ledger) -> dict[str, Any]:
    return L.create(action_code="WATER_RESTORE", zone="A", now=_at(0), rationale="scripted check",
                    source="mechanism_check")


def m1_unanswered() -> tuple[bool, dict[str, Any]]:
    L = Ledger()
    t = _water(L)
    L.tick(_at(t["deadline_min"] - 1))
    before = t["state"]
    L.tick(_at(t["deadline_min"] + 1))
    ok = before == "assigned" and t["state"] == "escalated" and t["owner_role"] == "hse"
    return ok, {"minutes": t["deadline_min"]}


def m2_m3_false_completion() -> tuple[tuple[bool, dict[str, Any]], tuple[bool, dict[str, Any]]]:
    L = Ledger()
    t = _water(L)
    tid = t["id"]
    for i, s in enumerate(("accepted", "in_progress")):
        L.transition(tid, s, actor="S01", role="supervisor", at=_at(1 + i))
    L.transition(tid, "reported_complete", actor="S01", role="supervisor", at=_at(4),
                 evidence={"kind": "supervisor_attestation", "scope": "says refilled"})
    word_only = _refused(lambda: L.transition(tid, "verified", actor="S01", role="supervisor", at=_at(5)),
                         "evidence_tier")
    L.dispute(tid, actor="W01", role="worker", at=_at(6), text="Still no water")
    to_hse = t["state"] == "escalated" and t["owner_role"] == "hse" and t["open_disputes"] == 1
    m2 = (word_only and to_hse, {})
    # M3: closing the dispute
    by_supervisor = _refused(lambda: L.resolve_dispute(tid, actor="S01", role="supervisor", at=_at(7),
                                                       reason="I checked it myself"), "independence")
    no_fresh_check = _refused(lambda: L.resolve_dispute(tid, actor="S02", role="hse", at=_at(8),
                                                        reason="The tank was full this morning"),
                              "evidence_after_dispute")
    L.add_evidence(tid, {"kind": "independent_spot_check", "scope": "HSE checked the water point"}, actor="S02",
                   role="hse", at=_at(12))
    L.resolve_dispute(tid, actor="S02", role="hse", at=_at(12), reason="Checked the water point myself: full")
    told = any(n["template"] == "msg.dispute_resolved" and n["to_actor"] == "W01" for n in L.notifications)
    for i, s in enumerate(("accepted", "in_progress", "reported_complete", "verified")):
        L.transition(tid, s, actor="S02", role="hse", at=_at(13 + i))
    verified = t["state"] == "verified"
    L.dispute(tid, actor="W01", role="worker", at=_at(30), text="Empty again")
    again = t["state"] == "assigned"
    m3 = (by_supervisor and no_fresh_check and told and verified and again, {})
    return m2, m3


def m4_stale_evidence() -> tuple[bool, dict[str, Any]]:
    L = Ledger()
    t = _water(L)
    for i, s in enumerate(("accepted", "in_progress")):
        L.transition(t["id"], s, actor="S01", role="supervisor", at=_at(1 + i))
    add = lambda ev: lambda: L.add_evidence(t["id"], ev, actor="S01", role="supervisor", at=_at(3))  # noqa: E731
    old = _refused(add({"kind": "photo", "observed_at": _at(-45), "zone": "A"}), "evidence_not_current")
    other_zone = _refused(add({"kind": "photo", "observed_at": _at(3), "zone": "B"}), "evidence_not_current")
    gallery = _refused(add({"kind": "photo", "observed_at": _at(3), "zone": "A", "in_app": False}),
                       "evidence_not_current")
    L.add_evidence(t["id"], {"kind": "photo", "observed_at": _at(3), "zone": "A"}, actor="S01", role="supervisor",
                   at=_at(3))
    return old and other_zone and gallery and t["achieved_tier"] == "E3", {"minutes": 30}


def m5_unreachable() -> tuple[bool, dict[str, Any]]:
    L = Ledger()
    L.offline_roles = {"hse"}
    t = _water(L)
    L.tick(_at(t["deadline_min"] + 1))
    esc = next((n for n in L.notifications if n["template"] == "msg.escalation"), None)
    queued = bool(esc) and esc["state"] == "queued" and esc["delivered_at"] is None
    reminder = any(n["template"] == "msg.escalation_pending" and n["to_role"] == "supervisor"
                   for n in L.notifications)
    return queued and reminder, {}


def m6_m7_sandbox() -> tuple[tuple[bool, dict[str, Any]], tuple[bool, dict[str, Any]]]:
    from . import actions
    from .sandbox import Sandbox
    sb = Sandbox("sb_mechanism")
    actions.emergency_event(sb, "W01", {"kind": "card_opened", "event_id": "mech-1", "subject": "W01"})
    rec = sb.emergencies[-1]
    st = actions.emergency_status(sb, rec)
    received_only = bool(st["received_by_server_at"]) and st["acknowledged"] is None
    st2 = actions.acknowledge_emergency(sb, rec["id"], actor="S01", role="supervisor")
    acked = (st2["acknowledged"] or {}).get("role") == "supervisor" and "actor" not in st2["acknowledged"]
    m6 = (received_only and acked, {})
    sc = sb.evaluate_draft("S01 (mechanism check)")
    over = [v for v in sc["revalidation"]["violations"] if v["rule"] == "rest_capacity"]
    try:
        sb.approve_plan(sc["scenario_id"], "S01 (mechanism check)")
        refused = False
    except ValueError:
        refused = True
    m7 = (bool(over) and refused, {"conflicts": len(over)})
    return m6, m7


ROWS = [  # id, the release test that covers the same rule
    ("M1", "test_escalation_after_deadline_and_role_rules"),
    ("M2", "test_worker_dispute_reopens_escalates_and_hides_the_disputer"),
    ("M3", "test_hse_resolves_a_dispute_with_a_fresh_independent_check_and_the_worker_can_challenge_again"),
    ("M4", "test_old_or_unrelated_photo_is_not_current_evidence"),
    ("M5", "test_unreachable_escalation_owner_leaves_notice_pending_and_reminds_locally"),
    ("M6", "test_received_by_the_server_is_not_seen_by_the_site_team_until_a_responder_acknowledges"),
    ("M7", "test_rest_capacity_shortage_gives_no_feasible_plan_with_remedies"),
]


def mechanism_checks() -> dict[str, Any]:
    m2, m3 = m2_m3_false_completion()
    m6, m7 = m6_m7_sandbox()
    results = {"M1": m1_unanswered(), "M2": m2, "M3": m3, "M4": m4_stale_evidence(), "M5": m5_unreachable(),
               "M6": m6, "M7": m7}
    rows = [{"id": rid, "passed": results[rid][0], "slots": results[rid][1], "test": test} for rid, test in ROWS]
    return {"rows": rows, "passed": sum(r["passed"] for r in rows), "total": len(rows),
            "label": "Scripted checks of the real code. They show what each workflow does, not how much faster "
                     "people are. Timeliness comes only from observed drills."}
