"""Protection ledger: tasks, evidence tiers, disputes, escalation and reports (T23-T33, T56, T64, T65)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.core import reporting
from app.core.ledger import Ledger, LedgerError

T0 = "2025-08-19T09:45:00+04:00"


def later(minutes: int, base: str = T0) -> str:
    return (datetime.fromisoformat(base) + timedelta(minutes=minutes)).isoformat()


@pytest.fixture
def ledger() -> Ledger:
    return Ledger()


def water_task(ledger: Ledger) -> dict:
    return ledger.create(action_code="WATER_RESTORE", zone="A", now=T0, rationale="Water point reported empty",
                         source="worker_report:icon")


@pytest.mark.tcase("T23")
def test_photo_evidence_never_changes_a_heat_value(site):
    """A photo that 'looks shaded' is evidence for a task only; it never changes any reading or band."""
    site.scene("harsh")
    before = {z["id"]: (z["reading"]["value"], z["band"]) for z in site.sup.get("/v1/sites/site_demo/operations")
              .json()["zones"]}
    t = site.sb.ledger.create(action_code="SHADE_EXTEND", zone="A", now=site.sb.now(), rationale="test",
                              source="test")
    r = site.sup.post(f"/v1/tasks/{t['id']}/events", {"action": "add_evidence", "evidence": {
        "kind": "photo", "in_app": True, "zone": "A", "observed_at": site.sb.now(), "scope": "Looks shaded now"}})
    assert r.status_code == 200
    after = {z["id"]: (z["reading"]["value"], z["band"]) for z in site.sup.get("/v1/sites/site_demo/operations")
             .json()["zones"]}
    assert before == after


@pytest.mark.tcase("T26")
@pytest.mark.parametrize("ev", [
    {"kind": "photo", "in_app": True, "zone": "A", "observed_at": "2025-08-19T08:00:00+04:00"},   # old
    {"kind": "photo", "in_app": False, "zone": "A", "observed_at": T0},                           # gallery
    {"kind": "photo", "in_app": True, "zone": "C", "observed_at": T0},                            # other zone
])
def test_old_or_unrelated_photo_is_not_current_evidence(ledger, ev):
    """An old photo, a gallery photo or a photo from another zone is refused as current evidence."""
    t = water_task(ledger)
    with pytest.raises(LedgerError) as e:
        ledger.add_evidence(t["id"], ev, actor="S01", role="supervisor", at=later(5))
    assert e.value.code == "evidence_not_current"


@pytest.mark.tcase("T27")
def test_worker_dispute_reopens_escalates_and_hides_the_disputer(site):
    """A worker disputes a completed protection: it escalates to HSE; the supervisor never sees who."""
    site.scene("start")
    ravi = site.as_("ravi")
    task = ravi.post("/v1/worker/reports", {"intent": "RESOURCE_WATER_UNAVAILABLE"}).json()["task"]
    sup = site.sup
    for action in ("accept", "start", "report_complete"):
        assert sup.post(f"/v1/tasks/{task['id']}/events", {"action": action}).status_code == 200
    d = ravi.post(f"/v1/worker/tasks/{task['id']}/dispute", {"text": "No water came"})
    assert d.status_code == 200
    seen_by_sup = next(t for t in sup.get("/v1/tasks").json()["tasks"] if t["id"] == task["id"])
    assert seen_by_sup["state"] == "escalated" and seen_by_sup["owner_role"] == "hse"
    assert all("raised_by_ref" not in x for x in seen_by_sup["disputes"])
    assert "W01" not in str(seen_by_sup["disputes"]) and "reporter_ref" not in seen_by_sup
    hse_view = next(t for t in site.as_("sara").get("/v1/tasks").json()["tasks"] if t["id"] == task["id"])
    assert hse_view["disputes"][0]["raised_by_ref"] == "W01"
    # The supervisor cannot take the escalated task back.
    r = sup.post(f"/v1/tasks/{task['id']}/events", {"action": "accept"})
    assert r.status_code == 403


@pytest.mark.tcase("T28")
def test_task_cannot_be_closed_without_evidence(site):
    """Verification without the required evidence tier is refused by the API (and the ledger)."""
    site.scene("start")
    t = site.as_("ravi").post("/v1/worker/reports", {"intent": "RESOURCE_COOLING_BROKEN"}).json()["task"]
    for action in ("accept", "start", "report_complete"):
        site.sup.post(f"/v1/tasks/{t['id']}/events", {"action": action})
    r = site.sup.post(f"/v1/tasks/{t['id']}/events", {"action": "verify"})
    assert r.status_code == 422 and "tier" in r.json()["detail"]
    denied = [e for e in site.sb.audit.entries if e["resource"] == t["id"] and e["decision"] == "denied"]
    assert denied and denied[-1]["reason"] == "evidence_tier"


@pytest.mark.tcase("T29")
def test_mandatory_protection_cannot_be_cancelled(ledger):
    """Cancelling a mandatory protection (to improve the statistics) is refused, even by HSE."""
    t = water_task(ledger)
    with pytest.raises(LedgerError) as e:
        ledger.transition(t["id"], "cancelled", actor="S02", role="hse", at=later(1), reason="tidy the numbers")
    assert e.value.code == "mandatory_protection"
    with pytest.raises(LedgerError):
        ledger.transition(t["id"], "cancelled", actor="S01", role="supervisor", at=later(1), reason="x")


@pytest.mark.tcase("T30")
def test_delivery_and_verification_times_are_separate(ledger):
    """Protection started on time and verified later is on time; verification time is recorded separately."""
    t = water_task(ledger)
    ledger.transition(t["id"], "accepted", actor="S01", role="supervisor", at=later(3))
    ledger.transition(t["id"], "in_progress", actor="S01", role="supervisor", at=later(5))
    ledger.transition(t["id"], "reported_complete", actor="S01", role="supervisor", at=later(12))
    ledger.add_evidence(t["id"], {"kind": "independent_spot_check", "observed_at": later(80)}, actor="S02",
                        role="hse", at=later(80))
    ledger.transition(t["id"], "verified", actor="S02", role="hse", at=later(81))
    pub = ledger.public(ledger.get(t["id"]), "hse")
    assert pub["performed_start"] == later(5) and pub["verified_at"] == later(81)
    assert pub["on_time"] is True


@pytest.mark.tcase("T31")
def test_break_cut_short_is_not_counted_as_delivered(site):
    """Breaks cut short never count as delivered protection in the compliance pack."""
    from app.core.history import history
    for d in history()["days"]:
        for c in d["crews"].values():
            assert c["breaks_delivered_full"] + c["breaks_cut_short"] <= c["breaks_required"]
    comp = site.as_("sara").get("/v1/sites/site_demo/compliance").json()
    for crew, b in comp["breaks_last_7_days"].items():
        rate = next((r for r in comp["rates"] if r["name"] == f"breaks_delivered_full:{crew}"), None)
        if not b["required"]:
            assert rate is None          # no 0/0 rates
            continue
        assert rate["numerator"] == b["delivered_full"] and rate["denominator"] == b["required"]


@pytest.mark.tcase("T56")
def test_unreachable_escalation_owner_leaves_notice_pending_and_reminds_locally(site):
    """The HSE lead is unreachable: the escalation notice is queued (never shown as sent) and the supervisor
    gets a local reminder to keep the protection in place."""
    sup = site.sup
    sup.post("/v1/sandbox/settings", {"offline_roles": ["hse"]})
    site.scene("start")
    t = site.as_("ravi").post("/v1/worker/reports", {"intent": "RESOURCE_SHADE_FULL"}).json()["task"]
    sup.post(f"/v1/tasks/{t['id']}/events", {"action": "accept"})
    r = sup.post(f"/v1/tasks/{t['id']}/events", {"action": "escalate", "reason": "need more seats"})
    assert r.status_code == 200
    notes = [n for n in site.sb.ledger.notifications if n["task"] == t["id"]]
    esc = next(n for n in notes if n["template"] == "msg.escalation")
    assert esc["state"] == "queued" and esc["delivered_at"] is None
    rem = next(n for n in notes if n["template"] == "msg.escalation_pending")
    assert rem["to_role"] == "supervisor" and rem["state"] == "delivered"


def test_escalation_after_deadline_and_role_rules(ledger):
    """An unaccepted task escalates after its start-by deadline; workers can never close tasks."""
    t = ledger.create(action_code="COOLING_FIX", zone="A", now=T0, rationale="fan broken", source="test")
    assert ledger.tick(later(10)) == []
    assert ledger.tick(later(31)) == [t["id"]] and ledger.get(t["id"])["state"] == "escalated"
    t2 = water_task(ledger)
    with pytest.raises(LedgerError):
        ledger.transition(t2["id"], "accepted", actor="W01", role="worker", at=later(1))


def test_supervisor_attestation_with_photo_is_not_upgraded(ledger):
    """A supervisor's assertion stays E2 even with a photo attached; E4 needs someone outside their line."""
    t = water_task(ledger)
    ledger.add_evidence(t["id"], {"kind": "supervisor_attestation", "with_photo": True}, actor="S01",
                        role="supervisor", at=later(5))
    assert ledger.get(t["id"])["achieved_tier"] == "E2"
    with pytest.raises(LedgerError) as e:
        ledger.add_evidence(t["id"], {"kind": "independent_spot_check"}, actor="S01", role="supervisor",
                            at=later(6))
    assert e.value.code == "independence"


