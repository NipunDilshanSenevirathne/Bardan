"""Observed drills (core/drill.py) and the scripted mechanism checks (core/mechanism.py).

The drill clock is real time; these tests move it with ``clock.shift`` instead of sleeping.
"""
from __future__ import annotations

import copy
import json

import pytest

from app.core import clock
from app.core.drill import (ARMS, DrillSeries, check_export, load_published, outcome_from, plan_order,
                            summary_from)
from tests.conftest import Persona


@pytest.fixture(autouse=True)
def _real_clock():
    clock.reset()
    yield
    clock.reset()


class Team:
    """A facilitator (the reviewer persona) with a drill sandbox, and the people taking part in it."""

    def __init__(self, client, **series):
        self.client = client
        self.fac = Persona(client, "reviewer")
        r = self.fac.post("/v1/drills/series", {"per_arm": 2, "probes": True, "people": 4, **series})
        assert r.status_code == 200, r.text
        j = r.json()
        self.sid = j["sandbox_id"]
        self.fac.sid, self.fac.token = j["sandbox_id"], j["token"]
        self.worker = Persona(client, "ravi", self.sid)
        self.sup = Persona(client, "joseph", self.sid)
        self.hse = Persona(client, "sara", self.sid)

    @property
    def sb(self):
        from app.core.sandbox import STORE
        return STORE.peek(self.sid)

    def series(self) -> dict:
        r = self.fac.get("/v1/drills/series")
        assert r.status_code == 200, r.text
        return r.json()

    def start_next(self, arm: str | None = None) -> dict:
        """Start the next planned drill (optionally: the next planned drill of this arm)."""
        s = self.series()
        d = next(x for x in s["drills"] if x["state"] == "planned" and (arm is None or x["arm"] == arm))
        r = self.fac.post("/v1/drills/start", {"drill_id": d["id"]})
        assert r.status_code == 200, r.text
        return next(x for x in r.json()["drills"] if x["id"] == d["id"])

    def mark(self, drill_id: str, mark: str, undo: bool = False):
        r = self.fac.post(f"/v1/drills/{drill_id}/mark", {"mark": mark, "undo": undo})
        assert r.status_code == 200, r.text
        return r.json()

    def end(self, drill_id: str, notes: str = "") -> dict:
        r = self.fac.post(f"/v1/drills/{drill_id}/end", {"notes": notes})
        assert r.status_code == 200, r.text
        return next(x for x in r.json()["drills"] if x["id"] == drill_id)

    def water_task(self) -> dict:
        r = self.worker.post("/v1/worker/reports", {"intent": "RESOURCE_WATER_UNAVAILABLE"})
        assert r.status_code == 200, r.text
        return r.json()["task"]

    def act(self, who: Persona, task_id: str, action: str, evidence: dict | None = None):
        body = {"action": action, **({"evidence": evidence} if evidence else {})}
        r = who.post(f"/v1/tasks/{task_id}/events", body)
        assert r.status_code == 200, r.text
        return r.json()["task"]


def minutes(x, y, tol=0.05):
    return x is not None and abs(x - y) <= tol


# --------------------------------------------------------------------------------------------------- plan
def test_drill_plan_is_counterbalanced_with_one_sealed_false_report_per_way_of_working():
    for per_arm in range(1, 7):
        for first in ARMS:
            order = plan_order(per_arm, first)
            assert len(order) == 2 * per_arm and order.count("current") == order.count("bardan") == per_arm
    assert plan_order(2, "current") == ["current", "bardan", "bardan", "current"]
    s = DrillSeries(label="x", scenario="water_out", per_arm=3, probes=True, deadline_min=None, people=4,
                    setting="role_play", languages=["en", "ar"], created_by="S99", seed=7)
    for arm in ARMS:
        assert sum(d["probe"] for d in s.drills if d["arm"] == arm) == 1
    assert s.deadline_min == 20 and not s.locked


