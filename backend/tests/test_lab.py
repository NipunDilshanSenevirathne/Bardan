"""Scenario Lab, shift simulator, break planner and the optional wearable (programme feedback, November 2026)."""
from __future__ import annotations

import copy

import pytest

from app.planner import lab, workrest
from app.planner.twin import REST_MIN, SLOTS, hhmm_to_slot


def preset(pid: str = "summer_site") -> dict:
    return copy.deepcopy(next(p for p in lab.presets() if p["id"] == pid))


def task_net_quarters(plan: dict, task_id: str) -> int:
    t = next(x for x in plan["tasks"] if x["id"] == task_id)
    rest = sum(b["quarters"] for b in plan["breaks"] if b["crew"] == task_id)
    return 2 * len(t["slots"]) - rest


# ------------------------------------------------------------------ break planner (ISO 7243 / NIOSH)
def test_limits_follow_the_published_equations():
    """The one-hour limits are the ISO 7243 / NIOSH REL and RAL equations at the standard metabolic rates."""
    assert workrest.limit_wbgt(300, True) == pytest.approx(28.21, abs=0.01)
    assert workrest.limit_wbgt(415, True) == pytest.approx(26.59, abs=0.01)
    assert workrest.limit_wbgt(180, True) == pytest.approx(30.76, abs=0.01)
    assert workrest.limit_wbgt(300, False) == pytest.approx(24.97, abs=0.01)
    assert workrest.limit_wbgt(115, True) == pytest.approx(33.0, abs=0.01)
    # Outside the valid range the rate is clamped to 115-520 W, never extrapolated.
    assert workrest.limit_wbgt(60, True) == workrest.limit_wbgt(115, True)
    assert workrest.limit_wbgt(900, False) == workrest.limit_wbgt(520, False)


@pytest.mark.parametrize("workload, wbgt, rest_min", [
    ("moderate", 28.0, 0),     # ACGIH TLV table: moderate, 75-100% work at 28.0
    ("moderate", 29.0, 15),    # 50-75% work at 29.0
    ("moderate", 30.0, 30),    # 25-50% work at 30.0
    ("light", 30.5, 0),        # light, 75-100% work up to 31.0
    ("heavy", 27.0, 15),       # heavy has no continuous limit above 26.6
])
def test_rest_agrees_with_the_acgih_screening_table(workload, wbgt, rest_min):
    """Same WBGT at work and rest, no walking: the rest found matches the ACGIH screening table's row."""
    r = workrest.rest_needed(wbgt, wbgt, workload, True, walk_each_way_min=0)
    assert r["workable"] and r["rest_min"] == rest_min


def test_rest_never_decreases_when_work_gets_harder():
    """Hotter, heavier, warmer clothing, a longer walk or a worker not yet acclimatized never needs less rest."""
    def rest(**kw):
        a = dict(wbgt_work=29.0, wbgt_rest=27.0, workload="moderate", acclimatized=True, clothing="work_clothes",
                 walk_each_way_min=3)
        a.update(kw)
        r = workrest.rest_needed(**a)
        return r["rest_min"] if r["workable"] else 60
    base = rest()
    for w in (29.5, 30.5, 31.5):
        assert rest(wbgt_work=w) >= base
    assert rest(workload="heavy") >= base >= rest(workload="light")
    assert rest(clothing="double_layer") >= rest(clothing="coveralls") >= base
    assert rest(walk_each_way_min=8) >= base
    for w in (26.0, 28.0, 30.0, 32.0):
        assert rest(wbgt_work=w, acclimatized=False) >= rest(wbgt_work=w)


def test_a_cooled_rest_area_gives_back_working_time():
    """Heavy work at WBGT 30 in the sun: a shade tent at 27 needs 45 minutes of rest an hour, a cooled cabin 30."""
    tent = workrest.rest_needed(30.0, 27.0, "heavy", True, walk_each_way_min=3)
    cabin = workrest.rest_needed(30.0, 19.5, "heavy", True, walk_each_way_min=3)
    assert tent["rest_min"] == 45 and cabin["rest_min"] == 30