@pytest.mark.tcase("T64")
def test_report_that_hides_rejected_readings_fails_validation(site):
    """A metrics report that omits failed alerts or rejected readings fails validation."""
    site.as_("sara").post("/v1/observations", {"zone": "A", "kind": "twl", "value": 140, "unit": "C",
                                               "observed_at": site.sb.now()})
    comp = site.as_("sara").get("/v1/sites/site_demo/compliance").json()
    assert comp["validation"]["valid"] is True
    assert comp["exclusions"]["rejected_readings"] >= 1
    hidden = {**comp}
    hidden.pop("exclusions")
    v = reporting.validate(hidden)
    assert v["valid"] is False and v["problems"][0]["check"] == "exclusions_disclosed"


@pytest.mark.tcase("T65")
def test_completion_rate_that_merges_tiers_fails_validation(site):
    """A completion rate that merges E2 and E4 evidence fails validation."""
    comp = site.as_("sara").get("/v1/sites/site_demo/compliance").json()
    merged = {**comp, "verified_by_tier": {"E2+E4": 7}}
    assert reporting.validate(merged)["valid"] is False
    mixed = {**comp, "rates": [{"name": "protection_completed", "numerator": 9, "denominator": 10,
                                "tiers": ["E2", "E4"]}]}
    v = reporting.validate(mixed)
    assert v["valid"] is False and any(p["check"] == "tiers_separate" for p in v["problems"])


