"""Deterministic heat-protection policy engine (server side).

The same rules run in the browser (frontend/src/engine/engine.ts). Both engines
must agree on every case in shared/conformance.json; the Decision Replay Pack
checks this (finalsystem.md §29.2).

Precedence (finalsystem.md §9.7):
  1. Emergency symptoms            -> emergency workflow
  2. Legal prohibition             -> block the activity (midday break)
  3. Clinician restriction label   -> minimum necessary restriction
  4. Occupational policy (TWL)     -> required controls
  5. Missing data or resources     -> approved fallback / stop affected work
  6. AI assistance                 -> never changes the outcome
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

STATE_RANK = {"routine": 0, "enhanced": 1, "unavailable": 2, "stop": 3, "emergency": 4}
BAND_RANK = {"unrestricted": 0, "acclimatization": 1, "buffer": 2, "withdrawal": 3}
KNOWN_WORKLOADS = ("light", "moderate", "heavy")


def shared_dir() -> Path:
    env = os.environ.get("BARDAN_SHARED_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3] / "shared"


class PackIntegrityError(Exception):
    """A policy pack whose content does not match its signed manifest entry (tampered or rolled back)."""


def _canonical(d: dict[str, Any]) -> bytes:
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


@lru_cache(maxsize=None)
def pack_manifest() -> dict[str, Any]:
    p = shared_dir() / "packs" / "manifest.json"
    if not p.exists():
        return {"packs": {}}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=None)
def load_pack(name: str) -> dict[str, Any]:
    with open(shared_dir() / "packs" / f"{name}.json", encoding="utf-8") as f:
        data = json.load(f)
    entry = pack_manifest().get("packs", {}).get(name)
    if entry:
        digest = hashlib.sha256(_canonical(data)).hexdigest()
        if digest != entry["sha256"] or data.get("version") != entry["version"]:
            raise PackIntegrityError(f"{name}: content or version does not match the manifest (T20)")
    return data


def pack_review_by(name: str) -> str | None:
    return (pack_manifest().get("packs", {}).get(name) or {}).get("review_by")


# Minimal built-in list used only if the pack itself cannot be trusted: the emergency path never depends
# on a valid pack (finalsystem.md §9.7, precedence 1).
BUILTIN_URGENT = ["confusion", "collapse", "seizure", "chest_pain", "breathing_difficulty", "slurred_speech",
                  "unresponsive"]


def _unavailable(reason: str) -> dict[str, Any]:
    return {"state": "unavailable", "band": None, "actions": ["FOLLOW_FALLBACK_PLAN"], "reasons": [reason],
            "exposure_percent": 0}


def heat_pack() -> dict[str, Any]:
    return load_pack("AE-AD-HEAT")


def midday_pack() -> dict[str, Any]:
    return load_pack("AE-FED-MIDDAY")


def _in_range(value: float, rule: dict[str, Any]) -> bool:
    lo_inc = rule.get("min_inclusive")
    lo_exc = rule.get("min_exclusive")
    hi_inc = rule.get("max_inclusive")
    hi_exc = rule.get("max_exclusive")
    if lo_inc is not None and value < lo_inc:
        return False
    if lo_exc is not None and value <= lo_exc:
        return False
    if hi_inc is not None and value > hi_inc:
        return False
    if hi_exc is not None and value >= hi_exc:
        return False
    return True


def band_from_twl(value: float, pack: dict[str, Any] | None = None) -> str:
    pack = pack or heat_pack()
    for rule in pack["twl_zones"]:
        if _in_range(value, rule):
            return rule["band"]
    raise ValueError(f"TWL value {value} outside all bands")


def band_from_wbgt(value: float, pack: dict[str, Any] | None = None) -> str:
    pack = pack or heat_pack()
    for rule in pack["wbgt_planning_bands_demo"]:
        if _in_range(value, rule):
            return rule["band"]
    raise ValueError(f"WBGT value {value} outside all bands")


def parse_time(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise ValueError("timestamps must include a UTC offset")
    return dt


def in_midday_window(now: datetime, pack: dict[str, Any] | None = None) -> bool:
    pack = pack or midday_pack()
    local = now.astimezone(ZoneInfo(pack["window"]["timezone"]))
    md = local.strftime("%m-%d")
    if not (pack["season"]["from"] <= md <= pack["season"]["to"]):
        return False
    hm = local.strftime("%H:%M")
    return pack["window"]["start"] <= hm < pack["window"]["end"]


def freshness_key(obs: dict[str, Any]) -> str | None:
    prov = obs.get("provenance")
    kind = obs.get("kind")
    if prov == "measured" and kind in ("twl", "wbgt"):
        return f"{kind}_measured"
    if prov == "official_external":
        return "official_external"
    if prov == "derived":
        return "derived"
    # "forecast" is deliberately absent: forecasts plan ahead and never count
    # as a live observation (finalsystem.md §9.2, §10.4).
    return None


def is_fresh(obs: dict[str, Any] | None, now: datetime, pack: dict[str, Any] | None = None) -> bool:
    pack = pack or heat_pack()
    if not obs or obs.get("value") is None or not obs.get("observed_at"):
        return False
    key = freshness_key(obs)
    if key is None:
        return False
    age_min = (now - parse_time(obs["observed_at"])).total_seconds() / 60.0
    if age_min < -5:  # observation from the future: clock problem, not trusted
        return False
    return age_min <= pack["freshness_minutes"][key]


def acclimatization_percent(worker: dict[str, Any] | None, pack: dict[str, Any] | None = None) -> int:
    pack = pack or heat_pack()
    if not worker:
        return 100
    stage = worker.get("acclimatization", "acclimatized")
    day = int(worker.get("day", 99))
    if stage == "new":
        sched = pack["acclimatization"]["new_percent_by_day"]
    elif stage == "returning":
        sched = pack["acclimatization"]["experienced_percent_by_day"]
    else:
        return 100
    if day < 1:
        return sched[0]
    if day > len(sched):
        return 100
    return sched[day - 1]


def is_unacclimatized(worker: dict[str, Any] | None, pack: dict[str, Any] | None = None) -> bool:
    if not worker:
        return False
    return acclimatization_percent(worker, pack) < 100


def evaluate(inp: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one worker/task/zone situation. Pure function of its input."""
    now = parse_time(inp["now"])
    symptoms_in = list(inp.get("symptoms") or [])
    try:
        pack = heat_pack()
        mpack = midday_pack()
    except PackIntegrityError:
        if any(s in BUILTIN_URGENT for s in symptoms_in):
            return {"state": "emergency", "band": None,
                    "actions": sorted(["EMERGENCY_CARD", "CALL_998", "START_COOLING", "BUDDY_STAY"]),
                    "reasons": ["emergency:urgent_symptom"], "exposure_percent": 0}
        return _unavailable("policy:pack_integrity_failed")
    local_day = now.astimezone(ZoneInfo(pack.get("site_timezone", "Asia/Dubai"))).date().isoformat()
    overdue = [n for n in ("AE-AD-HEAT", "AE-FED-MIDDAY") if (pack_review_by(n) or "9999-12-31") < local_day]
    if overdue:
        if any(s in pack["urgent_symptoms"] for s in symptoms_in):
            return {"state": "emergency", "band": None,
                    "actions": sorted(["EMERGENCY_CARD", "CALL_998", "START_COOLING", "BUDDY_STAY"]),
                    "reasons": ["emergency:urgent_symptom"], "exposure_percent": 0}
        return _unavailable("policy:pack_review_overdue")
    zone = inp.get("zone") or {}
    task = inp.get("task") or {}
    worker = inp.get("worker")
    resources = inp.get("resources") or {}
    symptoms = list(inp.get("symptoms") or [])
    exemption = inp.get("exemption") or {}

    reasons: list[str] = []
    actions: set[str] = set()
    state = "routine"
    band: str | None = None
    exposure = acclimatization_percent(worker, pack)

    def raise_state(new_state: str) -> None:
        nonlocal state
        if STATE_RANK[new_state] > STATE_RANK[state]:
            state = new_state

    # 1. Emergency symptoms outrank everything and need no data at all.
    urgent = [s for s in symptoms if s in pack["urgent_symptoms"]]
    if urgent:
        return {
            "state": "emergency",
            "band": None,
            "actions": sorted(["EMERGENCY_CARD", "CALL_998", "START_COOLING", "BUDDY_STAY"]),
            "reasons": ["emergency:urgent_symptom"],
            "exposure_percent": 0,
        }

    concerning = [s for s in symptoms if s in pack["concerning_symptoms"]]
    if concerning:
        raise_state("stop")
        actions.update(["STOP_ACTIVITY", "MOVE_TO_SHADE", "FIRST_AIDER_CHECK"])
        reasons.append("triage:concerning_symptom")
        if "muscle_pain_dark_urine" in concerning:
            actions.add("URGENT_CLINICAL_ASSESSMENT")
            reasons.append("triage:possible_muscle_breakdown")
        exposure = 0

    heat_task = bool(task.get("outdoor") or zone.get("direct_sun"))

    # 2. Legal prohibition: federal midday break.
    if (
        in_midday_window(now, mpack)
        and task.get("outdoor")
        and zone.get("direct_sun")
        and not exemption.get("authorised")
    ):
        raise_state("stop")
        actions.update(["STOP_OUTDOOR_WORK", "MOVE_TO_SHADE"])
        reasons.append("AE-FED-MIDDAY:window")
        exposure = 0

    # 2b. Unknown workload or clothing/PPE: the assessment cannot be exact, so the approved conservative plan
    # applies and the task is treated as heavy (T12).
    workload = task.get("workload")
    if task and (workload not in KNOWN_WORKLOADS or task.get("ppe") == "unknown"):
        raise_state("enhanced")
        actions.add("FOLLOW_FALLBACK_PLAN")
        reasons.append("unknown:workload_or_ppe")
        workload = "heavy"

    # 3. Clinician restriction label (minimum necessary; never the reason).
    restriction = (worker or {}).get("restriction")
    if isinstance(restriction, dict):
        restriction = restriction.get("label")
    if (restriction == "shaded_light_duty" and (workload == "heavy" or zone.get("direct_sun"))) or \
            (restriction == "no_heat_work" and heat_task):
        raise_state("stop")
        actions.add("REASSIGN_SHADED_LIGHT")
        reasons.append("clinical:restriction")
        exposure = 0

    # 4. Occupational policy from fresh observations. With two or more credible sources the most protective
    # band governs, every source's controls apply together, and the conflict goes to a person (T15).
    candidates = list(inp.get("observations") or [])
    if inp.get("observation"):
        candidates.insert(0, inp["observation"])
    fresh = [o for o in candidates if is_fresh(o, now, pack) and o.get("kind") in ("twl", "wbgt")]
    if not fresh:
        raise_state("unavailable")
        actions.add("FOLLOW_FALLBACK_PLAN")
        reasons.append("freshness:missing_or_stale")
    else:
        graded = []
        for o in fresh:
            b = band_from_twl(float(o["value"]), pack) if o["kind"] == "twl" else band_from_wbgt(float(o["value"]), pack)
            graded.append((BAND_RANK[b], b, o))
        _, band, obs = max(graded, key=lambda x: x[0])
        reasons.append(f"AE-AD-HEAT:{'twl' if obs['kind'] == 'twl' else 'wbgt_demo'}:{band}")
        for _, b, _o in graded:
            actions.update(pack["controls_by_band"][b])
        if len({b for _, b, _o in graded}) > 1:
            actions.add("RESOLVE_SOURCE_CONFLICT")
            reasons.append("conflict:sources_disagree")
        raise_state(pack["state_by_band"][band])
        if band in ("buffer", "withdrawal") and is_unacclimatized(worker, pack) and heat_task:
            raise_state("stop")
            actions.add("UNACCLIMATIZED_STOP_HEAT_WORK")
            reasons.append("AE-AD-HEAT:unacclimatized")
            exposure = 0
        elif band == "acclimatization" and is_unacclimatized(worker, pack):
            actions.add("NO_LONE_WORK")

    # 5. Missing resources.
    if resources.get("water_available") is False and heat_task:
        raise_state("stop")
        actions.update(["RESTORE_WATER", "STOP_AFFECTED_WORK"])
        reasons.append("resources:water_unavailable")
        exposure = 0

    if exposure < 100 and state not in ("stop", "emergency") and worker:
        actions.add("LIMIT_EXPOSURE")

    return {
        "state": state,
        "band": band,
        "actions": sorted(actions),
        "reasons": reasons,
        "exposure_percent": exposure,
    }