def test_work_that_no_break_can_protect_is_not_planned():
    r = workrest.rest_needed(33.5, 32.5, "heavy", True, walk_each_way_min=3)
    assert r["workable"] is False and r["work_min"] == 0


def test_the_band_minimum_is_rounded_up_never_down():
    assert [workrest.floor_quarters(REST_MIN[b]) for b in ("unrestricted", "acclimatization", "buffer",
                                                          "withdrawal")] == [0, 1, 1, 3]


# ------------------------------------------------------------------ the lab engine
@pytest.mark.parametrize("pid", ["summer_site", "humid_morning", "autumn_day"])
def test_every_preset_gives_an_independently_rechecked_plan(pid):
    """Each preset is planned by CP-SAT and passes the rule engine's re-check plus the heat-limit re-check."""
    r = lab.run(preset(pid))
    assert r["status"] in ("OPTIMAL", "FEASIBLE")
    assert r["revalidation"]["result"] == "valid" and r["revalidation"]["checks"] > 100
    assert r["label"] == "SIMULATION" and r["synthetic"] is True


def test_working_time_is_counted_net_of_breaks():
    """Breaks are not work: for every task, net working quarters plus deferred quarters equal what was asked."""
    sc = preset()
    r = lab.run(sc)
    for t in sc["tasks"]:
        pt = next(x for x in r["plan"]["tasks"] if x["id"] == t["id"])
        assert task_net_quarters(r["plan"], t["id"]) + pt["deferred_quarters"] == int(t["hours"] * 4)
        if not t["can_wait"]:
            assert pt["deferred_quarters"] == 0


def test_rules_are_never_relaxed_for_productivity():
    """No outdoor sun work in the midday window, no work in the withdrawal band, a break in every hot hour, and
    breaks never straddle two hours."""
    r = lab.run(preset("humid_morning"))
    g = r["grid"]
    zones = {z["id"]: z for z in r["world"]["zones"]}
    for t in r["plan"]["tasks"]:
        z = zones[t["zone"]]
        for s in t["slots"]:
            assert g["zones"][t["zone"]][s]["band"] != "withdrawal"
            if z["outdoor"] and z["direct_sun"]:
                assert not g["midday"][s]
    for b in r["plan"]["breaks"]:
        assert b["start_q"] // 4 == (b["start_q"] + b["quarters"] - 1) // 4
    for row in r["why"]:
        assert row["rest_min"] >= row["floor_min"] or row["worked_min"] == 30


def test_the_usual_fixed_day_breaks_the_limit_in_summer_but_not_in_autumn():
    summer = lab.run(preset("summer_site"))["usual"]
    autumn = lab.run(preset("autumn_day"))["usual"]
    assert summer["crew_hours_over_limit"] > 0 and summer["new_worker_hours_over_limit"] > 0
    assert autumn["crew_hours_over_limit"] == 0 and autumn["new_worker_hours_over_limit"] == 0


def test_a_cool_day_is_not_over_restricted():
    """In November the same site needs no extra rest and nothing waits: protection is not a fixed penalty."""
    m = lab.run(preset("autumn_day"))["metrics"]
    assert m["rest_worker_hours"] == 0 and m["deferred_worker_hours"] == 0


def test_new_and_restricted_workers_are_protected_individually():
    sc = preset()
    r = lab.run(sc)
    a = r["plan"]["assignments"]
    ravi = next(w for w in r["named_workers"] if w["name"] == "Ravi")
    assert len(a["P1"]["heat_slots"]) * 30 <= a["P1"]["allowance_min"]
    t2 = next(t for t in r["plan"]["tasks"] if t["id"] == ravi["crew"])
    for s in a["P1"]["heat_slots"]:
        assert r["grid"]["zones"][t2["zone"]][s]["band"] not in ("buffer", "withdrawal")
    # Khaled has a clinician's shaded-light-duty label on a heavy sun task: no heat work at all.
    assert a["P4"]["heat_slots"] == []
    assert r["revalidation"]["result"] == "valid"


