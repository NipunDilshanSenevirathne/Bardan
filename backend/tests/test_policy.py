"""Policy engine: emergency precedence, heat bands, midday window, freshness, packs (T01-T23)."""
from __future__ import annotations

import copy
import json
import shutil

import pytest
from helpers import base_input

from app.core import policy

SUITE = json.loads((policy.shared_dir() / "conformance.json").read_text(encoding="utf-8"))
EMERGENCY_ACTIONS = ["BUDDY_STAY", "CALL_998", "EMERGENCY_CARD", "START_COOLING"]


@pytest.mark.parametrize("case", SUITE["cases"], ids=[c["id"] for c in SUITE["cases"]])
def test_conformance_case(case):
    """Shared conformance suite: state, band, action set and reason codes match the hand-written expectation."""
    got = policy.evaluate(case["input"])
    exp = case["expected"]
    assert got["state"] == exp["state"]
    assert got["band"] == exp["band"]
    assert sorted(got["actions"]) == sorted(exp["actions"])
    assert got["reasons"] == exp["reasons"]


# ------------------------------------------------------------------------------ worker protection
@pytest.mark.tcase("T01")
def test_new_confusion_is_an_emergency_even_with_normal_readings():
    """Confusion with an unrestricted reading: emergency path, no reassurance, no test needed."""
    got = policy.evaluate(base_input(symptoms=["confusion"]))
    assert got["state"] == "emergency"
    assert got["actions"] == EMERGENCY_ACTIONS
    assert got["exposure_percent"] == 0


@pytest.mark.tcase("T02")
def test_heavy_sweating_does_not_cancel_an_emergency():
    """Altered mental state with heavy sweating: still an emergency (dry skin is not required)."""
    got = policy.evaluate(base_input(symptoms=["heavy_sweating", "confusion"]))
    assert got["state"] == "emergency"


@pytest.mark.tcase("T03")
def test_dark_urine_and_muscle_pain_need_same_day_clinician_without_a_strip():
    """Muscle pain with dark urine: urgent clinical assessment; no urine strip is a prerequisite."""
    got = policy.evaluate(base_input(symptoms=["muscle_pain_dark_urine"]))
    assert got["state"] == "stop"
    assert "URGENT_CLINICAL_ASSESSMENT" in got["actions"]
    assert not any("STRIP" in a or "TEST" in a for a in got["actions"])


@pytest.mark.tcase("T04")
def test_mild_symptoms_stop_cool_assess():
    """A mild symptom on an ordinary day stops the activity and calls a first aider; no automatic clearance."""
    got = policy.evaluate(base_input(symptoms=["headache"]))
    assert got["state"] == "stop"
    assert {"STOP_ACTIVITY", "MOVE_TO_SHADE", "FIRST_AIDER_CHECK"} <= set(got["actions"])
    assert "STANDARD_CONTROLS" in got["actions"]
    assert got["exposure_percent"] == 0


@pytest.mark.tcase("T05")
def test_device_engine_needs_no_language_or_network_for_an_emergency():
    """The engine takes structured symptoms only: a tap on 'confused' needs no speech, model or network."""
    got = policy.evaluate({"now": "2026-08-06T10:00:00+04:00", "symptoms": ["confusion"]})
    assert got["state"] == "emergency"


@pytest.mark.tcase("T07")
def test_fasting_preference_never_changes_emergency_instructions():
    """Preferences such as fasting are not inputs to the emergency path."""
    a = policy.evaluate(base_input(symptoms=["collapse"]))
    b = policy.evaluate({**base_input(symptoms=["collapse"]), "preferences": {"fasting": True}})
    assert a == b and a["state"] == "emergency"


# -------------------------------------------------------------------------------- site protection
@pytest.mark.tcase("T11")
def test_ordinary_day_routine_controls():
    """TWL 230 for an acclimatized worker: routine controls."""
    got = policy.evaluate(base_input())
    assert got["state"] == "routine" and got["actions"] == ["STANDARD_CONTROLS"]


@pytest.mark.tcase("T12")
def test_unknown_workload_or_ppe_uses_the_conservative_plan():
    """Unknown workload or PPE: never routine; the approved conservative plan applies, treated as heavy."""
    got = policy.evaluate(base_input(task={"workload": "unknown", "outdoor": True}))
    assert got["state"] != "routine" and "FOLLOW_FALLBACK_PLAN" in got["actions"]
    assert "unknown:workload_or_ppe" in got["reasons"]
    got = policy.evaluate(base_input(task={"workload": "light", "outdoor": True, "ppe": "unknown"},
                                     zone={"outdoor": True, "direct_sun": False},
                                     worker={"acclimatization": "acclimatized", "day": 30,
                                             "restriction": "shaded_light_duty"}))
    assert got["state"] == "stop" and "REASSIGN_SHADED_LIGHT" in got["actions"]


