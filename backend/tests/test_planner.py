"""Foresee and Plan: forecasts, the Site Heat Twin, CP-SAT plans, re-validation and fairness (T14, T24, T32, T33,
T71-T78)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.forecast import service as fs
from app.planner import fairness
from app.planner.certificate import inject_fault, revalidate


def optimise(site) -> dict:
    r = site.sup.post("/v1/plans/optimise", {})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------------------------- forecast
@pytest.mark.tcase("T71")
def test_forecast_unavailable_uses_the_season_standard_plan(site):
    """Forecast switched off: 'forecast unavailable', the season's standard plan, nothing relaxed."""
    site.sup.post("/v1/sandbox/settings", {"forecast_enabled": False})
    fc = site.sup.get("/v1/sites/site_demo/forecast").json()
    assert fc["available"] is False
    p = optimise(site)
    assert p["status"] == "FORECAST_UNAVAILABLE" and p["forecast_available"] is False
    assert p["fallback"]["relaxes_anything"] is False
    d = site.sup.post("/v1/plans/evaluate").json()
    assert d["forecast_available"] is False and d["fallback"]["relaxes_anything"] is False


@pytest.mark.tcase("T14")
def test_forecast_older_than_24_hours_is_not_used(site):
    """A 30-hour-old forecast is stale: not used for planning; the standard plan applies."""
    site.sb.world["clock"] = "2025-08-20T00:30:00+04:00"
    fc = site.sup.get("/v1/sites/site_demo/forecast").json()
    assert fc["available"] is False and fc["stale"] is True and fc["age_hours"] > 24
    assert optimise(site)["status"] == "FORECAST_UNAVAILABLE"


@pytest.mark.tcase("T72")
def test_live_reading_overrides_a_milder_forecast_and_tightens_the_plan(site):
    """Zone A turns harsher than forecast: the live value governs and the new worker moves to shaded work."""
    fc = fs.scenario_forecast()
    row = next(r for r in fc["zones"]["A"] if r["valid_hour"].startswith("2025-08-19T09"))
    assert row.get("scenario_injection") == "T72" and row["planning_band"] != "buffer"
    site.scene("harsh")
    zone_a = next(z for z in site.sup.get("/v1/sites/site_demo/operations").json()["zones"] if z["id"] == "A")
    assert zone_a["band"] == "buffer"
    st = site.as_("ravi").get("/v1/worker/today").json()["status"]
    assert st["assignment"]["kind"] == "shaded_task" and st["tightened"] is True
    task = next(t for t in site.sb.ledger.tasks.values() if t["action_code"] == "MOVE_TO_SHADED_TASK")
    assert task["source"] == "live_policy_engine" and "Live values govern" in task["rationale"]


def _fake_open_meteo(units: dict, start: datetime | None = None, **vals) -> dict:
    start = start or datetime.now(timezone(timedelta(hours=4))).replace(minute=0, second=0, microsecond=0)
    times = [(start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(1, 25)]
    n = len(times)
    base = {"temperature_2m": 38.0, "relative_humidity_2m": 45.0, "surface_pressure": 1000.0, "wind_speed_10m": 3.0,
            "shortwave_radiation": 600.0, "direct_radiation": 450.0, **vals}
    return {"hourly": {"time": times, **{k: [v] * n for k, v in base.items()}}, "hourly_units": units}


@pytest.mark.tcase("T73")
def test_forecast_in_wrong_units_is_quarantined(monkeypatch):
    """A provider answer in Fahrenheit is refused (quarantined): forecast unavailable, never converted."""
    payload = _fake_open_meteo({"temperature_2m": "°F", "wind_speed_10m": "m/s"}, temperature_2m=100.0)
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=payload))
    real = httpx.Client
    monkeypatch.setattr(fs.httpx, "Client", lambda **kw: real(transport=transport, **kw))
    monkeypatch.setattr(fs, "_LIVE_CACHE", {"at": 0.0, "data": None})
    fc = fs.live_forecast()
    assert fc["available"] is False and "quarantined" in fc["reason"]