# ---------------------------------------------- dispute scope and audited resolution (external review, Nov 2026)
def _water_dispute(site):
    """Water runs out in Zone A; the supervisor reports it fixed; Ravi (crew C2, Zone A) says it didn't happen."""
    site.scene("start")
    ravi = site.as_("ravi")
    task = ravi.post("/v1/worker/reports", {"intent": "RESOURCE_WATER_UNAVAILABLE"}).json()["task"]
    for action in ("accept", "start", "report_complete"):
        assert site.sup.post(f"/v1/tasks/{task['id']}/events", {"action": action}).status_code == 200
    assert ravi.post(f"/v1/worker/tasks/{task['id']}/dispute", {"text": "The cooler is still empty"}).status_code == 200
    return task, ravi, site.as_("sara")


@pytest.mark.tcase("T27")
def test_a_worker_can_only_dispute_a_protection_they_are_shown(site):
    """Ravi works in Zone A: a Zone C task is 'not found' to him and cannot be disputed or confirmed."""
    site.scene("start")
    t = site.sb.ledger.create(action_code="SHADE_EXTEND", zone="C", now=site.sb.now(), rationale="test", source="test",
                              crew="C3")
    for action in ("accept", "start"):
        site.sup.post(f"/v1/tasks/{t['id']}/events", {"action": action})
    ravi = site.as_("ravi")
    assert ravi.post(f"/v1/worker/tasks/{t['id']}/dispute", {"text": "no"}).status_code == 404
    assert ravi.post(f"/v1/worker/tasks/{t['id']}/confirm").status_code == 404
    assert site.sb.ledger.get(t["id"])["open_disputes"] == 0
    # Another worker's personal move to shade is not open to a colleague either.
    p = site.sb.ledger.create(action_code="MOVE_TO_SHADED_TASK", zone="A", now=site.sb.now(), rationale="test",
                              source="test", crew="C2", affected=["W05"])
    site.sup.post(f"/v1/tasks/{p['id']}/events", {"action": "accept"})
    assert ravi.post(f"/v1/worker/tasks/{p['id']}/dispute", {"text": "no"}).status_code == 404