@pytest.mark.tcase("T13")
def test_air_temperature_is_never_treated_as_wbgt_or_twl():
    """A feed with air temperature only: no band is derived from it; assessment unavailable."""
    for prov in ("measured", "derived", "official_external"):
        got = policy.evaluate(base_input(observation={"kind": "air_temp", "value": 44.0,
                                                      "observed_at": "2026-08-06T09:55:00+04:00",
                                                      "provenance": prov}))
        assert got["state"] == "unavailable" and got["band"] is None
        assert got["reasons"] == ["freshness:missing_or_stale"]


@pytest.mark.tcase("T14")
def test_forecast_is_never_a_live_observation():
    """A forecast value, however recent, never counts as a live reading."""
    got = policy.evaluate(base_input(observation={"kind": "wbgt", "value": 29.0,
                                                  "observed_at": "2026-08-06T09:59:00+04:00",
                                                  "provenance": "forecast"}))
    assert got["state"] == "unavailable" and "FOLLOW_FALLBACK_PLAN" in got["actions"]


@pytest.mark.tcase("T15")
def test_two_sources_disagree_most_protective_band_and_human_resolution():
    """Two fresh credible sources disagree: stricter band governs, all controls apply, a person resolves it."""
    got = policy.evaluate(base_input(
        observation={"kind": "twl", "value": 160, "observed_at": "2026-08-06T09:55:00+04:00", "provenance": "measured"},
        observations=[{"kind": "wbgt", "value": 32.2, "observed_at": "2026-08-06T09:50:00+04:00",
                       "provenance": "official_external"}]))
    assert got["band"] == "buffer"
    assert "RESOLVE_SOURCE_CONFLICT" in got["actions"] and "conflict:sources_disagree" in got["reasons"]
    assert {"EXTRA_BREAKS", "NO_LONE_WORK", "SHADE_AND_VENTILATION"} <= set(got["actions"])


@pytest.mark.tcase("T17")
def test_new_worker_day2_buffer_band_stops_heat_work():
    """New worker on day 2 at TWL 132 (buffer): heat work stopped for that worker."""
    got = policy.evaluate(base_input(worker={"acclimatization": "new", "day": 2},
                                     observation={"kind": "twl", "value": 132,
                                                  "observed_at": "2026-08-06T09:55:00+04:00",
                                                  "provenance": "measured"}))
    assert got["state"] == "stop" and "UNACCLIMATIZED_STOP_HEAT_WORK" in got["actions"]
    # The same reading for an acclimatized colleague is enhanced, not stopped.
    other = policy.evaluate(base_input(observation={"kind": "twl", "value": 132,
                                                    "observed_at": "2026-08-06T09:55:00+04:00",
                                                    "provenance": "measured"}))
    assert other["state"] == "enhanced"


@pytest.mark.tcase("T18")
@pytest.mark.parametrize("now,inside", [
    ("2026-08-06T08:30:00+00:00", True),     # 12:30 at the site
    ("2026-08-06T08:29:00+00:00", False),
    ("2026-08-06T10:59:00Z", True),          # 14:59 at the site
    ("2026-08-06T11:00:00Z", False),         # 15:00 at the site
    ("2026-08-06T15:30:00+05:30", True),     # a device in Colombo: 14:00 at the site
    ("2026-08-06T12:30:00-04:00", False),    # 20:30 at the site
])
def test_midday_window_uses_site_time_not_device_time(now, inside):
    """The midday rule is applied in Asia/Dubai whatever the device's time zone."""
    obs_time = now
    got = policy.evaluate(base_input(now=now, observation={"kind": "twl", "value": 230, "observed_at": obs_time,
                                                            "provenance": "measured"}))
    assert ("AE-FED-MIDDAY:window" in got["reasons"]) is inside


def test_timestamps_without_offset_are_refused():
    """A time without a UTC offset is ambiguous and is refused (no silent local-time guess)."""
    with pytest.raises(ValueError):
        policy.evaluate(base_input(now="2026-08-06T12:30:00"))


@pytest.mark.tcase("T19")
def test_exemption_requires_an_authorised_record():
    """A switched-on but unauthorised exemption does not lift the midday stop."""
    got = policy.evaluate(base_input(now="2026-08-06T13:00:00+04:00",
                                     observation={"kind": "twl", "value": 230,
                                                  "observed_at": "2026-08-06T12:55:00+04:00",
                                                  "provenance": "measured"},
                                     exemption={"authorised": False, "ref": "supervisor-toggle"}))
    assert got["state"] == "stop" and "AE-FED-MIDDAY:window" in got["reasons"]


@pytest.fixture
def tampered_shared(tmp_path, monkeypatch):
    """A copy of the shared policy folder that a test can tamper with; caches are cleared around it."""
    src = policy.shared_dir()
    dst = tmp_path / "shared"
    shutil.copytree(src, dst)
    monkeypatch.setenv("BARDAN_SHARED_DIR", str(dst))
    policy.load_pack.cache_clear()
    policy.pack_manifest.cache_clear()
    yield dst
    monkeypatch.delenv("BARDAN_SHARED_DIR", raising=False)
    policy.load_pack.cache_clear()
    policy.pack_manifest.cache_clear()