@pytest.mark.tcase("T74")
def test_inputs_outside_experience_are_flagged_with_a_wider_interval():
    """Weather far outside anything the method has seen: flagged, physics-only, wider interval."""
    # A fixed summer morning: with "now" the test depended on the hour it ran at, because the fake provider sends
    # the same sunshine at night, which is itself outside experience (it failed after about 15:00 Gulf time).
    now = datetime(2026, 8, 18, 5, 0, tzinfo=timezone(timedelta(hours=4)))
    normal = fs._from_open_meteo(_fake_open_meteo({"temperature_2m": "°C"}, start=now), 24.45, 54.38, now)
    extreme = fs._from_open_meteo(_fake_open_meteo({"temperature_2m": "°C"}, start=now, temperature_2m=55.0,
                                                   relative_humidity_2m=70.0), 24.45, 54.38, now)
    n_row = next(r for r in normal["zones"]["B"] if r["valid_hour"][11:13] == "11")
    assert not n_row.get("flags")
    x_row = next(r for r in extreme["zones"]["B"] if r.get("flags"))
    assert "outside_model_experience" in x_row["flags"] and x_row["estimate"] == "physics_only"
    def width(r):
        return r["wbgt_c_interval_90"][1] - r["wbgt_c_interval_90"][0]

    assert width(x_row) > width(n_row) * 1.4


def test_backtest_reports_coverage_on_held_out_days():
    """The replay forecast's backtest is computed on held-out days and reports interval coverage."""
    from app.forecast.model import backtest
    b = backtest()
    assert "held out" in b["period"]
    lo, hi = b["targets"]["coverage_90"]
    for z, m in b["by_zone"].items():
        assert lo <= m["coverage_90"] <= hi, z
        assert m["mae_model"] < m["mae_climatology"]
        assert m["underestimation_rate"] <= b["targets"]["underestimation_max"]


# --------------------------------------------------------------------------------------------- planning
def test_optimised_plan_is_revalidated_certified_and_needs_approval(site):
    """The optimiser proposes; the rule engine re-validates; a supervisor approves before activation."""
    p = optimise(site)
    assert p["status"] in ("OPTIMAL", "FEASIBLE")
    assert p["revalidation"]["result"] == "valid" and p["certificate"]["sha256"]
    assert p["metrics"]["heavy_harsh_worker_hours"] <= p["draft_metrics"]["heavy_harsh_worker_hours"]
    assert p["metrics"]["midday_violation_hours"] == 0 and p["metrics"]["withdrawal_work_hours"] == 0
    sid = p["scenario_id"]
    assert site.sup.post(f"/v1/plans/{sid}/activate").status_code == 409       # not approved yet
    assert site.sup.post(f"/v1/plans/{sid}/approve").status_code == 200
    a = site.sup.post(f"/v1/plans/{sid}/activate")
    assert a.status_code == 200 and a.json()["activation"]["state"] == "active"
    # Evening messages reach each worker in their own language.
    msgs = {m["worker"]: m for m in p["worker_messages"]}
    assert msgs["W07"]["lang"] == "ar" and msgs["W01"]["lang"] == "en"


@pytest.mark.tcase("T24", "T76")
def test_rest_capacity_shortage_gives_no_feasible_plan_with_remedies(site):
    """Too few shaded seats: 'no feasible protected plan', the binding constraint and permitted remedies."""
    r1 = next(r for r in site.sb.world["rest_areas"] if r["id"] == "R1")
    r1["seats"] = 8                                  # crew 1 alone needs 14 seats at a time
    p = optimise(site)
    assert p["status"] == "NO_FEASIBLE_PROTECTED_PLAN"
    dg = p["diagnosis"]
    assert "rest_capacity" in dg["binding_constraints"]
    remedy = next(x for x in dg["permitted_remedies"] if x["remedy"] == "rest_capacity")
    assert remedy["restores_feasibility"] is True and remedy["text_ar"]
    assert {"midday_window", "withdrawal_band", "clinician_restrictions"} <= set(dg["never_relaxed"])