def test_infeasible_work_gets_permitted_remedies_never_a_relaxed_rule():
    sc = preset()
    sc["tasks"][0].update(hours=8, one_piece=True, can_wait=False)
    r = lab.run(sc)
    assert r["status"] == "NO_FEASIBLE_PROTECTED_PLAN" and "plan" not in r
    assert {"midday_window", "withdrawal_band", "heat_limit"} <= set(r["diagnosis"]["never_relaxed"])
    assert any(x["remedy"] == "deferral" for x in r["diagnosis"]["permitted_remedies"])


# ------------------------------------------------------------------ the shift simulator
def run_day(sc, steps):
    r = lab.run(sc)
    plans, events = [r], []
    for at, ev in steps:
        if ev:
            events.append({**ev, "at": at})
        r = lab.run(sc, now=at, previous=plans[-1]["plan"], events=list(events))
        assert r["status"] in ("OPTIMAL", "FEASIBLE"), r.get("diagnosis")
        plans.append(r)
    return plans


def test_the_past_is_frozen_and_changes_apply_only_from_now():
    sc = preset()
    first, after = run_day(sc, [("07:00", {"type": "hotter"})])
    now = hhmm_to_slot("07:00")
    for t0, t1 in zip(first["plan"]["tasks"], after["plan"]["tasks"]):
        assert [s for s in t0["slots"] if s < now] == [s for s in t1["slots"] if s < now]
    b0 = [b for b in first["plan"]["breaks"] if b["start_q"] < 2 * now]
    b1 = [b for b in after["plan"]["breaks"] if b["start_q"] < 2 * now]
    assert b0 == b1
    assert after["revalidation"]["result"] == "valid"
    # Hotter from 07:00: the work spot's planning value rises from then on, never before.
    z = first["plan"]["tasks"][0]["zone"]
    assert all(first["grid"]["zones"][z][s]["wbgt_hi"] == after["grid"]["zones"][z][s]["wbgt_hi"] for s in range(now))
    assert after["grid"]["zones"][z][now]["wbgt_hi"] > first["grid"]["zones"][z][now]["wbgt_hi"]


def test_water_outage_stops_that_task_until_water_is_back():
    sc = preset()
    sc["workers"].append({"id": "P9", "name": "Bilal", "lang": "en", "task": "T2", "status": "acclimatized",
                          "day": 300})
    _, after = run_day(sc, [("06:00", {"type": "water_out", "target": "T2"})])
    t2 = next(t for t in after["plan"]["tasks"] if t["id"] == "T2")
    assert hhmm_to_slot("06:00") not in t2["slots"]
    bilal = next(w for w in after["workers"] if w["id"] == "P9")
    assert bilal["now"]["state"] == "stop" and bilal["now"]["code"] == "water"
    # Ravi, a new worker, gets the stop only if he was at that work spot (heat work) just before.
    ravi = next(w for w in after["workers"] if w["id"] == "P1")
    was_at_spot = hhmm_to_slot("06:00") - 1 in after["plan"]["assignments"]["P1"]["heat_slots"]
    assert (ravi["now"]["code"] == "water") == was_at_spot
    assert after["revalidation"]["result"] == "valid"


def test_air_conditioning_failure_lengthens_the_breaks_that_follow():
    sc = preset()
    sc["tasks"][0]["can_wait"] = True
    base, after = run_day(sc, [("05:30", {"type": "ac_fails", "target": "R1"})])
    before = next(r for r in base["why"] if r["task"] == "T1" and r["hour"] == "05:00")
    later = [r for r in after["why"] if r["task"] in ("T1", "T2") and r["hour"] >= "06:00"]
    assert before["wbgt_rest"] < 21 and later
    for row in later:
        assert row["ac_failed"] is True and row["wbgt_rest"] > 25 and row["rest_min"] >= row["iso_rest_min"] - 30
    assert after["metrics"]["rest_share_pct"] >= base["metrics"]["rest_share_pct"]
    assert after["revalidation"]["result"] == "valid"


