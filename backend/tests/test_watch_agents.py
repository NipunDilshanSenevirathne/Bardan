"""Watch (aggregate signals) and bounded agents (T92-T97)."""
from __future__ import annotations

import json

import pytest

from app.ai import orchestrator
from app.ai.orchestrator import MANIFESTS, AgentDenied, AgentRun
from app.insights import cusum


@pytest.mark.tcase("T92")
def test_subcontractor_group_of_three_is_suppressed():
    """A subcontractor group of 3 workers produces no signal; the suppression is stated."""
    out = cusum.signals()
    d = next(s for s in out["signals"] if s["scope"]["subcontractor"] == "Subcontractor D")
    assert d["suppressed"] is True and "cusum_path" not in d and d["individuals_included"] is False


@pytest.mark.tcase("T93")
def test_detector_output_naming_an_individual_is_blocked():
    """Detectors work on aggregates only: output carrying a worker ID, pseudonym or name is blocked."""
    for bad in ({"signal": "W07 had 4 gaps"}, {"x": ["pt_1a2b3c4d"]}, {"note": "Ravi Kumar again"}):
        with pytest.raises(cusum.IndividualOutputBlocked):
            cusum.guard_aggregate(bad)
    cusum.guard_aggregate(cusum.signals())         # the real output passes
    assert "W0" not in json.dumps(cusum.signals())


@pytest.mark.tcase("T94")
def test_injected_water_gap_pattern_is_detected_and_drafts_a_review(site):
    """An injected pattern of repeated water gaps alarms; the HSE review task is drafted, never automatic."""
    out = cusum.signals()
    alarms = [s for s in out["signals"] if s.get("alarm")]
    assert alarms and all(a["action"]["automatic_action"] is False for a in alarms)
    assert alarms[0]["explanation"]["ar"]
    ev = cusum.evaluate_detector()          # held-out seed, 1000 synthetic site-months per family
    sf = ev["supply_failure"]
    assert sf["detection_rate_2d"] >= 0.90 and sf["false_alerts_per_site_month"] <= 1 and sf["met_targets"]
    # The gradual x4 stress test is reported honestly, target or not; it must still not flood HSE with alerts.
    assert ev["gradual_x4"]["false_alerts_per_site_month"] <= 1
    assert isinstance(ev["gradual_x4"]["met_targets"], bool)
    sara = site.as_("sara")
    before = len(site.sb.ledger.tasks)
    r = sara.post("/v1/insights/review-tasks", {"signal_id": alarms[0]["signal_id"]})
    assert r.status_code == 200 and r.json()["task"]["action_code"] == "HSE_REVIEW"
    assert len(site.sb.ledger.tasks) == before + 1
    # A supervisor cannot approve a review task from a signal.
    assert site.sup.post("/v1/insights/review-tasks", {"signal_id": alarms[0]["signal_id"]}).status_code == 403


@pytest.mark.tcase("T95")
def test_agent_exceeding_its_step_budget_is_stopped():
    """An agent past its step budget is stopped, the fallback is used and the run is recorded."""
    run = AgentRun("insight")
    with pytest.raises(AgentDenied) as e:
        for _ in range(MANIFESTS["insight"]["budgets"]["max_steps"] + 1):
            run.call("aggregate_query", lambda: None)
    assert "T95" in str(e.value) and run.outcome == "budget"


@pytest.mark.tcase("T96")
def test_tool_outside_the_manifest_is_denied_and_logged(sandbox):
    """A tool outside the signed manifest is denied, the run ends safely, and the denial is logged."""
    run = AgentRun("care_navigator", sandbox)
    with pytest.raises(AgentDenied):
        run.call("write_operational", lambda: "should never run")
    rec = sandbox.agent_runs[-1]
    assert rec["outcome"] == "denied" and rec["steps"][-1]["decision"] == "denied"


@pytest.mark.tcase("T96")
def test_tampered_manifest_cannot_start():
    """A manifest edited after signing (adding read_clinical) fails its signature check."""
    tampered = json.loads(json.dumps(MANIFESTS["insight"]))
    tampered["tools"]["read_clinical"] = "read"
    assert orchestrator._sign(tampered) != tampered["signature"]


@pytest.mark.tcase("T97")
def test_planning_agent_cannot_export_or_activate(site):
    """A red-team request to the planning agent: export and activation are denied; approval matrix enforced."""
    probes = {p["probe"]: p for p in orchestrator.probe_tool_misuse()}
    assert probes["planning agent calls export_data"]["blocked"] is True
    assert probes["planning agent activates a plan"]["blocked"] is True
    assert all(p["blocked"] for p in probes.values())
    r = site.sup.post("/v1/plans/optimise", {})
    assert r.json()["agent_run"]["outcome"] == "completed"
    assert site.sb.active_plan_id is None or site.sb.active_plan_id != r.json()["scenario_id"]
    assert all(s["tool"] in MANIFESTS["planning"]["tools"] for s in r.json()["agent_run"]["steps"])


def test_kill_switch_stops_an_agent():
    """With the kill switch off, the agent does not run and the manual path is used."""
    run = AgentRun("compliance", kill_switch=False)
    with pytest.raises(AgentDenied):
        run.call("query_metrics", lambda: None)
    assert run.outcome == "killed"