@pytest.mark.tcase("T76", "T77")
def test_work_forced_into_the_midday_window_has_no_legal_plan(site):
    """A pour fixed at 12:30 cannot be scheduled: the legal window is never relaxed; the remedy is to move it."""
    r = site.sup.post("/v1/plans/optimise", {"task_overrides": {"P1": {"fixed_start": "12:30"}}})
    p = r.json()
    assert p["status"] == "NO_FEASIBLE_PROTECTED_PLAN"
    assert p["diagnosis"]["binding_constraints"] == ["legal_window_or_withdrawal_band"]
    assert p["diagnosis"]["permitted_remedies"][0]["remedy"] == "reschedule"


@pytest.mark.tcase("T75", "T77", "T33")
@pytest.mark.parametrize("kind,rule", [("midday", "policy_state_stop"), ("withdrawal", "policy_state_stop"),
                                       ("capacity", "rest_capacity"), ("remove_breaks", "required_rest_missing")])
def test_fault_injection_is_caught_by_independent_revalidation(site, kind, rule):
    """A plan that breaks a rule (injected fault) is rejected by the rule engine; activation is blocked."""
    p = optimise(site)
    r = site.sup.post(f"/v1/plans/{p['scenario_id']}/fault-injection", {"kind": kind}).json()
    assert r["revalidation"]["result"] == "invalid" and r["activation"] == "blocked"
    assert any(v["rule"] == rule for v in r["revalidation"]["violations"])
    if kind == "midday":
        assert any("AE-FED-MIDDAY:window" in v.get("reasons", []) for v in r["revalidation"]["violations"])


@pytest.mark.tcase("T32")
def test_change_between_evaluation_and_activation_invalidates_the_plan(site):
    """A clinician restriction set after approval changes the basis: activation is refused; re-plan."""
    p = optimise(site)
    sid = p["scenario_id"]
    site.sup.post(f"/v1/plans/{sid}/approve")
    r = site.as_("fatima").post("/v1/clinical/restrictions", {"worker_ref": "W07", "label": "no_heat_work",
                                                            "until": "2025-08-26T18:00:00+04:00",
                                                            "reason_private": "Clinical follow-up (SYNTHETIC)"})
    assert r.status_code == 200
    a = site.sup.post(f"/v1/plans/{sid}/activate")
    assert a.status_code == 409 and "restrictions_hash" in a.json()["detail"]
    assert site.sb.plans[sid]["activation"]["state"] == "rejected"
    # The new plan keeps the restricted worker out of heat work and passes re-validation.
    p2 = optimise(site)
    assert p2["revalidation"]["result"] == "valid"
    assert p2["plan"]["assignments"]["W07"]["heat_slots"] == []
    assert site.sup.post(f"/v1/plans/{p2['scenario_id']}/approve").status_code == 200
    assert site.sup.post(f"/v1/plans/{p2['scenario_id']}/activate").status_code == 200


def test_revalidation_catches_a_restricted_worker_in_heat_work(sandbox):
    """Independent re-validation reads the clinician's label: heat work for a 'no heat work' label is invalid."""
    from app.planner.twin import draft_to_plan, grid
    w = next(x for x in sandbox.world["workers"] if x["id"] == "W07")
    w["restriction"] = {"label": "no_heat_work", "until": "2025-08-26T18:00:00+04:00"}
    g = grid(sandbox.world, fs.scenario_forecast(), "2025-08-19")
    rv = revalidate(sandbox.world, g, draft_to_plan(sandbox.world), "2025-08-19")
    assert any(v.get("worker") == "W07" and "clinical:restriction" in v.get("reasons", []) for v in rv["violations"])


def test_fault_injection_helper_never_mutates_the_plan(site):
    """Fault injection works on a copy: the proposed plan itself is untouched."""
    p = site.sb.plans[optimise(site)["scenario_id"]]["plan"]
    snapshot = json.dumps(p, sort_keys=True)
    inject_fault(p, "remove_breaks")
    assert json.dumps(p, sort_keys=True) == snapshot