def test_only_the_independent_reviewer_runs_drills_and_participants_learn_only_that_one_runs(client):
    r = Persona(client, "joseph").post("/v1/drills/series", {})
    assert r.status_code == 403
    team = Team(client)
    assert team.worker.get("/v1/drills/series").status_code == 403
    assert team.sup.get("/v1/drills/export").status_code == 403
    planned = team.series()["drills"]
    assert planned[0]["probe"] in (True, False)                 # the next drill: needed for the private briefing
    assert all(d["probe"] is None for d in planned[1:])         # later drills stay sealed
    team.start_next()
    st = team.worker.get("/v1/sandbox/state").json()
    assert st["drill"]["running"] is True and st["drill"]["arm"] in ARMS
    assert set(st["drill"]) == {"series", "running", "arm", "index"} and st["live_clock"] is True


def test_the_scenario_clock_runs_in_real_time_during_a_drill_and_cannot_be_moved_by_hand(client):
    team = Team(client)
    before = team.sb.now()
    team.start_next()
    clock.shift(125)
    now = team.sb.now()
    assert now[:10] == before[:10] and (int(now[11:13]) * 60 + int(now[14:16])) - \
        (int(before[11:13]) * 60 + int(before[14:16])) in (2, 3)
    assert team.sup.post("/v1/sandbox/scene", {"scene": "water"}).status_code == 409
    assert team.sup.post("/v1/sandbox/advance", {"minutes": 30}).status_code == 409
    assert team.sup.post("/v1/sandbox/reset", {}).status_code == 409
    d = team.series()["running"]
    team.end(d)
    frozen = team.sb.now()
    clock.shift(600)
    assert team.sb.now() == frozen                               # frozen again after the drill


# ------------------------------------------------------------------------------------------- bardan arm
def test_bardan_drill_takes_times_from_the_ledger_and_the_observer_records_the_ground_truth(client):
    team = Team(client, probes=False)
    d = team.start_next("bardan")
    clock.shift(30)
    task = team.water_task()
    assert task["drill"] == d["id"]
    clock.shift(90)
    team.act(team.sup, task["id"], "accept")
    team.act(team.sup, task["id"], "start")
    clock.shift(240)
    team.act(team.sup, task["id"], "report_complete", {"kind": "water_point_check", "water_actually_delivered": True})
    team.mark(d["id"], "restored_seen")                          # the observer sees the water back
    clock.shift(60)
    r = team.worker.post(f"/v1/worker/tasks/{task['id']}/confirm")
    assert r.status_code == 200, r.text                          # the worker's word; the observer has the truth
    view = team.end(d["id"])
    o = view["outcome"]
    assert minutes(o["minutes"]["reported"], 0.5) and minutes(o["minutes"]["fix_started"], 2.0)
    assert minutes(o["minutes_to_restored"], 6.0) and minutes(o["minutes_to_verified"], 7.0)
    assert o["verified_by_deadline"] and o["restored_by_deadline"] and not o["false_confirmation"]
    assert o["sources"]["restored_seen"] == "observer" and o["sources"]["independent_check"] == "system"
    assert view["system_marks"]["independent_check"]["kind"] == "worker_confirmation"
    # The drill's task is closed, so the next drill starts from a clean site; its history is kept.
    t = team.sb.ledger.tasks[task["id"]]
    assert t["state"] == "cancelled" and t["history"][-1]["kind"] == "rehearsal_closed"
    assert team.sb.water_status("A") == "available"


def test_an_unanswered_report_escalates_in_real_time_during_a_drill(client):
    team = Team(client, probes=False)
    d = team.start_next("bardan")
    task = team.water_task()
    clock.shift(9 * 60)
    s = team.series()
    assert team.sb.ledger.tasks[task["id"]]["state"] == "assigned"
    clock.shift(2 * 60 + 5)
    s = team.series()                                            # the console's polling runs the timers
    feed = next(x for x in s["drills"] if x["id"] == d["id"])["feed"]
    esc = next(e for e in feed if e["kind"] == "escalated")
    assert 10 <= esc["minute"] <= 11.2 and team.sb.ledger.tasks[task["id"]]["owner_role"] == "hse"