def test_a_started_pour_that_cannot_finish_safely_is_never_pushed_through():
    """Cooling fails during a pour that may not wait: no protected plan exists, so Bardan offers the permitted
    remedy (let the rest wait, a planned joint) and keeps the heat limit."""
    sc = preset()
    first = lab.run(sc)
    r = lab.run(sc, now="05:30", previous=first["plan"], events=[{"type": "ac_fails", "at": "05:30",
                                                                    "target": "R1"}])
    assert r["status"] == "NO_FEASIBLE_PROTECTED_PLAN"
    assert [x["remedy"] for x in r["diagnosis"]["permitted_remedies"]] == ["deferral"]
    assert "heat_limit" in r["diagnosis"]["never_relaxed"]


def test_a_wearable_break_and_a_symptom_are_honoured_for_that_worker_only():
    sc = preset()
    plans = run_day(sc, [("06:00", {"type": "wearable", "target": "P2"}), ("06:30", {"type": "symptom",
                                                                                      "target": "P1"})])
    after_wearable, after_symptom = plans[1], plans[2]
    anwar = next(w for w in after_wearable["workers"] if w["id"] == "P2")
    assert anwar["now"]["state"] == "break" and anwar["now"]["code"] == "wearable"
    assert hhmm_to_slot("06:00") not in after_wearable["plan"]["assignments"]["P2"]["heat_slots"]
    # The rest of Anwar's crew keeps its plan: only Anwar rests.
    t1 = next(t for t in after_wearable["plan"]["tasks"] if t["id"] == "T1")
    assert hhmm_to_slot("06:00") in t1["slots"]
    ravi = next(w for w in after_symptom["workers"] if w["id"] == "P1")
    assert ravi["now"]["state"] == "stop" and ravi["now"]["code"] == "symptom"
    assert all(s < hhmm_to_slot("06:30") for s in after_symptom["plan"]["assignments"]["P1"]["heat_slots"])
    assert after_symptom["revalidation"]["result"] == "valid"


def test_changes_report_what_moved_from_now_on():
    sc = preset()
    _, after = run_day(sc, [("06:00", {"type": "water_out", "target": "T2"})])
    names = {c["task"] for c in after["changes"]}
    assert "T2" in names


# ------------------------------------------------------------------ validation and access
def test_a_previous_plan_from_another_scenario_is_refused():
    with pytest.raises(lab.LabError):
        lab.run(preset(), now="08:00", previous={"tasks": [{"id": "ZZ", "slots": [1]}], "breaks": []}, events=[])


@pytest.mark.parametrize("change, fragment", [
    (lambda s: s["workers"].append({"id": "P9", "name": "X", "lang": "en", "task": "T9", "status": "new", "day": 1}),
     "does not exist"),
    (lambda s: s["tasks"][0].update(crew_size=1), "more named workers"),
    (lambda s: s["tasks"][0].update(rest_area="R9"), "rest areas"),
    (lambda s: s["tasks"][0].update(start="06:10"), "half hour"),
])
def test_scenarios_are_checked_with_plain_reasons(change, fragment):
    sc = preset()
    change(sc)
    with pytest.raises(lab.LabError) as e:
        lab.run(sc)
    assert fragment in str(e.value)


def test_lab_api_is_for_staff_and_stores_nothing(site):
    sc = preset()
    r = site.sup.post("/v1/lab/plan", {"scenario": sc})
    assert r.status_code == 200, r.text
    assert r.json()["revalidation"]["result"] == "valid"
    hse = site.as_("sara").post("/v1/lab/plan", {"scenario": sc})
    judge = site.as_("reviewer").post("/v1/lab/plan", {"scenario": sc})
    assert hse.status_code == 200 and judge.status_code == 200
    assert site.as_("ravi").post("/v1/lab/plan", {"scenario": sc}).status_code == 403
    # Only counts reach the audit log; no name the reviewer typed is kept.
    entries = [e for e in site.sb.audit.entries if e["action"] == "lab.plan"]
    assert entries and all("Ravi" not in str(e) and "Anwar" not in str(e) for e in entries)
    assert not hasattr(site.sb, "lab")


