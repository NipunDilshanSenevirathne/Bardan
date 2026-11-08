"""Site Heat Twin (finalsystem.md §10.3 step 3, §11.4, Appendix G19, G25).

The twin simulates one site-day for a candidate plan on a 30-minute grid
(05:00-19:00, Asia/Dubai). It is deterministic and has no AI in it. For every
zone and slot it knows the forecast planning band (upper end of the 90%
interval, G26), the legal windows and the resources, and it reports:

* heavy-work worker-hours in the buffer band or harsher (G25),
* work placed in the withdrawal band or the midday window (hard violations),
* rest-seat demand against capacity per 15-minute block, counting walking time
  as exposure, not rest (G19),
* unacclimatized workers on heat work in buffer or harsher, and exposure above
  their documented schedule (§9.6),
* deferred work, fairness across crews and an estimate of water demand.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ..core import policy
from ..forecast.service import band_of, slot_value

DAY_START = "05:00"
SLOTS = 28           # 30-minute slots, 05:00-19:00
SLOT_MIN = 30
HARSH = ("buffer", "withdrawal")
REST_MIN = {"unrestricted": 0, "acclimatization": 10, "buffer": 15, "withdrawal": 40}
WATER_L_PER_HOUR = 0.75   # general background (NIOSH ~1 cup / 15-20 min); planning estimate only


def slot_time(day: str, i: int) -> datetime:
    return datetime.fromisoformat(f"{day}T{DAY_START}:00+04:00") + timedelta(minutes=SLOT_MIN * i)


def hhmm_to_slot(hhmm: str) -> int:
    h, m = int(hhmm[:2]), int(hhmm[3:5])
    return (h * 60 + m - 5 * 60) // SLOT_MIN


def slot_label(i: int) -> str:
    t = 5 * 60 + SLOT_MIN * i
    return f"{t // 60:02d}:{t % 60:02d}"


def grid(world: dict[str, Any], fc: dict[str, Any], day: str) -> dict[str, Any]:
    """Planning band and legality for every zone and slot."""
    out: dict[str, Any] = {"zones": {}, "midday": [], "day": day}
    mpack = policy.midday_pack()
    for i in range(SLOTS):
        mid = slot_time(day, i) + timedelta(minutes=15)
        out["midday"].append(policy.in_midday_window(mid, mpack))
    for z in world["zones"]:
        rows = []
        for i in range(SLOTS):
            mid = slot_time(day, i) + timedelta(minutes=15)
            if fc.get("available"):
                hi = slot_value(fc, z["id"], mid, "hi")
                pt = slot_value(fc, z["id"], mid, "point")
            else:
                hi = pt = None
            rows.append({"slot": i, "time": slot_label(i), "wbgt_hi": hi, "wbgt_point": pt,
                         "band": band_of(hi) if hi is not None else "unavailable"})
        out["zones"][z["id"]] = rows
    return out


def _task_slots(task: dict[str, Any]) -> list[int]:
    return sorted(task.get("slots") or [])


def crew_members(world: dict[str, Any], crew_id: str) -> list[dict[str, Any]]:
    return [w for w in world["workers"] if w["crew"] == crew_id]


def heat_allowance_min(worker: dict[str, Any]) -> int:
    return int(round(policy.acclimatization_percent(worker) / 100.0 * 480))


def simulate(world: dict[str, Any], g: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """Run the twin on a plan.

    plan = {"tasks": [{id, zone, crew, workload, outdoor, slots:[...]}],
            "breaks": [{crew, start_q (15-min index from 05:00), quarters, rest_area}],
            "assignments": {worker_id: {"heat_slots": [...], "shaded_slots": [...]}} (optional)}
    """
    zones = {z["id"]: z for z in world["zones"]}
    rest = {r["id"]: r for r in world["rest_areas"]}
    crews = {c["id"]: c for c in world["crews"]}
    m = {"heavy_harsh_worker_hours": 0.0, "moderate_harsh_worker_hours": 0.0, "withdrawal_work_hours": 0.0,
         "midday_violation_hours": 0.0, "deferred_work_hours": 0.0, "water_litres": 0.0}
    violations: list[dict[str, Any]] = []
    crew_harsh: dict[str, float] = {c: 0.0 for c in crews}
    work_by_crew_slot: dict[tuple[str, int], dict[str, Any]] = {}
    for t in plan["tasks"]:
        slots = _task_slots(t)
        size = crews[t["crew"]]["size"]
        req = int(t.get("duration_min", len(slots) * SLOT_MIN)) // SLOT_MIN
        m["deferred_work_hours"] += max(0, req - len(slots)) * size * SLOT_MIN / 60.0
        z = zones[t["zone"]]
        heat_task = bool(t.get("outdoor") or z.get("direct_sun"))
        for s in slots:
            band = g["zones"][t["zone"]][s]["band"]
            work_by_crew_slot[(t["crew"], s)] = {"task": t["id"], "band": band, "heat": heat_task, "zone": t["zone"]}
            hours = SLOT_MIN / 60.0
            if heat_task:
                m["water_litres"] += WATER_L_PER_HOUR * size * hours
            if heat_task and band in HARSH:
                if t["workload"] == "heavy":
                    m["heavy_harsh_worker_hours"] += size * hours
                elif t["workload"] == "moderate":
                    m["moderate_harsh_worker_hours"] += size * hours
                crew_harsh[t["crew"]] += size * hours
            if band == "withdrawal":
                m["withdrawal_work_hours"] += size * hours
                violations.append({"type": "withdrawal_band", "task": t["id"], "slot": slot_label(s),
                                   "detail": f"Zone {t['zone']} forecast band is withdrawal"})
            if t.get("outdoor") and z.get("direct_sun") and g["midday"][s]:
                m["midday_violation_hours"] += size * hours
                violations.append({"type": "midday_window", "task": t["id"], "slot": slot_label(s),
                                   "detail": "Outdoor work in direct sun during the federal midday break"})
            if band == "unavailable":
                violations.append({"type": "forecast_unavailable", "task": t["id"], "slot": slot_label(s),
                                   "detail": "No forecast: the season's standard plan applies"})

    # Rest requirement per crew-hour and seat capacity per 15-minute block.
    seat_use: dict[tuple[str, int], int] = {}
    breaks_by_crew_hour: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for b in plan.get("breaks", []):
        for c in b["crews"] if "crews" in b else [b["crew"]]:
            size = crews[c]["size"]
            for q in range(b["start_q"], b["start_q"] + b["quarters"]):
                seat_use[(b["rest_area"], q)] = seat_use.get((b["rest_area"], q), 0) + size
                breaks_by_crew_hour.setdefault((c, q // 4), []).append(b)
    rest_conflicts = []
    for (rid, q), used in sorted(seat_use.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        cap = rest[rid]["seats"] if rest[rid]["working"] and rest[rid]["accessible"] else 0
        if used > cap:
            rest_conflicts.append({"rest_area": rid, "time": _q_label(q), "demand": used, "seats": cap})
    missing_rest = []
    for c in crews:
        for h in range(SLOTS // 2):
            bands = [work_by_crew_slot.get((c, 2 * h + k)) for k in (0, 1)]
            need = max((REST_MIN.get(x["band"], 0) for x in bands if x and x["heat"]), default=0)
            if need and not breaks_by_crew_hour.get((c, h)):
                missing_rest.append({"crew": c, "hour": slot_label(2 * h), "required_min": need})
    # Unacclimatized workers.
    unaccl = []
    for w in world["workers"]:
        if not policy.is_unacclimatized(w):
            continue
        a = (plan.get("assignments") or {}).get(w["id"])
        crew_slots = [s for (c, s), x in work_by_crew_slot.items() if c == w["crew"] and x["heat"]]
        heat_slots = a["heat_slots"] if a else crew_slots
        allowance = heat_allowance_min(w)
        if len(heat_slots) * SLOT_MIN > allowance:
            unaccl.append({"worker": w["id"], "type": "exposure_above_schedule",
                           "minutes": len(heat_slots) * SLOT_MIN, "allowance_min": allowance})
        for s in heat_slots:
            x = work_by_crew_slot.get((w["crew"], s))
            if x and x["band"] in HARSH:
                unaccl.append({"worker": w["id"], "type": "heat_work_in_harsh_band", "slot": slot_label(s),
                               "band": x["band"]})
    fairness = {c: round(v, 1) for c, v in crew_harsh.items()}
    vals = [v for v in fairness.values()]
    m = {k: round(v, 1) for k, v in m.items()}
    m["rest_conflicts"] = len(rest_conflicts)
    m["missing_rest_hours"] = len(missing_rest)
    m["unacclimatized_violations"] = len(unaccl)
    m["fairness_max_crew_harsh_hours"] = max(vals) if vals else 0
    feasible = not (violations or rest_conflicts or missing_rest or unaccl)
    return {"metrics": m, "violations": violations, "rest_conflicts": rest_conflicts, "missing_rest": missing_rest,
            "unacclimatized": unaccl, "crew_harsh_hours": fairness, "feasible": feasible,
            "label": "SIMULATION"}


def _q_label(q: int) -> str:
    t = 5 * 60 + 15 * q
    return f"{t // 60:02d}:{t % 60:02d}"


def draft_to_plan(world: dict[str, Any]) -> dict[str, Any]:
    """Turn the supervisor's draft (start times) into the twin's plan format."""
    tasks = []
    for t in world["plan_tomorrow"]["tasks"]:
        s0 = hhmm_to_slot(t["draft_start"])
        n = t["duration_min"] // SLOT_MIN
        tasks.append({**t, "slots": [s for s in range(s0, s0 + n) if 0 <= s < SLOTS]})
    breaks = []
    for b in world["plan_tomorrow"]["breaks"]:
        start_q = (int(b["start"][:2]) * 60 + int(b["start"][3:5]) - 300) // 15
        breaks.append({"crews": b["crews"], "start_q": start_q, "quarters": b["minutes"] // 15,
                       "rest_area": b["rest_area"]})
    return {"tasks": tasks, "breaks": breaks, "assignments": {}}