def test_a_false_report_is_caught_by_the_workers_dispute(client):
    team = Team(client, per_arm=1, probes=True)
    d = team.start_next("bardan")
    assert d["probe"] is True                                    # one drill per arm, so this one carries it
    task = team.water_task()
    clock.shift(60)
    team.act(team.sup, task["id"], "accept")
    team.act(team.sup, task["id"], "start")
    clock.shift(60)
    team.act(team.sup, task["id"], "report_complete", {"kind": "supervisor_attestation", "scope": "says refilled"})
    clock.shift(45)
    r = team.worker.post(f"/v1/worker/tasks/{task['id']}/dispute", {"text": "Still no water"})
    assert r.status_code == 200
    clock.shift(4 * 60)                                          # the supervisor really refills it now
    team.mark(d["id"], "restored_seen")
    clock.shift(30)
    team.act(team.hse, task["id"], "add_evidence", {"kind": "independent_spot_check", "scope": "refilled, checked"})
    r = team.hse.post(f"/v1/tasks/{task['id']}/events",
                      {"action": "resolve_dispute", "reason": "Checked the water point myself: refilled"})
    assert r.status_code == 200, r.text
    view = team.end(d["id"])
    o = view["outcome"]
    assert o["false_report_caught"] and o["caught_by_deadline"] and minutes(o["minutes_to_caught"], 2.75)
    assert minutes(o["minutes_to_restored"], 6.75) and minutes(o["minutes_to_verified"], 7.25)
    assert o["verified_by_deadline"] and view["system_marks"]["independent_check"]["role"] == "hse"


def test_the_person_who_fixed_it_cannot_also_be_its_independent_check(client):
    team = Team(client, probes=False)
    d = team.start_next("bardan")
    task = team.water_task()
    team.act(team.hse, task["id"], "accept")
    team.act(team.hse, task["id"], "start")
    clock.shift(120)
    team.mark(d["id"], "restored_seen")
    team.act(team.hse, task["id"], "add_evidence", {"kind": "independent_spot_check", "scope": "my own fix"})
    o = team.end(d["id"])["outcome"]
    assert o["minutes_to_verified"] is None and "independent_check" not in o["minutes"]


def test_a_confirmation_before_the_control_is_really_back_is_not_a_verification(client):
    team = Team(client, probes=False)
    d = team.start_next("bardan")
    task = team.water_task()
    team.act(team.sup, task["id"], "accept")
    clock.shift(60)
    assert team.worker.post(f"/v1/worker/tasks/{task['id']}/confirm").status_code == 200
    clock.shift(5 * 60)
    team.mark(d["id"], "restored_seen")
    o = team.end(d["id"])["outcome"]
    assert o["false_confirmation"] is True and o["minutes_to_verified"] is None and not o["verified_by_deadline"]
    assert minutes(o["minutes_to_restored"], 6.0) and o["restored_by_deadline"]


def test_each_bardan_drill_gets_its_own_task(client):
    team = Team(client, per_arm=2, probes=False)
    d1 = team.start_next("bardan")
    t1 = team.water_task()
    team.end(d1["id"])
    d2 = team.start_next("bardan")
    t2 = team.water_task()
    assert t1["id"] != t2["id"] and t2["drill"] == d2["id"]
    assert team.sb.drills.get(d2["id"])["task"] == t2["id"]