@pytest.mark.tcase("T27")
def test_hse_resolves_a_dispute_with_a_fresh_independent_check_and_the_worker_can_challenge_again(site):
    """When the worker is not there to confirm, HSE resolves the dispute with its own check, in writing; the
    worker is told and keeps the right to say 'this didn't happen' again."""
    task, ravi, sara = _water_dispute(site)
    tid = task["id"]
    assert sara.post(f"/v1/tasks/{tid}/events", {"action": "accept"}).status_code == 200
    # Resolving needs a check made after the dispute, and a written finding.
    r = sara.post(f"/v1/tasks/{tid}/events", {"action": "resolve_dispute", "reason": "Checked the cooler: full"})
    assert r.status_code == 422 and "after the worker raised it" in r.json()["detail"]
    ev = {"kind": "independent_spot_check", "scope": "Cooler refilled and checked at the water point"}
    assert sara.post(f"/v1/tasks/{tid}/events", {"action": "add_evidence", "evidence": ev}).status_code == 200
    assert sara.post(f"/v1/tasks/{tid}/events", {"action": "resolve_dispute", "reason": "ok"}).status_code == 422
    for action in ("start", "report_complete"):
        assert sara.post(f"/v1/tasks/{tid}/events", {"action": action}).status_code == 200, action
    # Verification is still refused while the dispute is open.
    r = sara.post(f"/v1/tasks/{tid}/events", {"action": "verify"})
    assert r.status_code == 422 and "dispute" in r.json()["detail"]
    r = sara.post(f"/v1/tasks/{tid}/events", {"action": "resolve_dispute",
                                              "reason": "Cooler refilled; I checked it myself at the water point"})
    assert r.status_code == 200 and r.json()["task"]["open_disputes"] == 0
    assert sara.post(f"/v1/tasks/{tid}/events", {"action": "verify"}).status_code == 200
    d = site.sb.ledger.get(tid)["disputes"][0]
    assert d["resolved_by"] == "independent_check" and d["worker_can_challenge_again"] is True
    assert any(e["action"] == "task.resolve_dispute" for e in site.sb.audit.entries)
    # Ravi is told what was checked, in his language, and can still challenge.
    notes = ravi.get("/v1/worker/today").json()["notifications"]
    assert any("checked" in n["text"] and "didn’t happen" in n["text"] for n in notes)
    again = ravi.post(f"/v1/worker/tasks/{tid}/dispute", {"text": "Still empty"})
    assert again.status_code == 200 and site.sb.ledger.get(tid)["state"] != "verified"


@pytest.mark.tcase("T27")
def test_only_someone_outside_the_supervisors_line_can_resolve_a_dispute(site):
    """The supervisor whose completion was disputed cannot close the dispute."""
    task, _, _ = _water_dispute(site)
    r = site.sup.post(f"/v1/tasks/{task['id']}/events", {"action": "resolve_dispute",
                                                         "reason": "I am sure the water was delivered"})
    assert r.status_code == 403
    assert site.sb.ledger.get(task["id"])["open_disputes"] == 1


@pytest.mark.tcase("T27")
def test_the_worker_can_close_their_own_dispute_once_the_water_is_back(site):
    """The other path: HSE refills and checks, the worker confirms, and the task can be verified."""
    task, ravi, sara = _water_dispute(site)
    tid = task["id"]
    sara.post(f"/v1/tasks/{tid}/events", {"action": "accept"})
    assert ravi.post(f"/v1/worker/tasks/{tid}/confirm").status_code == 422      # still empty: refused
    sara.post(f"/v1/tasks/{tid}/events", {"action": "add_evidence",
                                          "evidence": {"kind": "independent_spot_check", "scope": "Refilled"}})
    assert ravi.post(f"/v1/worker/tasks/{tid}/confirm").status_code == 200
    for action in ("start", "report_complete", "verify"):
        assert sara.post(f"/v1/tasks/{tid}/events", {"action": action}).status_code == 200, action


@pytest.mark.tcase("T54")
def test_a_retried_task_action_is_answered_once_not_done_twice(site):
    """A dropped connection makes the phone send the same action again: the server answers from the first result."""
    task = site.as_("ravi").post("/v1/worker/reports", {"intent": "RESOURCE_WATER_UNAVAILABLE"}).json()["task"]
    h = {"Idempotency-Key": "accept-1"}
    r1 = site.sup.post(f"/v1/tasks/{task['id']}/events", {"action": "accept"}, headers=h)
    r2 = site.sup.post(f"/v1/tasks/{task['id']}/events", {"action": "accept"}, headers=h)
    assert r1.status_code == r2.status_code == 200 and r2.json()["idempotent_replay"] is True
    assert sum(1 for e in site.sb.ledger.tasks[task["id"]]["history"] if e["kind"] == "accepted") == 1
    # Without the key, a second accept is refused as an invalid transition, as before.
    assert site.sup.post(f"/v1/tasks/{task['id']}/events", {"action": "accept"}).status_code == 409
    # A retried dispute is one dispute, not two.
    site.sup.post(f"/v1/tasks/{task['id']}/events", {"action": "start"})
    site.sup.post(f"/v1/tasks/{task['id']}/events", {"action": "report_complete",
                                                   "evidence": {"kind": "supervisor_attestation"}})
    w = site.as_("ravi")
    for _ in range(2):
        assert w.post(f"/v1/worker/tasks/{task['id']}/dispute", {"text": "No water"},
                      headers={"Idempotency-Key": "d-1"}).status_code == 200
    assert len(site.sb.ledger.tasks[task["id"]]["disputes"]) == 1