@pytest.mark.tcase("T78")
def test_same_crew_getting_the_hottest_slots_is_flagged(site):
    """Across the week one crew keeps getting the most harsh-band work: the report flags it for the supervisor."""
    rep = site.sup.get("/v1/sites/site_demo/fairness").json()
    assert rep["flag"] and rep["flag"]["crew"] == "C2" and rep["flag"]["days_most_exposed"] >= 4
    assert rep["message"]["ar"] and "W0" not in json.dumps(rep)          # crews only, never individuals
    crews = {c: {"name": c, "heat": True} for c in ("X", "Y", "Z")}
    always = [{"date": f"d{i}", "per_worker": {"X": 5.0, "Y": 3.0, "Z": 3.0}} for i in range(7)]
    assert fairness.assess(always, crews)["flag"]["crew"] == "X"
    rotating = [{"date": f"d{i}", "per_worker": {c: (5.0 if j == i % 3 else 3.0) for j, c in enumerate("XYZ")}}
                for i in range(7)]
    assert fairness.assess(rotating, crews)["flag"] is None


@pytest.mark.tcase("T78")
def test_optimiser_spreads_harsh_work_more_evenly_than_the_draft(site):
    """Within a day the fairness objective lowers the largest crew share of harsh-band work."""
    p = optimise(site)
    assert p["metrics"]["fairness_max_crew_harsh_hours"] <= p["draft_metrics"]["fairness_max_crew_harsh_hours"]


@pytest.mark.tcase("T75", "T76")
def test_every_replayed_day_gets_a_valid_plan_or_an_honest_remedy():
    """On 8 replayed August days every proposed plan passes independent re-validation; where no protected plan
    exists, the named remedy (postponing work) gives one, and no rule is relaxed. Regression: indoor work in a
    zone's withdrawal band (15 Aug) was once proposed by the solver and caught by re-validation."""
    from app.ai.evaluation import eval_plan
    ev = eval_plan()
    for row in ev["rows"]:
        if row["status"] in ("OPTIMAL", "FEASIBLE"):
            assert row["revalidation"] == "valid", row["day"]
        else:
            assert row["after_remedy"] and row["after_remedy"]["revalidation"] == "valid", row["day"]
    assert ev["solved"] + ev["solved_after_permitted_remedy"] == ev["site_days"]
    assert ev["fault_injections_rejected"].split("/")[0] == ev["fault_injections_rejected"].split("/")[1]


# --------------------------------------------- forecast information cutoff and splits (external review, Nov 2026)
def test_the_forecast_uses_only_readings_complete_at_the_18_00_issue_time():
    """Readings after the issue time can never change a forecast: late hours anchor on the previous day."""
    from datetime import date, timedelta

    from app.forecast import model as M
    issue, target = date(2025, 8, 18), date(2025, 8, 19)
    series = {(issue - timedelta(days=k), h): 30.0 + 0.1 * k for k in range(0, 20) for h in range(24)}
    for h in range(24):
        clean = M._features(dict(series), issue, target, h)
        poisoned = dict(series)
        for late in range(M.LAST_KNOWN_HOUR + 1, 24):     # everything not yet complete at 18:00 on the issue day
            poisoned[(issue, late)] = 999.0
        assert M._features(poisoned, issue, target, h) == clean, h
        assert clean[2] == (1 if h <= M.LAST_KNOWN_HOUR else 2)    # late hours have a longer effective lead


def test_fit_calibration_and_test_periods_are_separate_and_in_time_order():
    """The interval is calibrated on data the damping was not fitted on, and tested on data neither saw."""
    from app.forecast import model as M
    assert M.FIT_TO < M.CAL_FROM and M.CAL_TO < M.TEST_FROM
    f = M.fitted()
    assert all(p["n_fit"] > 0 and p["n_cal"] > 0 for p in f["params"].values())
    assert "calibrated on 2025-07-25" in f["method"]["interval"] and "fitted on 2025-06-30" in f["method"]["interval"]
    b = M.backtest()
    assert b["periods"]["test"].startswith("2025-08-08") and b["by_zone"]["all"]["zone_hours"] > 2000
    assert b["by_zone"]["all"]["mae_model"] < b["by_zone"]["all"]["mae_persistence"]