# ------------------------------------------------------------------------------------------ current arm
def test_current_arm_is_measured_by_the_observer_and_app_use_is_reported(client):
    team = Team(client, probes=False)
    d = team.start_next("current")
    clock.shift(60)
    team.mark(d["id"], "reported")
    clock.shift(4 * 60)
    team.mark(d["id"], "fix_started")
    clock.shift(5 * 60)
    team.mark(d["id"], "reported_fixed")
    team.mark(d["id"], "restored_seen")
    team.water_task()                                            # someone used the app anyway
    view = team.end(d["id"], notes="Supervisor walked to the store; nobody checked afterwards.")
    o = view["outcome"]
    assert minutes(o["minutes_to_restored"], 10.0) and o["minutes_to_verified"] is None
    assert o["restored_by_deadline"] and not o["verified_by_deadline"]
    assert view["app_actions_in_current_arm"] == 1
    s = team.series()["summary"]["arms"]["current"]
    assert s["not_verified"] == 1 and s["verified_by_deadline"] == {"k": 0, "n": 1}
    assert s["app_actions_in_current_arm"] == 1


def test_observer_marks_can_be_corrected_but_not_added_after_the_drill(client):
    team = Team(client, probes=False)
    d = team.start_next()
    team.mark(d["id"], "reported")
    team.end(d["id"])
    r = team.fac.post(f"/v1/drills/{d['id']}/mark", {"mark": "restored_seen"})
    assert r.status_code == 409
    j = team.mark(d["id"], "reported", undo=True)
    assert next(x for x in j["drills"] if x["id"] == d["id"])["marks"] == {}


def test_abandoned_drills_need_a_reason_and_are_left_out_of_the_results(client):
    team = Team(client, probes=False)
    d = team.start_next()
    assert team.fac.post(f"/v1/drills/{d['id']}/abandon", {"reason": ""}).status_code == 422
    r = team.fac.post(f"/v1/drills/{d['id']}/abandon", {"reason": "A participant had to leave"})
    assert r.status_code == 200
    arms = r.json()["summary"]["arms"]
    assert arms[d["arm"]]["abandoned"] == 1 and arms[d["arm"]]["drills_run"] == 0
    assert team.sb.live_clock is None


def test_a_forgotten_drill_ends_at_the_time_cap(client):
    team = Team(client, probes=False)
    d = team.start_next()
    clock.shift(61 * 60)
    view = next(x for x in team.series()["drills"] if x["id"] == d["id"])
    assert view["state"] == "ended" and view["ended_by"] == "time_cap"


# --------------------------------------------------------------------------------------- export and publish
def _run_two(team: Team) -> dict:
    for arm in ("current", "bardan"):
        d = team.start_next(arm)
        if arm == "bardan":
            task = team.water_task()
            team.act(team.sup, task["id"], "accept")
            team.act(team.sup, task["id"], "start")
            clock.shift(300)
            team.act(team.sup, task["id"], "report_complete", {"kind": "water_point_check",
                                                               "water_actually_delivered": True})
            team.mark(d["id"], "restored_seen")
            team.worker.post(f"/v1/worker/tasks/{task['id']}/confirm")
        else:
            clock.shift(60)
            team.mark(d["id"], "reported")
            clock.shift(480)
            team.mark(d["id"], "restored_seen")
            team.mark(d["id"], "independent_check")
        team.end(d["id"])
    r = team.fac.get("/v1/drills/export")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    return r.json()


def test_export_is_self_checking_and_tampering_is_detected(client):
    team = Team(client, per_arm=1, probes=False)
    body = _run_two(team)
    assert check_export(body) == []
    assert body["summary"]["arms"]["bardan"]["verified_by_deadline"] == {"k": 1, "n": 1}
    forged = copy.deepcopy(body)
    d = next(x for x in forged["drills"] if x["arm"] == "current")
    d["outcome"]["minutes_to_restored"] = 2.0                    # a nicer number, without the moments behind it
    assert "hash" in check_export(forged) and f"outcome:{d['id']}" in check_export(forged)
    resealed = copy.deepcopy(forged)
    from app.core.drill import _digest
    resealed["sha256"] = _digest(resealed)                       # even with a fresh hash, results must follow
    assert check_export(resealed) == [f"outcome:{d['id']}", "summary"]