@pytest.mark.tcase("T20")
def test_modified_pack_is_rejected_with_a_safe_fallback(tampered_shared):
    """A pack whose content no longer matches its signed manifest is refused; fallback applies."""
    p = tampered_shared / "packs" / "AE-AD-HEAT.json"
    pack = json.loads(p.read_text(encoding="utf-8"))
    pack["twl_zones"][0]["min_exclusive"] = 100   # quietly relax a band
    p.write_text(json.dumps(pack), encoding="utf-8")
    got = policy.evaluate(base_input())
    assert got["state"] == "unavailable" and got["reasons"] == ["policy:pack_integrity_failed"]
    # Emergency still works without a trusted pack.
    assert policy.evaluate(base_input(symptoms=["collapse"]))["state"] == "emergency"


@pytest.mark.tcase("T20")
def test_rolled_back_pack_version_is_rejected(tampered_shared):
    """An older pack version (rollback) does not match the manifest and is refused."""
    p = tampered_shared / "packs" / "AE-AD-HEAT.json"
    pack = json.loads(p.read_text(encoding="utf-8"))
    pack["version"] = "0.0.9-demo"
    p.write_text(json.dumps(pack), encoding="utf-8")
    assert policy.evaluate(base_input())["reasons"] == ["policy:pack_integrity_failed"]


@pytest.mark.tcase("T21")
def test_pack_past_review_date_gives_assessment_unavailable():
    """After a pack's review date the engine returns the designated fallback, never a silent pass."""
    got = policy.evaluate(base_input(now="2027-07-01T10:00:00+04:00",
                                     observation={"kind": "twl", "value": 230,
                                                  "observed_at": "2027-07-01T09:55:00+04:00",
                                                  "provenance": "measured"}))
    assert got["state"] == "unavailable" and got["reasons"] == ["policy:pack_review_overdue"]
    urgent = policy.evaluate(base_input(now="2027-07-01T10:00:00+04:00", symptoms=["seizure"]))
    assert urgent["state"] == "emergency"


@pytest.mark.tcase("T22")
def test_physiological_signals_never_speed_up_acclimatization():
    """Research-module fields (camera pulse and similar) are not inputs: exposure follows the schedule only.
    The camera pulse module itself is not built in the prototype."""
    plain = policy.evaluate(base_input(worker={"acclimatization": "new", "day": 2}))
    with_pulse = policy.evaluate(base_input(worker={"acclimatization": "new", "day": 2, "camera_pulse_bpm": 58,
                                                    "pulse_low": True, "acclimatization_hint": "fast"}))
    assert plain == with_pulse and plain["exposure_percent"] == 40


@pytest.mark.tcase("T25")
def test_water_unavailable_stops_affected_outdoor_work():
    """No drinking water in the zone: affected heat work stops until water is restored."""
    got = policy.evaluate(base_input(resources={"water_available": False}))
    assert got["state"] == "stop" and {"RESTORE_WATER", "STOP_AFFECTED_WORK"} <= set(got["actions"])


@pytest.mark.tcase("T61")
def test_returning_worker_follows_the_documented_schedule():
    """A worker back after illness or leave restarts on the documented schedule; no algorithmic clearance."""
    sched = policy.heat_pack()["acclimatization"]["experienced_percent_by_day"]
    for day, pct in enumerate(sched, start=1):
        got = policy.evaluate(base_input(worker={"acclimatization": "returning", "day": day}))
        assert got["exposure_percent"] == pct
        assert ("LIMIT_EXPOSURE" in got["actions"]) is (pct < 100)
    assert sched[0] < 100


def test_wbgt_bands_mirror_the_forecast_model():
    """The forecast's band function and the engine's demo WBGT bands agree at every edge."""
    from app.forecast.model import band_of_wbgt
    from app.forecast.service import band_of
    for v in (27.9, 28.0, 30.9, 31.0, 32.9, 33.0, 36.0):
        assert policy.band_from_wbgt(v) == band_of_wbgt(v) == band_of(v)


def test_precedence_emergency_outranks_midday_and_stale_data():
    """Precedence: emergency first, even inside the midday window and without any reading."""
    got = policy.evaluate(base_input(now="2026-08-06T13:00:00+04:00", observation=None, symptoms=["chest_pain"]))
    assert got["state"] == "emergency"


def test_engine_is_a_pure_function():
    """Same input, same output; the input is not mutated."""
    inp = base_input(symptoms=["headache"])
    snapshot = copy.deepcopy(inp)
    assert policy.evaluate(inp) == policy.evaluate(inp)
    assert inp == snapshot