def test_lab_api_refuses_unknown_fields_and_oversized_scenarios(site):
    sc = preset()
    sc["workers"][0]["heart_rate"] = 150
    assert site.sup.post("/v1/lab/plan", {"scenario": sc}).status_code == 422
    sc = preset()
    sc["tasks"] = sc["tasks"] * 2
    assert site.sup.post("/v1/lab/plan", {"scenario": sc}).status_code == 422
    r = site.sup.get("/v1/lab/presets")
    assert r.status_code == 200 and len(r.json()["presets"]) == 3 and "do not enter real people" in r.json()["notice"]


def test_simulator_round_trip_through_the_api(site):
    sc = preset()
    first = site.sup.post("/v1/lab/plan", {"scenario": sc}).json()
    r = site.sup.post("/v1/lab/plan", {"scenario": sc, "now": "07:00", "previous": first["plan"],
                                       "events": [{"type": "hotter", "at": "07:00"}]})
    assert r.status_code == 200, r.text
    assert r.json()["now"] == "07:00" and r.json()["revalidation"]["result"] == "valid"


# ------------------------------------------------------------------ optional wearable, worker-controlled
def test_wearable_status_needs_the_workers_own_consent(site):
    ravi = site.as_("ravi")
    before = len(site.sb.ledger.tasks)
    r = ravi.post("/v1/worker/wearable/status", {"status": "needs_break"})
    assert r.status_code == 403 and "nothing was sent" in r.json()["detail"]
    assert len(site.sb.ledger.tasks) == before


def test_shared_status_reaches_the_supervisor_as_words_never_numbers(site):
    ravi = site.as_("ravi")
    assert ravi.post("/v1/consents/events", {"purpose": "wearable_status_share", "action": "grant"}).status_code == 200
    r = ravi.post("/v1/worker/wearable/status", {"status": "needs_break"})
    assert r.status_code == 200, r.text
    task = site.sb.ledger.tasks[r.json()["task"]]
    assert task["action_code"] == "CHECK_WORKER" and task["source"] == "wearable_status"
    seen = site.sup.get("/v1/tasks").json()["tasks"]
    mine = next(t for t in seen if t["id"] == task["id"])
    text = str(mine)
    assert "heart" not in text.lower() or "No heart rate" in text
    assert not any(k in mine for k in ("hr", "heart_rate", "core_temp", "strain"))
    notes = [n for n in site.sb.ledger.notifications if n["to_actor"] == "W01" and n["template"] == "msg.wearable_shared"]
    assert notes


@pytest.mark.parametrize("body", [
    {"status": "needs_break", "heart_rate": 152},
    {"status": "needs_break", "core_temp_est": 38.6},
    {"status": "ok"},
    {"status": "fit_to_work"},
])
def test_no_number_and_no_clearing_status_can_cross_from_the_phone(site, body):
    ravi = site.as_("ravi")
    ravi.post("/v1/consents/events", {"purpose": "wearable_status_share", "action": "grant"})
    assert ravi.post("/v1/worker/wearable/status", body).status_code == 422


def test_withdrawing_wearable_sharing_stops_it_at_once(site):
    ravi = site.as_("ravi")
    ravi.post("/v1/consents/events", {"purpose": "wearable_status_share", "action": "grant"})
    ravi.post("/v1/consents/events", {"purpose": "wearable_status_share", "action": "withdraw"})
    assert ravi.post("/v1/worker/wearable/status", {"status": "needs_break"}).status_code == 403