def test_published_results_are_rechecked_when_loaded(client, tmp_path, monkeypatch):
    team = Team(client, per_arm=1, probes=False)
    body = _run_two(team)
    shared = tmp_path / "shared"
    (shared / "drills").mkdir(parents=True)
    bad = copy.deepcopy(body)
    bad["drills"][0]["notes"] = "edited after export"
    (shared / "drills" / "published.json").write_text(json.dumps({"note": "x", "series": [body, bad]}))
    monkeypatch.setenv("BARDAN_SHARED_DIR", str(shared))
    pub = load_published()
    assert [s["integrity"] for s in pub["series"]] == ["verified", "problem"]
    assert pub["series"][1]["problems"] == ["hash"]


def test_the_release_ships_with_no_invented_drill_results():
    pub = load_published()
    assert pub["series"] == [] or all(s["integrity"] == "verified" for s in pub["series"])


def test_outcome_and_summary_are_pure_functions_of_the_recorded_moments():
    start = "2026-11-10T09:00:00+00:00"
    marks = {"restored_seen": {"at": "2026-11-10T09:12:00+00:00", "source": "observer"},
             "independent_check": {"at": "2026-11-10T09:11:30+00:00", "source": "observer"}}
    o = outcome_from(marks, started_at=start, deadline_min=20, probe=False)
    assert o["minutes_to_verified"] == 12.0 and not o["false_confirmation"]    # within the one-minute tolerance
    marks["independent_check"]["at"] = "2026-11-10T09:05:00+00:00"
    o2 = outcome_from(marks, started_at=start, deadline_min=20, probe=False)
    assert o2["false_confirmation"] and o2["minutes_to_verified"] is None
    rows = [{"arm": "current", "state": "ended", "probe": False, "started_at": start, "outcome": o,
             "app_actions_in_current_arm": 0},
            {"arm": "bardan", "state": "ended", "probe": False, "started_at": "2026-11-10T09:30:00+00:00",
             "outcome": o2}]
    s = summary_from(rows, 20)
    assert s["arms"]["current"]["minutes_to_verified"]["median"] == 12.0
    assert s["arms"]["bardan"]["false_confirmations"] == 1 and s["order_followed"] is True


# ------------------------------------------------------------------------------------------- lifetime
def test_a_drill_sandbox_in_use_outlives_the_hourly_reset_but_not_four_hours(client):
    import time
    team = Team(client, probes=False)
    sb = team.sb
    sb.created -= 2 * 3600
    sb.last_seen = time.time()
    assert not sb.expired(time.time())
    sb.created -= 3 * 3600
    assert sb.expired(time.time())
    from app.core.sandbox import Sandbox
    plain = Sandbox("sb_plain")
    plain.created -= 3700
    assert plain.expired(time.time())


# -------------------------------------------------------------------------------------- mechanism checks
def test_mechanism_checks_pass_and_can_fail():
    from app.core import mechanism
    r = mechanism.mechanism_checks()
    assert r["passed"] == r["total"] == 7 and all(x["test"] for x in r["rows"])


def test_mechanism_check_fails_when_the_rule_is_broken(monkeypatch):
    """The checks run the real code: if escalation stopped working, the table would say so."""
    from app.core import mechanism
    from app.core.ledger import Ledger
    monkeypatch.setattr(Ledger, "tick", lambda self, now: [])
    ok, _ = mechanism.m1_unanswered()
    assert ok is False


def test_evaluation_report_has_mechanism_checks_and_drills_but_no_simulated_comparison(client):
    ev = client.get("/v1/reports/evaluation").json()
    assert "alert_only" not in ev and ev["mechanism"]["total"] == 7 and "series" in ev["drills"]
