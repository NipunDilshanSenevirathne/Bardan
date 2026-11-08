"""Independent re-validation and the capacity-feasibility certificate (§10.3 step 5, §29.3, B.11).

The optimiser is never trusted. This module checks a proposed plan with the
deterministic policy engine (core/policy.py) one worker and one slot at a time,
and checks rest capacity per 15-minute block. It shares no code path with the
solver's constraint model, so a solver bug or an injected fault is caught here
(tests T75, T77).
"""
from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

from ..core import policy
from .twin import REST_MIN, SLOT_MIN, SLOTS, slot_label, slot_time

ENGINE_VERSION = "rule-engine@1.0.0"


def revalidate(world: dict[str, Any], g: dict[str, Any], plan: dict[str, Any], day: str) -> dict[str, Any]:
    zones = {z["id"]: z for z in world["zones"]}
    crews = {c["id"]: c for c in world["crews"]}
    rest = {r["id"]: r for r in world["rest_areas"]}
    violations: list[dict[str, Any]] = []
    checks = 0
    task_by_crew = {t["crew"]: t for t in plan["tasks"]}
    breaks_by_crew_hour: dict[tuple[str, int], int] = {}
    seat_use: dict[tuple[str, int], int] = {}
    for b in plan.get("breaks", []):
        for c in b.get("crews") or [b["crew"]]:
            breaks_by_crew_hour[(c, b["start_q"] // 4)] = breaks_by_crew_hour.get((c, b["start_q"] // 4), 0) + \
                15 * b["quarters"]
            for q in range(b["start_q"], b["start_q"] + b["quarters"]):
                seat_use[(b["rest_area"], q)] = seat_use.get((b["rest_area"], q), 0) + crews[c]["size"]
    for w in world["workers"]:
        t = task_by_crew.get(w["crew"])
        if not t:
            continue
        z = zones[t["zone"]]
        assigned = (plan.get("assignments") or {}).get(w["id"])
        heat_slots = set(assigned["heat_slots"]) if assigned else set(t["slots"])
        for s in t["slots"]:
            on_heat = s in heat_slots
            if not on_heat:
                continue
            checks += 1
            now = slot_time(day, s) + timedelta(minutes=15)
            row = g["zones"][t["zone"]][s]
            if row["wbgt_hi"] is None:
                violations.append({"worker": w["id"], "slot": slot_label(s), "rule": "forecast_unavailable"})
                continue
            res = policy.evaluate({
                "now": now.isoformat(),
                "zone": {"outdoor": z["outdoor"], "direct_sun": z["direct_sun"]},
                "task": {"workload": t["workload"], "outdoor": t["outdoor"]},
                "worker": {"acclimatization": w["acclimatization"], "day": w["day"],
                           "restriction": w.get("restriction")},
                "observation": {"kind": "wbgt", "value": row["wbgt_hi"], "provenance": "derived",
                                "observed_at": slot_time(day, s).isoformat()},
                "resources": {"water_available": True},
                "symptoms": [],
                "exemption": None,
            })
            if res["state"] in ("stop", "emergency", "unavailable"):
                violations.append({"worker": w["id"], "task": t["id"], "slot": slot_label(s),
                                   "rule": "policy_state_" + res["state"], "reasons": res["reasons"]})
        if policy.is_unacclimatized(w):
            allowance = policy.acclimatization_percent(w) / 100.0 * 480
            if len(heat_slots) * SLOT_MIN > allowance + 1e-6:
                violations.append({"worker": w["id"], "rule": "acclimatization_schedule",
                                   "minutes": len(heat_slots) * SLOT_MIN, "allowance_min": allowance})
    # Rest per crew-hour.
    for c, t in task_by_crew.items():
        z = zones[t["zone"]]
        if not (t["outdoor"] or z["direct_sun"]):
            continue
        for h in range(SLOTS // 2):
            worked = [s for s in (2 * h, 2 * h + 1) if s in t["slots"]]
            if not worked:
                continue
            need = max(REST_MIN.get(g["zones"][t["zone"]][s]["band"], 0) for s in worked)
            checks += 1
            if need and breaks_by_crew_hour.get((c, h), 0) < min(need, 15):
                violations.append({"crew": c, "hour": slot_label(2 * h), "rule": "required_rest_missing",
                                   "required_min": need})
    # Capacity per 15-minute block (G19).
    for (rid, q), used in seat_use.items():
        checks += 1
        cap = rest[rid]["seats"] if rest[rid]["working"] and rest[rid]["accessible"] else 0
        if used > cap:
            t = 300 + 15 * q
            violations.append({"rest_area": rid, "time": f"{t // 60:02d}:{t % 60:02d}", "rule": "rest_capacity",
                               "demand": used, "seats": cap})
    return {"engine": ENGINE_VERSION, "result": "valid" if not violations else "invalid",
            "checks": checks, "violations": violations}


def certificate(world: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    body = {
        "scenario_id": scenario["scenario_id"],
        "site_id": world["site"]["id"],
        "for_date": scenario["for_date"],
        "policy_versions": world["site"]["policy_packs"],
        "forecast": {"issued_at": scenario["forecast_issued_at"], "label": scenario["forecast_label"]},
        "metrics": scenario["metrics"],
        "revalidation": {k: scenario["revalidation"][k] for k in ("engine", "result", "checks")},
    }
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    return {**body, "certificate_id": "cert_" + digest[:12], "sha256": digest, "label": "SIMULATION",
            "statement": ("Every assigned heat-work slot was re-checked by the rule engine against the "
                          "conservative forecast band, the midday window and the acclimatization schedule, "
                          "and rest-seat demand was checked against capacity for every 15-minute block.")}


def inject_fault(plan: dict[str, Any], kind: str = "midday") -> dict[str, Any]:
    """Fault injection for tests T33/T75/T77: break a rule in a copy of a valid plan."""
    bad = json.loads(json.dumps(plan))
    t = next(x for x in bad["tasks"] if x["id"] == "P1")
    if kind == "midday":
        t["slots"] = list(range(15, 15 + len(t["slots"])))     # 12:30 onwards
    elif kind == "capacity":
        bad["breaks"].append({"crew": "C2", "crews": ["C1", "C2"], "start_q": 8, "quarters": 1, "rest_area": "R1"})
    elif kind == "withdrawal":
        t["slots"] = list(range(10, 10 + len(t["slots"])))     # 10:00 onwards
    elif kind == "remove_breaks":
        bad["breaks"] = []                                      # T33: breaks removed under enhanced controls
    return bad