def test_buddy_check_needs_its_own_consent_and_sends_a_name_only(site):
    ravi = site.as_("ravi")
    ravi.post("/v1/consents/events", {"purpose": "wearable_status_share", "action": "grant"})
    assert ravi.post("/v1/worker/wearable/status", {"status": "check_on_me"}).status_code == 403
    ravi.post("/v1/consents/events", {"purpose": "wearable_buddy_alert", "action": "grant"})
    r = ravi.post("/v1/worker/wearable/status", {"status": "check_on_me"})
    assert r.status_code == 200 and r.json()["notified"] == "buddy"
    n = next(n for n in site.sb.ledger.notifications if n["id"] == r.json()["notification"])
    assert n["to_actor"] == "W07" and n["slots"] == {"name": "Ravi"}


def test_a_repeated_wearable_status_creates_one_task(site):
    ravi = site.as_("ravi")
    ravi.post("/v1/consents/events", {"purpose": "wearable_status_share", "action": "grant"})
    h = {"Idempotency-Key": "wear-1"}
    a = ravi.post("/v1/worker/wearable/status", {"status": "needs_break"}, headers=h).json()
    b = ravi.post("/v1/worker/wearable/status", {"status": "needs_break"}, headers=h).json()
    assert a["task"] == b["task"] and b.get("idempotent_replay") is True


def test_wearable_purposes_are_optional_and_off_by_default(site):
    c = {x["purpose"]: x for x in site.as_("ravi").get("/v1/consents").json()["consents"]}
    for p in ("wearable_status_share", "wearable_buddy_alert"):
        assert c[p]["withdrawable"] is True and c[p]["active"] is False


def test_slots_constant_is_the_planning_grid():
    assert SLOTS == 28 and lab.SLOTS == SLOTS


def test_random_days_of_changes_always_stay_rechecked_valid():
    """A seeded stress run: random weather, tasks and mid-shift changes. Every plan the simulator shows passes
    the independent re-check, and a day that has no protected plan is only resumed by a permitted remedy."""
    import random
    rng = random.Random(7)
    kinds = ["hotter", "humid", "calm", "cloud", "water_out", "ac_fails", "symptom", "wearable"]
    steps = 0
    for _ in range(4):
        sc = preset(rng.choice(["summer_site", "humid_morning", "autumn_day"]))
        sc["weather"].update(peak_c=rng.randint(32, 46), humidity_pct=rng.randint(20, 60))
        for t in sc["tasks"]:
            t.update(hours=rng.choice([1, 2, 3, 4]), workload=rng.choice(["light", "moderate", "heavy"]),
                     exposure=rng.choice(["sun", "partial", "shade", "indoor"]), can_wait=True)
        r = lab.run(sc)
        assert r["revalidation"]["result"] == "valid"
        prev, events, now = r["plan"], [], 0
        while now < 16:
            now += 1
            at = lab.slot_label(now)
            if rng.random() < 0.4:
                k = rng.choice(kinds)
                target = {"water_out": rng.choice(sc["tasks"])["id"], "ac_fails": "R1",
                          "symptom": rng.choice(sc["workers"])["id"],
                          "wearable": rng.choice(sc["workers"])["id"]}.get(k)
                events.append({"type": k, "at": at, "target": target})
            r = lab.run(sc, now=at, previous=prev, events=list(events))
            steps += 1
            if r.get("plan"):
                assert r["revalidation"]["result"] == "valid", r["revalidation"]["violations"][:2]
                prev = r["plan"]
            else:
                assert "heat_limit" in r["diagnosis"]["never_relaxed"]
    assert steps == 64


def test_a_crew_that_stops_at_the_half_hour_still_gets_its_break_on_record():
    """The crew worked 07:00-07:30 with its break planned for later in the hour, then the plan stops it at 07:30:
    it rests straight away in the rest area, the hour keeps a break, and the next step keeps that as history."""
    sc = preset()
    r = lab.run(sc)
    prev = r["plan"]
    for at in ("05:30", "06:00", "06:30", "07:00", "07:30", "08:00"):
        ev = [{"type": "hotter", "at": "07:30"}] if at >= "07:30" else []
        r = lab.run(sc, now=at, previous=prev, events=ev)
        assert r["revalidation"]["result"] == "valid", (at, r["revalidation"]["violations"])
        prev = r["plan"]
