"""Scenario Lab and shift simulator (programme feedback, November 2026).

A reviewer enters sample workers, weather and tasks; the same engines as the site plan re-plan the day:

1. Weather to heat: the hourly weather is turned into WBGT for each work spot and rest area (Liljegren
   method via ECMWF thermofeel, a clear-sky sun model and the sky the reviewer chose). Planning uses the
   conservative upper end of the 90% band, as for the site forecast.
2. Break planner (workrest.py): for every crew and hour, the shortest shaded break that keeps the hour within
   the ISO 7243 / NIOSH limit for that job, with the rule pack's band minimum as a floor.
3. Plan (CP-SAT): when each crew works and rests. Net working time is counted (breaks are not work), rest
   seats are shared per 15 minutes, new workers keep to their acclimatization allowance and move to shaded
   work in hours their crew's breaks would not protect them, the midday break and the withdrawal band are
   never relaxed.
4. Independent re-check: the rule engine re-checks every worker and slot (certificate.revalidate) and every
   crew-hour is re-checked against the limit as planned. A plan that fails is never shown as valid.
5. Alerts: what each named worker's phone says, in the worker's language.

The shift simulator re-plans from "now": the past is frozen, conditions change only from the moment they
are reported, and the new plan is compared with the old one. Everything is stateless and synthetic: nothing
the reviewer enters is stored. No AI is used here.
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import thermofeel
from ortools.sat.python import cp_model

from ..core import policy
from ..forecast.service import SIGMA, Z90, band_of
from ..forecast.wbgt import cos_solar_zenith
from . import certificate as cert
from . import workrest
from .twin import REST_MIN, SLOT_MIN, SLOTS, heat_allowance_min, hhmm_to_slot, simulate, slot_label

LAT, LON = 24.45, 54.38
SEASONS = {"summer": "2026-08-19", "autumn": "2026-11-04"}
PRESSURE_HPA = 1005.0
COOLED_ROOM = {"t": 25.0, "rh": 45.0, "wind": 0.3}
HI_MARGIN = round(Z90 * SIGMA, 2)          # the planning value is the upper end of the 90% band
EXPOSURE = {
    "sun": {"outdoor": True, "direct_sun": True, "shade_fraction": 0.0},
    "partial": {"outdoor": True, "direct_sun": True, "shade_fraction": 0.5},
    "shade": {"outdoor": True, "direct_sun": False, "shade_fraction": 1.0},
    "indoor": {"outdoor": False, "direct_sun": False, "shade_fraction": 1.0},
}
SKY = {"clear": (1.0, 0.78), "haze": (0.85, 0.5), "cloud": (0.6, 0.3)}   # (sunshine factor, direct share)
LIMITS = {"tasks": 6, "workers": 12, "rest_areas": 3, "crew_size": 30, "events": 24}
EVENT_TYPES = ("hotter", "humid", "calm", "cloud", "water_out", "ac_fails", "symptom", "wearable")
WATER_RESTORE_SLOTS = 1     # the plan assumes water is back within 30 minutes (the task deadline is 10)
WEARABLE_REST_SLOTS = 1     # a worker's own device asks for a 30-minute shaded break
TIME_LIMIT_S = 1.0


class LabError(ValueError):
    """A scenario the lab refuses, with a plain-language reason."""


# ------------------------------------------------------------------ presets
def presets() -> list[dict[str, Any]]:
    """Ready-made scenarios. Fictional names; English and Arabic only."""
    summer = {
        "id": "summer_site", "title": "Abu Dhabi site, August", "title_ar": "موقع في أبوظبي، أغسطس",
        "season": "summer",
        "weather": {"peak_c": 42, "humidity_pct": 30, "wind_ms": 3.5, "sky": "haze"},
        "rest_areas": [
            {"id": "R1", "name": "Cooled cabin", "type": "cooled", "seats": 14},
            {"id": "R2", "name": "Shade tent", "type": "shade", "seats": 10},
        ],
        "shaded_places": 3,
        "tasks": [
            {"id": "T1", "name": "Slab pour, level 4", "exposure": "sun", "workload": "heavy", "clothing": "work_clothes",
             "hours": 2, "start": "05:00", "end": "19:00", "crew_size": 8, "rest_area": "R1", "walk_min": 2,
             "one_piece": True, "can_wait": False},
            {"id": "T2", "name": "Rebar tying", "exposure": "partial", "workload": "moderate",
             "clothing": "work_clothes", "hours": 4, "start": "05:00", "end": "19:00", "crew_size": 6,
             "rest_area": "R1", "walk_min": 3, "one_piece": False, "can_wait": True},
            {"id": "T3", "name": "Blockwork under canopy", "exposure": "shade", "workload": "moderate",
             "clothing": "work_clothes", "hours": 4, "start": "06:00", "end": "18:00", "crew_size": 5,
             "rest_area": "R2", "walk_min": 2, "one_piece": False, "can_wait": True},
            {"id": "T4", "name": "Spray painting, stairwell", "exposure": "indoor", "workload": "light",
             "clothing": "coveralls", "hours": 4, "start": "06:00", "end": "17:00", "crew_size": 3,
             "rest_area": "R2", "walk_min": 2, "one_piece": False, "can_wait": True},
        ],
        "workers": [
            {"id": "P1", "name": "Ravi", "lang": "en", "task": "T2", "status": "new", "day": 2},
            {"id": "P2", "name": "Anwar", "lang": "ar", "task": "T1", "status": "acclimatized", "day": 400,
             "age": 41, "wearable": True, "share_status": True},
            {"id": "P3", "name": "Imran", "lang": "en", "task": "T3", "status": "returning", "day": 3},
            {"id": "P4", "name": "Khaled", "lang": "ar", "task": "T1", "status": "acclimatized", "day": 300,
             "restriction": "shaded_light_duty"},
        ],
    }
    humid = {
        **summer, "id": "humid_morning", "title": "Humid coastal day, September",
        "title_ar": "يوم ساحلي رطب، سبتمبر",
        "weather": {"peak_c": 39, "humidity_pct": 45, "wind_ms": 2.0, "sky": "haze"},
    }
    autumn = {
        **summer, "id": "autumn_day", "title": "Mild day, November", "title_ar": "يوم معتدل، نوفمبر",
        "season": "autumn",
        "weather": {"peak_c": 31, "humidity_pct": 45, "wind_ms": 3.5, "sky": "clear"},
    }
    return [summer, humid, autumn]


# ------------------------------------------------------------------ validation
def _hhmm(v: str, field: str) -> str:
    if not isinstance(v, str) or len(v) != 5 or v[2] != ":" or not (v[:2] + v[3:]).isdigit():
        raise LabError(f"{field} must be a time like 06:30")
    h, m = int(v[:2]), int(v[3:])
    if m not in (0, 30) or not (5 <= h <= 19) or (h == 19 and m):
        raise LabError(f"{field} must be between 05:00 and 19:00, on the hour or half hour")
    return v


def normalise(sc: dict[str, Any]) -> dict[str, Any]:
    """Semantic checks with plain-language reasons (types and lengths are checked by the API model)."""
    if sc.get("season") not in SEASONS:
        raise LabError("season must be summer or autumn")
    wx = sc.get("weather") or {}
    if not (25 <= float(wx.get("peak_c", 0)) <= 50):
        raise LabError("Peak air temperature must be between 25 and 50 °C")
    if not (10 <= float(wx.get("humidity_pct", 0)) <= 90):
        raise LabError("Humidity at the hottest hour must be between 10 and 90%")
    if not (0.5 <= float(wx.get("wind_ms", 0)) <= 10):
        raise LabError("Wind must be between 0.5 and 10 m/s")
    if wx.get("sky") not in SKY:
        raise LabError("sky must be clear, haze or cloud")
    rest = sc.get("rest_areas") or []
    tasks = sc.get("tasks") or []
    workers = sc.get("workers") or []
    if not rest or len(rest) > LIMITS["rest_areas"]:
        raise LabError(f"Add between 1 and {LIMITS['rest_areas']} rest areas")
    if not tasks or len(tasks) > LIMITS["tasks"]:
        raise LabError(f"Add between 1 and {LIMITS['tasks']} tasks")
    if len(workers) > LIMITS["workers"]:
        raise LabError(f"Follow at most {LIMITS['workers']} named workers")
    rids = [r["id"] for r in rest]
    tids = [t["id"] for t in tasks]
    if len(set(rids)) != len(rids) or len(set(tids)) != len(tids):
        raise LabError("Each rest area and task needs its own id")
    for r in rest:
        if r.get("type") not in ("cooled", "shade") or not (0 <= int(r.get("seats", -1)) <= 60):
            raise LabError("A rest area is cooled or shade, with 0 to 60 seats")
    named_per_task: dict[str, int] = {}
    for w in workers:
        if w.get("task") not in tids:
            raise LabError(f"{w.get('name', 'A worker')} is on a task that does not exist")
        if w.get("status") not in ("new", "returning", "acclimatized"):
            raise LabError("Status must be new, returning or acclimatized")
        if w.get("lang") not in ("en", "ar"):
            raise LabError("Language must be English or Arabic")
        if w.get("restriction") not in (None, "", "shaded_light_duty", "no_heat_work"):
            raise LabError("Unknown work restriction")
        named_per_task[w["task"]] = named_per_task.get(w["task"], 0) + 1
    for t in tasks:
        if t.get("exposure") not in EXPOSURE:
            raise LabError("Sun exposure must be sun, partial, shade or indoor")
        if t.get("workload") not in ("light", "moderate", "heavy"):
            raise LabError("Workload must be light, moderate or heavy")
        if t.get("clothing") not in workrest.CLOTHING_CAF:
            raise LabError("Unknown clothing")
        if t.get("rest_area") not in rids:
            raise LabError(f"{t['name']}: choose one of the rest areas")
        _hhmm(t.get("start", ""), "Start")
        _hhmm(t.get("end", ""), "End")
        if hhmm_to_slot(t["end"]) <= hhmm_to_slot(t["start"]):
            raise LabError(f"{t['name']}: the end must be after the start")
        hours = float(t.get("hours", 0))
        if not (0.5 <= hours <= 10) or abs(hours * 4 - round(hours * 4)) > 1e-9:
            raise LabError(f"{t['name']}: working time is 0.5 to 10 hours, in quarter hours")
        size = int(t.get("crew_size", 0))
        if not (1 <= size <= LIMITS["crew_size"]):
            raise LabError(f"{t['name']}: a crew has 1 to {LIMITS['crew_size']} workers")
        if named_per_task.get(t["id"], 0) > size:
            raise LabError(f"{t['name']}: more named workers than the crew size")
        if not (0 <= float(t.get("walk_min", 0)) <= 10):
            raise LabError(f"{t['name']}: the walk to the rest area is 0 to 10 minutes")
    if not (0 <= int(sc.get("shaded_places", 0)) <= 20):
        raise LabError("Shaded work places must be 0 to 20")
    return sc


# ------------------------------------------------------------------ weather to heat
def _slot_mid_local(day: str, i: int) -> datetime:
    return datetime.fromisoformat(f"{day}T05:00:00+04:00") + timedelta(minutes=SLOT_MIN * i + 15)


def _magnus_dewpoint(t: float, rh: float) -> float:
    b, c = 17.62, 243.12
    g = math.log(max(1.0, rh) / 100.0) + b * t / (c + t)
    return c * g / (b - g)


def _rh_from_dewpoint(t: float, td: float) -> float:
    b, c = 17.62, 243.12
    return max(5.0, min(100.0, 100.0 * math.exp(b * td / (c + td) - b * t / (c + t))))


def weather_series(sc: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Air temperature, humidity, wind and sun for each half-hour slot, with reported changes applied from
    the slot they were reported in. The dew point is held through the day (humidity falls as it warms)."""
    day = SEASONS[sc["season"]]
    wx = sc["weather"]
    peak = float(wx["peak_c"])
    span = 9.0 if sc["season"] == "summer" else 8.0
    tmin = peak - span
    td0 = _magnus_dewpoint(peak, float(wx["humidity_pct"]))
    out = []
    for i in range(SLOTS):
        mid = _slot_mid_local(day, i)
        tau = mid.hour + mid.minute / 60.0
        if tau <= 14.5:
            t = tmin + (peak - tmin) * (1 - math.cos(math.pi * (tau - 5.0) / 9.5)) / 2.0
        else:
            t = peak - 0.6 * (tau - 14.5)
        rec = {"slot": i, "time": slot_label(i), "t": t, "td": td0, "wind": float(wx["wind_ms"]), "sky": wx["sky"]}
        for ev in events:
            if hhmm_to_slot(ev["at"]) > i:
                continue
            if ev["type"] == "hotter":
                rec["t"] += 3.0
            elif ev["type"] == "humid":
                rec["td"] += 4.0
            elif ev["type"] == "calm":
                rec["wind"] = 0.5
            elif ev["type"] == "cloud":
                rec["sky"] = "cloud"
        rec["td"] = min(rec["td"], rec["t"] - 0.5)
        rec["rh"] = _rh_from_dewpoint(rec["t"], rec["td"])
        cosz = cos_solar_zenith(mid.astimezone(timezone.utc), LAT, LON)
        sun, share = SKY[rec["sky"]]
        ghi = sun * 1098.0 * cosz * math.exp(-0.057 / cosz) if cosz > 0.02 else 0.0
        rec.update({"cosz": round(cosz, 4), "ghi": round(ghi, 1), "direct": round(ghi * share, 1)})
        rec["t"], rec["rh"] = round(rec["t"], 2), round(rec["rh"], 1)
        out.append(rec)
    return out


def _liljegren(t: np.ndarray, rh: np.ndarray, wind: np.ndarray, ssrd: np.ndarray, fdir: np.ndarray,
               cosz: np.ndarray) -> np.ndarray:
    tk = t + 273.15
    p = np.full_like(t, PRESSURE_HPA)
    val = thermofeel.calculate_wbgt_liljegren(tk, np.clip(rh, 1, 100), p, np.maximum(wind, 0.1), np.maximum(ssrd, 0),
                                              fdir, np.maximum(cosz, 0)) - 273.15
    bad = np.isnan(val)
    if bad.any():
        simple = thermofeel.calculate_wbgt_simple(tk, np.clip(rh, 1, 100)) - 273.15
        val = np.where(bad, simple, val)
    return val


def heat_grid(wx: list[dict[str, Any]]) -> dict[str, list[float]]:
    """Point WBGT per slot for full sun, full shade, a still indoor space and a cooled room."""
    t = np.array([r["t"] for r in wx], dtype=float)
    rh = np.array([r["rh"] for r in wx], dtype=float)
    wind = np.array([r["wind"] for r in wx], dtype=float)
    ghi = np.array([r["ghi"] for r in wx], dtype=float)
    direct = np.array([r["direct"] for r in wx], dtype=float)
    cosz = np.array([r["cosz"] for r in wx], dtype=float)
    fdir = np.where(ghi > 1, np.clip(direct / np.maximum(ghi, 1), 0, 0.9), 0.0)
    sun = _liljegren(t, rh, wind, ghi, fdir, cosz)
    diffuse = np.maximum(0.0, ghi - direct) * 0.6
    shade = _liljegren(t, rh, wind, diffuse, np.zeros_like(t), cosz)
    indoor = _liljegren(t + 1.0, rh, np.full_like(t, 0.5), np.zeros_like(t), np.zeros_like(t), cosz)
    cool = _liljegren(np.array([COOLED_ROOM["t"]]), np.array([COOLED_ROOM["rh"]]), np.array([COOLED_ROOM["wind"]]),
                      np.zeros(1), np.zeros(1), np.zeros(1))[0]
    return {"sun": [round(float(v), 2) for v in sun], "shade": [round(float(v), 2) for v in shade],
            "indoor": [round(float(v), 2) for v in indoor], "cooled": round(float(cool), 2)}


def spot_wbgt(heat: dict[str, Any], exposure: str, i: int) -> float:
    if exposure == "indoor":
        return heat["indoor"][i]
    f = EXPOSURE[exposure]["shade_fraction"]
    return round(f * heat["shade"][i] + (1 - f) * heat["sun"][i], 2)


def rest_slots_wbgt(heat: dict[str, Any], rest_area: dict[str, Any], slots: list[int], ac_failed: bool) -> float:
    """WBGT at a rest area over some slots: a working cooled room is controlled; a shade tent (or a cooled
    room whose air conditioning failed) follows the outdoor shade, at the planning value."""
    if rest_area["cooled"] and not ac_failed:
        return heat["cooled"]
    return round(max(heat["shade"][s] for s in slots) + HI_MARGIN, 2)


def rest_hour_wbgt(heat: dict[str, Any], rest_area: dict[str, Any], h: int, ac_failed: bool) -> float:
    return rest_slots_wbgt(heat, rest_area, [2 * h, 2 * h + 1], ac_failed)


# ------------------------------------------------------------------ world
def build_world(sc: dict[str, Any]) -> dict[str, Any]:
    """The lab scenario in the site plan's world format: one work spot and one crew per task. Crew members
    who are not named are acclimatized and unrestricted."""
    day = SEASONS[sc["season"]]
    zones, crews, tasks, workers = [], [], [], []
    rest_areas = [{"id": r["id"], "name": r["name"], "seats": int(r["seats"]), "cooled": r["type"] == "cooled",
                   "type": r["type"], "working": True, "accessible": True, "open": "05:00", "close": "19:00"}
                  for r in sc["rest_areas"]]
    for t in sc["tasks"]:
        e = EXPOSURE[t["exposure"]]
        zones.append({"id": t["id"], "name": t["name"], **e, "exposure": t["exposure"], "rest_area": t["rest_area"],
                      "walk_min": float(t.get("walk_min", 3))})
        crews.append({"id": t["id"], "name": t["name"], "zone": t["id"], "size": int(t["crew_size"])})
        tasks.append({"id": t["id"], "name": t["name"], "zone": t["id"], "crew": t["id"], "workload": t["workload"],
                      "outdoor": e["outdoor"], "draft_start": t["start"], "duration_min": int(round(t["hours"] * 60)),
                      "contiguous": bool(t.get("one_piece")), "earliest": t["start"], "latest_end": t["end"],
                      "deferrable": bool(t.get("can_wait")), "clothing": t["clothing"]})
    for w in sc.get("workers", []):
        workers.append({"id": w["id"], "name": w["name"], "lang": w["lang"], "crew": w["task"],
                        "acclimatization": w["status"], "day": int(w.get("day") or 1),
                        "restriction": w.get("restriction") or None, "named": True,
                        "wearable": bool(w.get("wearable")), "share_status": bool(w.get("share_status")),
                        "age": w.get("age")})
    for c in crews:
        have = sum(1 for w in workers if w["crew"] == c["id"])
        for k in range(c["size"] - have):
            workers.append({"id": f"{c['id']}-{k + 1:02d}", "name": f"{c['name']} worker {k + 1}", "lang": "en",
                            "crew": c["id"], "acclimatization": "acclimatized", "day": 365, "restriction": None,
                            "named": False})
    return {"site": {"id": "lab", "name": "Scenario Lab (synthetic)", "policy_packs": ["AE-AD-HEAT@0.1.1-demo",
                                                                                      "AE-FED-MIDDAY@2026.1-demo"]},
            "day": day, "zones": zones, "rest_areas": rest_areas, "crews": crews, "workers": workers,
            "shaded_task": {"capacity": int(sc.get("shaded_places", 0))},
            "plan_tomorrow": {"date": day, "tasks": tasks, "breaks": []}}


def build_grid(world: dict[str, Any], heat: dict[str, Any]) -> dict[str, Any]:
    day = world["day"]
    mpack = policy.midday_pack()
    g: dict[str, Any] = {"zones": {}, "midday": [], "day": day}
    for i in range(SLOTS):
        g["midday"].append(policy.in_midday_window(_slot_mid_local(day, i), mpack))
    for z in world["zones"]:
        rows = []
        for i in range(SLOTS):
            pt = spot_wbgt(heat, z["exposure"], i)
            hi = round(pt + HI_MARGIN, 2)
            rows.append({"slot": i, "time": slot_label(i), "wbgt_point": pt, "wbgt_hi": hi, "band": band_of(hi)})
        g["zones"][z["id"]] = rows
    return g


# ------------------------------------------------------------------ events
def _ev_slot(ev: dict[str, Any]) -> int:
    return hhmm_to_slot(ev["at"])


def ac_failed_from(events: list[dict[str, Any]], rid: str) -> int | None:
    s = [_ev_slot(e) for e in events if e["type"] == "ac_fails" and e.get("target") == rid]
    return min(s) if s else None


def water_out_slots(events: list[dict[str, Any]], tid: str) -> set[int]:
    out: set[int] = set()
    for e in events:
        if e["type"] == "water_out" and e.get("target") == tid:
            s = _ev_slot(e)
            out.update(range(s, min(SLOTS, s + WATER_RESTORE_SLOTS)))
    return out


def personal_events(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per worker: from which slot heat work stops for the day (a symptom) and which slots are a break their
    own device asked for."""
    out: dict[str, dict[str, Any]] = {}
    for e in events:
        if e["type"] not in ("symptom", "wearable"):
            continue
        p = out.setdefault(e["target"], {"stop_from": None, "rest_slots": set()})
        s = _ev_slot(e)
        if e["type"] == "symptom":
            p["stop_from"] = s if p["stop_from"] is None else min(p["stop_from"], s)
        else:
            p["rest_slots"].update(range(s, min(SLOTS, s + WEARABLE_REST_SLOTS)))
    return out


# ------------------------------------------------------------------ break planner per crew-hour
def crew_hour_needs(world: dict[str, Any], g: dict[str, Any], heat: dict[str, Any],
                    events: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    zones = {z["id"]: z for z in world["zones"]}
    rest = {r["id"]: r for r in world["rest_areas"]}
    out: dict[tuple[str, int], dict[str, Any]] = {}
    for t in world["plan_tomorrow"]["tasks"]:
        z = zones[t["zone"]]
        r = rest[z["rest_area"]]
        failed = ac_failed_from(events, r["id"])
        for h in range(SLOTS // 2):
            s0, s1 = 2 * h, 2 * h + 1
            work = max(g["zones"][t["zone"]][s0]["wbgt_hi"], g["zones"][t["zone"]][s1]["wbgt_hi"])
            ac_off = failed is not None and failed <= s1
            rst = rest_hour_wbgt(heat, r, h, ac_off)
            band = max((g["zones"][t["zone"]][s]["band"] for s in (s0, s1)), key=lambda b: policy.BAND_RANK.get(b, 9))
            floor_q = workrest.floor_quarters(REST_MIN.get(band, 0)) if (t["outdoor"] or z["direct_sun"]) else 0
            acc = workrest.rest_needed(work, rst, t["workload"], True, t["clothing"], z["walk_min"])
            una = workrest.rest_needed(work, rst, t["workload"], False, t["clothing"], z["walk_min"])
            full_q = max(acc["quarters"], floor_q) if acc["workable"] else 4
            out[(t["crew"], h)] = {"full_q": full_q, "floor_q": floor_q, "workable": acc["workable"],
                                   "iso": acc, "iso_new": una,
                                   "new_q": max(una["quarters"], floor_q) if una["workable"] else 4,
                                   "wbgt_work": work, "wbgt_rest": rst, "band": band, "ac_failed": ac_off}
    return out


def _one_slot_q(n: dict[str, Any]) -> int:
    """Break quarters inside a single worked slot when the other half of the hour is not worked (counted as
    rest): what the limit still needs, and at least the band minimum's one break."""
    return max(1 if n["floor_q"] else 0, n["full_q"] - 2)


# ------------------------------------------------------------------ plan (CP-SAT)
def _model(world: dict[str, Any], g: dict[str, Any], need: dict[tuple[str, int], dict[str, Any]],
           events: list[dict[str, Any]], now_slot: int, previous: dict[str, Any] | None,
           relax: set[str] | None = None):
    relax = relax or set()
    zones = {z["id"]: z for z in world["zones"]}
    crews = {c["id"]: c for c in world["crews"]}
    rest = {r["id"]: r for r in world["rest_areas"]}
    tasks = world["plan_tomorrow"]["tasks"]
    personal = personal_events(events)
    prev_x: dict[str, set[int]] = {}
    prev_b: dict[str, set[int]] = {}
    prev_y: dict[str, set[int]] = {}
    if previous:
        for t in previous.get("tasks", []):
            prev_x[t["id"]] = set(t.get("slots") or [])
        for b in previous.get("breaks", []):
            for q in range(b["start_q"], b["start_q"] + b.get("quarters", 1)):
                prev_b.setdefault(b["crew"], set()).add(q)
        for wid, a in (previous.get("assignments") or {}).items():
            prev_y[wid] = set(a.get("heat_slots") or [])
    frozen = previous is not None and now_slot > 0
    m = cp_model.CpModel()
    x: dict[tuple[str, int], Any] = {}
    deferred: dict[str, Any] = {}
    starts: dict[str, list] = {}
    bq: dict[tuple[str, int], Any] = {}
    net_terms: dict[str, list] = {}
    for t in tasks:
        z = zones[t["zone"]]
        lo, hi = max(0, hhmm_to_slot(t["earliest"])), min(SLOTS, hhmm_to_slot(t["latest_end"]))
        dry = water_out_slots(events, t["id"])
        for s in range(SLOTS):
            v = m.NewBoolVar(f"x_{t['id']}_{s}")
            x[(t["id"], s)] = v
            if frozen and s < now_slot:
                m.Add(v == (1 if s in prev_x.get(t["id"], set()) else 0))
                continue
            band = g["zones"][t["zone"]][s]["band"]
            h = s // 2
            forbidden = (s < lo or s >= hi or band in ("withdrawal", "unavailable")
                         or (t["outdoor"] and z["direct_sun"] and g["midday"][s])
                         or not need[(t["crew"], h)]["workable"] or s in dry)
            if forbidden:
                m.Add(v == 0)
        # Break quarters per hour, net working quarters, one contiguous break per hour.
        for h in range(SLOTS // 2):
            n = need[(t["crew"], h)]
            w0, w1 = x[(t["id"], 2 * h)], x[(t["id"], 2 * h + 1)]
            qs = [m.NewBoolVar(f"b_{t['id']}_{h}_{q}") for q in range(4)]
            for q in range(4):
                bq[(t["crew"], 4 * h + q)] = qs[q]
                m.AddImplication(qs[q], x[(t["id"], 2 * h + q // 2)])
            past = [q for q in range(4) if frozen and (2 * h + q // 2) < now_slot]
            a, b1 = n["full_q"], _one_slot_q(n)
            done_rest = sum(1 for q in past if (4 * h + q) in prev_b.get(t["crew"], set()))
            if len(past) == 2 and 2 * h in prev_x.get(t["id"], set()) and done_rest == 0 and (a > 0 or n["floor_q"]):
                # The crew worked the first half of this hour with its break still to come. If it now stops at the
                # half hour, it takes that break in the rest area straight away (counted in the seats, not as work).
                stop_rest = m.NewBoolVar(f"sr_{t['id']}_{h}")
                m.Add(stop_rest == 1).OnlyEnforceIf(w1.Not())
                m.Add(stop_rest == 0).OnlyEnforceIf(w1)
                bq[(t["crew"], 4 * h + 2)] = qs[2] + stop_rest
            sq = [m.NewBoolVar(f"bs_{t['id']}_{h}_{q}") for q in range(4)]
            m.Add(sq[0] >= qs[0])
            for q in range(1, 4):
                m.Add(sq[q] >= qs[q] - qs[q - 1])
            m.Add(sum(sq) <= 1)
            for q in past:
                pinned = (4 * h + q) in prev_b.get(t["crew"], set())
                if pinned and (2 * h + q // 2) not in prev_x.get(t["id"], set()):
                    # A break the crew took after stopping at the half hour: history, kept as it happened.
                    m.Add(qs[q] == 0)
                    bq[(t["crew"], 4 * h + q)] = qs[q] + 1
                else:
                    m.Add(qs[q] == (1 if pinned else 0))
            both = m.NewBoolVar(f"both_{t['id']}_{h}")
            m.Add(both <= w0)
            m.Add(both <= w1)
            m.Add(both >= w0 + w1 - 1)
            one = w0 + w1 - 2 * both
            if len(past) == 2 and a < 4:
                # The first half of this hour has happened: the second half only adds what is still missing.
                if 2 * h in prev_x.get(t["id"], set()):
                    extra = max(0, a - done_rest)
                    if extra > 2:
                        m.Add(w1 == 0)
                    m.Add(qs[2] + qs[3] >= extra).OnlyEnforceIf(w1)
                else:
                    if b1 > 2:
                        m.Add(w1 == 0)
                    m.Add(qs[2] + qs[3] == b1).OnlyEnforceIf(w1)
                m.Add(qs[2] + qs[3] == 0).OnlyEnforceIf(w1.Not())
            elif len(past) < 2:
                if a >= 4:
                    m.Add(w0 == 0)
                    m.Add(w1 == 0)
                if b1 > 2:
                    m.Add(one == 0)
                m.Add(sum(qs) == a * both + b1 * one)
            net_terms.setdefault(t["id"], []).append(2 * (w0 + w1) - sum(qs))
        req_q = t["duration_min"] // 15
        d = m.NewIntVar(0, req_q, f"def_{t['id']}")
        deferred[t["id"]] = d
        m.Add(sum(net_terms[t["id"]]) + d == req_q)
        if not t.get("deferrable") and "deferral" not in relax:
            m.Add(d == 0)
        st = [m.NewBoolVar(f"st_{t['id']}_{s}") for s in range(SLOTS)]
        for s in range(SLOTS):
            prev = x[(t["id"], s - 1)] if s > 0 else 0
            m.Add(st[s] >= x[(t["id"], s)] - prev)
        if t.get("contiguous"):
            m.Add(sum(st) <= 1)
            started = frozen and any(s in prev_x.get(t["id"], set()) for s in range(now_slot))
            if not started:
                # Not begun: all of it in one go, or none of it today.
                done = m.NewBoolVar(f"done_{t['id']}")
                m.Add(d == 0).OnlyEnforceIf(done)
                m.Add(sum(x[(t["id"], s)] for s in range(SLOTS)) == 0).OnlyEnforceIf(done.Not())
            # Already begun: it continues without a gap; if it cannot finish safely, the rest may wait only when
            # the supervisor allows it (for a pour, a planned construction joint).
        else:
            m.Add(sum(st) <= 2)
        starts[t["id"]] = st

    # Named workers scheduled one by one: new and returning workers, clinician labels and personal events.
    y: dict[tuple[str, int], Any] = {}
    shaded_use: dict[int, list] = {s: [] for s in range(SLOTS)}
    personal_rest_seats: dict[tuple[str, int], int] = {}
    task_by_crew = {t["crew"]: t for t in tasks}
    indiv = [w for w in world["workers"] if w.get("named") and (policy.is_unacclimatized(w)
                                                                 or w.get("restriction") or w["id"] in personal)]
    for w in indiv:
        t = task_by_crew[w["crew"]]
        z = zones[t["zone"]]
        heat = bool(t["outdoor"] or z["direct_sun"])
        label = w.get("restriction")
        blocked = (label == "no_heat_work" and heat) or \
            (label == "shaded_light_duty" and (t["workload"] == "heavy" or z["direct_sun"]))
        unaccl = policy.is_unacclimatized(w)
        pe = personal.get(w["id"], {"stop_from": None, "rest_slots": set()})
        for s in range(SLOTS):
            v = m.NewBoolVar(f"y_{w['id']}_{s}")
            y[(w["id"], s)] = v
            m.AddImplication(v, x[(t["id"], s)])
            if frozen and s < now_slot and w["id"] in prev_y:
                m.Add(v == (1 if s in prev_y[w["id"]] else 0))
                continue
            band = g["zones"][t["zone"]][s]["band"]
            n = need[(t["crew"], s // 2)]
            stop = (blocked or (pe["stop_from"] is not None and s >= pe["stop_from"]) or s in pe["rest_slots"]
                    or (unaccl and heat and band in ("buffer", "withdrawal") and "unacclimatized" not in relax)
                    or (unaccl and not n["iso_new"]["workable"] and "unacclimatized" not in relax))
            if stop:
                m.Add(v == 0)
            elif not heat and not unaccl:
                m.Add(v == x[(t["id"], s)])
            off = m.NewBoolVar(f"off_{w['id']}_{s}")
            m.Add(off >= x[(t["id"], s)] - v)
            m.Add(off <= x[(t["id"], s)])
            m.Add(off <= 1 - v)
            if s in pe["rest_slots"] or (pe["stop_from"] is not None and s >= pe["stop_from"]):
                ra = z["rest_area"]
                for q in (2 * s, 2 * s + 1):
                    personal_rest_seats[(ra, q)] = personal_rest_seats.get((ra, q), 0) + 1
            else:
                shaded_use[s].append(off)
        if unaccl and "unacclimatized" not in relax:
            m.Add(sum(y[(w["id"], s)] for s in range(SLOTS)) <= heat_allowance_min(w) // SLOT_MIN)
            # Extra rest for a worker not yet acclimatized (the NIOSH RAL is lower than the crew's REL): in an hour
            # where the crew's breaks are not enough, this worker does heat work for at most the half hour the RAL
            # allows and spends the rest of the hour on shaded work (Hong Kong's guidance: +15 minutes an hour).
            # Indoor work that is not cooled counts too: the limit is about the heat, not about the sun.
            for h in range(SLOTS // 2):
                n = need[(t["crew"], h)]
                if not (n["iso_new"]["workable"] and n["new_q"] > n["full_q"]):
                    continue
                allowed = (4 - n["new_q"]) // 2
                if not frozen or 2 * h >= now_slot:
                    m.Add(y[(w["id"], 2 * h)] + y[(w["id"], 2 * h + 1)] <= allowed)
                elif 2 * h + 1 >= now_slot:
                    done = 1 if 2 * h in prev_y.get(w["id"], set()) else 0
                    m.Add(y[(w["id"], 2 * h + 1)] <= max(0, allowed - done))
    for s, offs in shaded_use.items():
        if offs and "shaded_capacity" not in relax and not (frozen and s < now_slot):
            m.Add(sum(offs) <= world["shaded_task"]["capacity"])

    # Rest seats per 15 minutes (crews on break plus anyone resting on their own).
    if "rest_capacity" not in relax:
        for rid, r in rest.items():
            users = [c for c, t in task_by_crew.items() if zones[t["zone"]]["rest_area"] == rid]
            for qq in range(SLOTS * 2):
                if frozen and qq < 2 * now_slot:
                    continue
                terms = [crews[c]["size"] * bq[(c, qq)] for c in users]
                extra = personal_rest_seats.get((rid, qq), 0)
                if terms or extra:
                    m.Add(sum(terms) + extra <= (r["seats"] if r["working"] and r["accessible"] else 0))

    # Objectives, solved in order (each optimum is kept before the next).
    harsh_heavy, moderate, crew_harsh, rest_terms, disruption = [], [], {}, [], []
    for t in tasks:
        size = crews[t["crew"]]["size"]
        heat = bool(t["outdoor"] or zones[t["zone"]]["direct_sun"])
        terms = [x[(t["id"], s)] for s in range(SLOTS) if heat and g["zones"][t["zone"]][s]["band"] in
                 ("buffer", "withdrawal")]
        expr = size * sum(terms) if terms else 0
        (harsh_heavy if t["workload"] == "heavy" else moderate if t["workload"] == "moderate" else []).append(expr)
        ch = m.NewIntVar(0, size * SLOTS, f"ch_{t['crew']}")
        m.Add(ch == expr)
        crew_harsh[t["crew"]] = ch
        rest_terms += [size * bq[(t["crew"], q)] for q in range(SLOTS * 2)]
        d0 = hhmm_to_slot(t["draft_start"])
        disruption += [abs(s - d0) * starts[t["id"]][s] for s in range(SLOTS)]
        disruption.append(4 * sum(starts[t["id"]]))
        for h in range(SLOTS // 2):
            disruption += [(3 - q) * bq[(t["crew"], 4 * h + q)] for q in range(4)]
        if previous:
            old = prev_x.get(t["id"], set())
            for s in range(now_slot, SLOTS):
                disruption.append(6 * (x[(t["id"], s)] if s not in old else 1 - x[(t["id"], s)]))
    max_crew = m.NewIntVar(0, 100000, "max_crew_harsh")
    m.AddMaxEquality(max_crew, list(crew_harsh.values()) or [0])
    sizes = {t["id"]: crews[t["crew"]]["size"] for t in tasks}
    objectives = [
        ("harsh_exposure", sum(harsh_heavy) if harsh_heavy else 0),
        ("deferred_work", sum(sizes[k] * v for k, v in deferred.items())),
        ("rest_time", sum(rest_terms)),
        ("fairness", max_crew * 10 + (sum(moderate) if moderate else 0)),
        ("disruption", sum(disruption)),
        ("acclimatization_progress", -sum(y.values()) if y else 0),
    ]
    return m, x, y, bq, deferred, objectives, indiv


def solve(world, g, need, events, now_slot=0, previous=None, time_limit_s=TIME_LIMIT_S) -> dict[str, Any]:
    t0 = time.perf_counter()
    m, x, y, bq, deferred, objectives, indiv = _model(world, g, need, events, now_slot, previous)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = 4
    stages, status = [], None
    for name, obj in objectives:
        m.Minimize(obj)
        status = solver.Solve(m)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            break
        val = int(round(solver.ObjectiveValue()))
        stages.append({"objective": name, "value": val, "status": solver.StatusName(status)})
        m.Add(obj <= val)
        m.ClearHints()
        for v in list(x.values()) + list(bq.values()) + list(y.values()):
            if isinstance(v, cp_model.IntVar):
                m.AddHint(v, solver.Value(v))
    runtime = round(time.perf_counter() - t0, 2)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": "NO_FEASIBLE_PROTECTED_PLAN", "solver": {"engine": "cp-sat (OR-Tools)",
                "status": solver.StatusName(status), "runtime_s": runtime}, "stages": stages}
    tasks = []
    for t in world["plan_tomorrow"]["tasks"]:
        slots = [s for s in range(SLOTS) if solver.Value(x[(t["id"], s)])]
        tasks.append({**t, "slots": slots, "deferred_quarters": solver.Value(deferred[t["id"]])})
    breaks = []
    zones = {z["id"]: z for z in world["zones"]}
    for t in world["plan_tomorrow"]["tasks"]:
        qs = [q for q in range(SLOTS * 2) if solver.Value(bq[(t["crew"], q)])]
        run: list[int] = []
        for q in qs + [None]:
            # One break record per hour: a break never straddles two hours, so each hour's rest is counted
            # in that hour by every checker.
            if run and (q is None or q != run[-1] + 1 or q % 4 == 0):
                breaks.append({"crew": t["crew"], "crews": [t["crew"]], "start_q": run[0], "quarters": len(run),
                               "rest_area": zones[t["zone"]]["rest_area"]})
                run = []
            if q is not None:
                run.append(q)
    breaks.sort(key=lambda b: (b["start_q"], b["crew"]))
    assignments = {}
    task_by_crew = {t["crew"]: t for t in tasks}
    for w in indiv:
        t = task_by_crew[w["crew"]]
        heat_slots = [s for s in range(SLOTS) if solver.Value(y[(w["id"], s)])]
        assignments[w["id"]] = {"heat_slots": heat_slots, "shaded_slots": [s for s in t["slots"] if s not in heat_slots],
                                "allowance_min": heat_allowance_min(w)}
    return {"status": "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE",
            "solver": {"engine": "cp-sat (OR-Tools)", "status": solver.StatusName(status), "runtime_s": runtime},
            "stages": stages, "plan": {"tasks": tasks, "breaks": breaks, "assignments": assignments}}


LAB_REMEDIES = [
    ("deferral", "Let part of the work wait until tomorrow", "دع جزءاً من العمل ينتظر إلى الغد"),
    ("rest_capacity", "Add rest seats or a second rest area", "أضف مقاعد راحة أو مكان راحة ثانياً"),
    ("shaded_capacity", "Add shaded work places for workers coming off heat work",
     "أضف أماكن عمل مظللة للعمال الخارجين من العمل في الحر"),
]


def diagnose(world, g, need, events, now_slot, previous) -> dict[str, Any]:
    remedies = []
    for key, en, ar in LAB_REMEDIES:
        m, *_ = _model(world, g, need, events, now_slot, previous, relax={key})
        s = cp_model.CpSolver()
        s.parameters.max_time_in_seconds = 0.8
        s.parameters.num_search_workers = 4
        if s.Solve(m) in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            remedies.append({"remedy": key, "text": en, "text_ar": ar})
    if not remedies:
        remedies.append({"remedy": "reschedule", "text": "Move the work to cooler hours or another day, or move "
                         "the rest area closer and cooler", "text_ar": "انقل العمل إلى ساعات أبرد أو يوم آخر، أو "
                         "اجعل مكان الراحة أقرب وأبرد"})
    return {"permitted_remedies": remedies,
            "never_relaxed": ["midday_window", "withdrawal_band", "heat_limit", "clinician_restrictions"]}


# ------------------------------------------------------------------ independent re-check
def revalidate(world: dict[str, Any], g: dict[str, Any], plan: dict[str, Any], need: dict, heat: dict[str, Any],
               events: list[dict[str, Any]]) -> dict[str, Any]:
    """The site plan's rule-engine re-check, plus every worked crew-hour re-checked against the heat limit
    as planned (actual work and rest minutes), water outages and personal events."""
    base = cert.revalidate(world, g, plan, world["day"])
    violations = list(base["violations"])
    checks = base["checks"]
    zones = {z["id"]: z for z in world["zones"]}
    rest = {r["id"]: r for r in world["rest_areas"]}
    personal = personal_events(events)
    rest_quarters: dict[str, set[int]] = {}
    for b in plan["breaks"]:
        rest_quarters.setdefault(b["crew"], set()).update(range(b["start_q"], b["start_q"] + b["quarters"]))
    for t in plan["tasks"]:
        z = zones[t["zone"]]
        r = rest[z["rest_area"]]
        failed = ac_failed_from(events, r["id"])
        slots = set(t["slots"])
        rq_in_work = {q for q in rest_quarters.get(t["crew"], set()) if q // 2 in slots}
        dry = water_out_slots(events, t["id"])
        for s in slots & dry:
            violations.append({"task": t["id"], "slot": slot_label(s), "rule": "water_unavailable"})
        for h in range(SLOTS // 2):
            worked = [s for s in (2 * h, 2 * h + 1) if s in slots]
            if not worked:
                continue
            checks += 1
            work_min = 30 * len(worked) - 15 * sum(1 for q in range(4 * h, 4 * h + 4) if q in rq_in_work)
            # Judged on the conditions of the slots actually worked: a change reported later in the hour does
            # not rewrite what already happened.
            wbgt_work = max(g["zones"][t["zone"]][s]["wbgt_hi"] for s in worked)
            ac_off = failed is not None and failed <= max(worked)
            wbgt_rest = rest_slots_wbgt(heat, r, worked, ac_off)
            res = workrest.check_hour(work_min, wbgt_work, wbgt_rest, t["workload"], True, t["clothing"],
                                      z["walk_min"])
            if not res["ok"]:
                violations.append({"crew": t["crew"], "hour": slot_label(2 * h), "rule": "heat_limit_iso7243",
                                   **res})
            for w in world["workers"]:
                if w["crew"] != t["crew"] or not w.get("named"):
                    continue
                a = (plan.get("assignments") or {}).get(w["id"])
                heat_here = [s for s in worked if (s in a["heat_slots"] if a else True)]
                if not heat_here:
                    continue
                pe = personal.get(w["id"])
                for s in heat_here:
                    if pe and (s in pe["rest_slots"] or (pe["stop_from"] is not None and s >= pe["stop_from"])):
                        violations.append({"worker": w["id"], "slot": slot_label(s), "rule": "personal_event"})
                if policy.is_unacclimatized(w):
                    # Judged on this worker's own heat time in the hour (the rest of the hour is shaded work or
                    # rest), at the conditions of the slots this worker actually worked.
                    checks += 1
                    wm = 30 * len(heat_here) - 15 * sum(1 for q in range(4 * h, 4 * h + 4)
                                                        if q in rq_in_work and q // 2 in heat_here)
                    wb_w = max(g["zones"][t["zone"]][s]["wbgt_hi"] for s in heat_here)
                    wb_r = rest_slots_wbgt(heat, r, heat_here, failed is not None and failed <= max(heat_here))
                    res2 = workrest.check_hour(wm, wb_w, wb_r, t["workload"], False, t["clothing"], z["walk_min"])
                    if not res2["ok"]:
                        violations.append({"worker": w["id"], "hour": slot_label(2 * h),
                                           "rule": "heat_limit_not_acclimatized", **res2})
    return {"engine": base["engine"] + "+workrest@1.0", "result": "valid" if not violations else "invalid",
            "checks": checks, "violations": violations}


# ------------------------------------------------------------------ the usual way of working
def usual_schedule(world: dict[str, Any]) -> dict[str, Any]:
    """A common fixed day for comparison: each task from its preferred start, one 15-minute break each hour,
    the same for everyone, nothing moved for heat."""
    tasks, breaks = [], []
    zones = {z["id"]: z for z in world["zones"]}
    for t in world["plan_tomorrow"]["tasks"]:
        s0 = hhmm_to_slot(t["draft_start"])
        gross_q = math.ceil(t["duration_min"] / 45 * 4)      # 45 working minutes per hour
        n = min(SLOTS - s0, math.ceil(gross_q / 2))
        slots = list(range(s0, s0 + n))
        tasks.append({**t, "slots": slots})
        for h in sorted({s // 2 for s in slots}):
            q = 4 * h + 3
            if q // 2 in slots:
                breaks.append({"crew": t["crew"], "crews": [t["crew"]], "start_q": q, "quarters": 1,
                               "rest_area": zones[t["zone"]]["rest_area"]})
    return {"tasks": tasks, "breaks": breaks, "assignments": {}}


# ------------------------------------------------------------------ alerts and summaries
def _ranges(slots: list[int]) -> list[str]:
    out, run = [], []
    for s in sorted(slots) + [None]:
        if run and (s is None or s != run[-1] + 1):
            out.append(f"{slot_label(run[0])}–{slot_label(run[-1] + 1)}")
            run = []
        if s is not None:
            run.append(s)
    return out


def _qlabel(q: int) -> str:
    m = 300 + 15 * q
    return f"{m // 60:02d}:{m % 60:02d}"


def worker_view(world: dict[str, Any], plan: dict[str, Any], w: dict[str, Any],
                events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    t = next(x for x in plan["tasks"] if x["crew"] == w["crew"])
    a = (plan.get("assignments") or {}).get(w["id"])
    heat_slots = a["heat_slots"] if a else t["slots"]
    pe = personal_events(events or []).get(w["id"])
    own_rest = set()
    if pe:
        own_rest = set(pe["rest_slots"]) | ({s for s in range(pe["stop_from"], SLOTS)} if pe["stop_from"] is not None
                                              else set())
    shaded = [s for s in (a["shaded_slots"] if a else []) if s not in own_rest]
    rest_area = next(r for r in world["rest_areas"] if r["id"] == next(z for z in world["zones"]
                                                                       if z["id"] == t["zone"])["rest_area"])
    brk = [b for b in plan["breaks"] if b["crew"] == w["crew"] and b["start_q"] // 2 in set(heat_slots)]
    return {"task": t["name"], "work": _ranges(heat_slots), "shaded": _ranges(shaded),
            "own_rest": _ranges(sorted(s for s in own_rest if s in set(t["slots"]))),
            "breaks": [{"from": _qlabel(b["start_q"]), "to": _qlabel(b["start_q"] + b["quarters"]),
                        "minutes": 15 * b["quarters"]} for b in brk],
            "rest_area": rest_area["name"], "heat_slots": heat_slots, "shaded_slots": shaded}


def worker_now(world: dict[str, Any], plan: dict[str, Any], w: dict[str, Any], now_slot: int, g: dict[str, Any],
               events: list[dict[str, Any]]) -> dict[str, Any]:
    """What the worker's phone says at the simulator's clock."""
    v = worker_view(world, plan, w, events)
    pe = personal_events(events).get(w["id"])
    q_now = 2 * now_slot
    if pe and pe["stop_from"] is not None and now_slot >= pe["stop_from"]:
        return {"state": "stop", "code": "symptom", "rest_area": v["rest_area"]}
    if pe and now_slot in pe["rest_slots"]:
        return {"state": "break", "code": "wearable", "until": slot_label(max(pe["rest_slots"]) + 1),
                "rest_area": v["rest_area"]}
    t = next(x for x in plan["tasks"] if x["crew"] == w["crew"])
    a = (plan.get("assignments") or {}).get(w["id"])
    at_spot = (now_slot - 1 in v["heat_slots"]) if a else True     # a worker on shaded work is not at that spot
    if now_slot in water_out_slots(events, t["id"]) and at_spot:
        return {"state": "stop", "code": "water", "rest_area": v["rest_area"]}
    for b in plan["breaks"]:
        if b["crew"] == w["crew"] and b["start_q"] <= q_now < b["start_q"] + b["quarters"] \
                and now_slot in v["heat_slots"]:
            return {"state": "break", "code": "planned", "until": _qlabel(b["start_q"] + b["quarters"]),
                    "rest_area": v["rest_area"]}
    if now_slot in v["heat_slots"]:
        return {"state": "work", "code": "heat_work", "band": g["zones"][t["zone"]][now_slot]["band"]}
    if now_slot in v["shaded_slots"]:
        return {"state": "shaded", "code": "shaded_work"}
    if g["midday"][now_slot] and t["outdoor"]:
        return {"state": "off", "code": "midday"}
    return {"state": "off", "code": "not_scheduled"}


def changes(old: dict[str, Any] | None, new: dict[str, Any], now_slot: int) -> list[dict[str, Any]]:
    """What changed from now on, per task: work slots and breaks."""
    if not old:
        return []
    out = []
    ob = {}
    for b in old.get("breaks", []):
        ob.setdefault(b["crew"], set()).update(range(b["start_q"], b["start_q"] + b["quarters"]))
    nb = {}
    for b in new.get("breaks", []):
        nb.setdefault(b["crew"], set()).update(range(b["start_q"], b["start_q"] + b["quarters"]))
    old_t = {t["id"]: set(t.get("slots") or []) for t in old.get("tasks", [])}
    for t in new["tasks"]:
        before = {s for s in old_t.get(t["id"], set()) if s >= now_slot}
        after = {s for s in t["slots"] if s >= now_slot}
        rb = {q for q in ob.get(t["crew"], set()) if q >= 2 * now_slot}
        ra = {q for q in nb.get(t["crew"], set()) if q >= 2 * now_slot}
        if before != after or rb != ra:
            out.append({"task": t["id"], "name": t["name"], "work_before": _ranges(sorted(before)),
                        "work_after": _ranges(sorted(after)), "rest_before_min": 15 * len(rb),
                        "rest_after_min": 15 * len(ra)})
    return out


def metrics(world: dict[str, Any], plan: dict[str, Any], need: dict) -> dict[str, Any]:
    crews = {c["id"]: c for c in world["crews"]}
    rest_q: dict[str, int] = {}
    for b in plan["breaks"]:
        rest_q[b["crew"]] = rest_q.get(b["crew"], 0) + b["quarters"]
    net = rest = deferred = required = scheduled = 0.0
    for t in plan["tasks"]:
        size = crews[t["crew"]]["size"]
        gross_h = len(t["slots"]) * 0.5
        rest_h = rest_q.get(t["crew"], 0) * 0.25
        net += (gross_h - rest_h) * size
        rest += rest_h * size
        scheduled += gross_h * size
        deferred += t.get("deferred_quarters", 0) * 0.25 * size
        required += t["duration_min"] / 60.0 * size
    water = 0.0
    zones = {z["id"]: z for z in world["zones"]}
    for t in plan["tasks"]:
        if t["outdoor"] or zones[t["zone"]]["direct_sun"]:
            water += 0.75 * len(t["slots"]) * 0.5 * crews[t["crew"]]["size"]
    return {"required_worker_hours": round(required, 1), "productive_worker_hours": round(net, 1),
            "rest_worker_hours": round(rest, 1), "deferred_worker_hours": round(deferred, 1),
            "rest_share_pct": round(100 * rest / scheduled, 1) if scheduled else 0.0,
            "water_litres": round(water)}


def need_table(world: dict[str, Any], plan: dict[str, Any], need: dict) -> list[dict[str, Any]]:
    """The break planner's reasoning for every worked hour (the 'why' behind each break)."""
    rest_q: dict[tuple[str, int], int] = {}
    for b in plan["breaks"]:
        for q in range(b["start_q"], b["start_q"] + b["quarters"]):
            rest_q[(b["crew"], q // 4)] = rest_q.get((b["crew"], q // 4), 0) + 1
    out = []
    for t in plan["tasks"]:
        for h in range(SLOTS // 2):
            worked = [s for s in (2 * h, 2 * h + 1) if s in t["slots"]]
            if not worked:
                continue
            n = need[(t["crew"], h)]
            out.append({"task": t["id"], "hour": slot_label(2 * h), "worked_min": 30 * len(worked),
                        "rest_min": 15 * rest_q.get((t["crew"], h), 0), "wbgt_work": n["wbgt_work"],
                        "wbgt_rest": n["wbgt_rest"], "band": n["band"], "floor_min": 15 * n["floor_q"],
                        "iso_rest_min": n["iso"]["rest_min"] if n["iso"]["workable"] else 60,
                        "limit": n["iso"]["limit"], "wbgt_avg": n["iso"]["wbgt_avg"], "m_avg": n["iso"]["m_avg"],
                        "new_worker_rest_min": n["iso_new"]["rest_min"] if n["iso_new"]["workable"] else 60,
                        "ac_failed": n["ac_failed"]})
    return out


def _public_grid(g: dict[str, Any], heat: dict[str, Any], world: dict[str, Any], events) -> dict[str, Any]:
    rest = {}
    for r in world["rest_areas"]:
        failed = ac_failed_from(events, r["id"])
        rest[r["id"]] = [heat["cooled"] if (r["cooled"] and (failed is None or s < failed))
                         else round(heat["shade"][s] + HI_MARGIN, 2) for s in range(SLOTS)]
    return {"zones": g["zones"], "midday": g["midday"], "day": g["day"], "rest_wbgt": rest,
            "sun": heat["sun"], "shade": heat["shade"], "cooled": heat["cooled"], "planning_margin_c": HI_MARGIN}


# ------------------------------------------------------------------ entry point
def run(sc: dict[str, Any], *, now: str | None = None, previous: dict[str, Any] | None = None,
        events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    t0 = time.perf_counter()
    sc = normalise(sc)
    events = sorted(events or [], key=lambda e: e["at"])
    if len(events) > LIMITS["events"]:
        raise LabError("Too many changes in one day; reset the simulation")
    task_ids = {t["id"] for t in sc["tasks"]}
    named = {w["id"] for w in sc.get("workers", [])}
    rest_ids = {r["id"] for r in sc["rest_areas"]}
    for e in events:
        _hhmm(e.get("at", ""), "Event time")
        if e.get("type") not in EVENT_TYPES:
            raise LabError("Unknown change")
        if e["type"] == "water_out" and e.get("target") not in task_ids:
            raise LabError("Water outage: choose a task")
        if e["type"] == "ac_fails" and e.get("target") not in rest_ids:
            raise LabError("Air conditioning failure: choose a rest area")
        if e["type"] in ("symptom", "wearable") and e.get("target") not in named:
            raise LabError("Choose one of the named workers")
    now_slot = hhmm_to_slot(_hhmm(now, "Now")) if now else 0
    if previous is not None:
        _check_previous(previous, task_ids)
    world = build_world(sc)
    wx = weather_series(sc, events)
    heat = heat_grid(wx)
    g = build_grid(world, heat)
    need = crew_hour_needs(world, g, heat, events)
    res = solve(world, g, need, events, now_slot, previous)
    out: dict[str, Any] = {"label": "SIMULATION", "synthetic": True, "day": world["day"], "now": slot_label(now_slot),
                           "weather": wx, "grid": _public_grid(g, heat, world, events),
                           "world": {k: world[k] for k in ("zones", "rest_areas", "crews")},
                           "named_workers": [w for w in world["workers"] if w.get("named")],
                           "solver": res["solver"], "stages": res.get("stages", []), "status": res["status"]}
    if res["status"] not in ("OPTIMAL", "FEASIBLE"):
        out["diagnosis"] = diagnose(world, g, need, events, now_slot, previous)
    else:
        plan = res["plan"]
        twin = simulate(world, g, plan)
        reval = revalidate(world, g, plan, need, heat, events)
        out.update({"plan": plan, "revalidation": reval, "metrics": metrics(world, plan, need),
                    "twin_metrics": {k: twin["metrics"][k] for k in ("heavy_harsh_worker_hours",
                                                                     "withdrawal_work_hours",
                                                                     "midday_violation_hours", "rest_conflicts")},
                    "why": need_table(world, plan, need),
                    "workers": [{"id": w["id"], "name": w["name"], "lang": w["lang"], "crew": w["crew"],
                                 "status": w["acclimatization"], "day": w["day"], "restriction": w.get("restriction"),
                                 "wearable": w.get("wearable", False), "share_status": w.get("share_status", False),
                                 "plan": worker_view(world, plan, w, events),
                                 "now": worker_now(world, plan, w, now_slot, g, events)}
                                for w in world["workers"] if w.get("named")],
                    "changes": changes(previous, plan, now_slot)})
    usual = usual_schedule(world)
    usual_check = revalidate(world, g, usual, need, heat, [])
    usual_twin = simulate(world, g, usual)["metrics"]
    vs = usual_check["violations"]
    um = metrics(world, usual, need)
    um["productive_worker_hours"] = min(um["productive_worker_hours"], um["required_worker_hours"])
    out["usual"] = {"plan": usual, "valid": not vs,
                    "crew_hours_over_limit": sum(1 for v in vs if v["rule"] == "heat_limit_iso7243"),
                    "new_worker_hours_over_limit": sum(1 for v in vs if v["rule"] == "heat_limit_not_acclimatized"),
                    "worker_slots_stopped_by_rules": sum(1 for v in vs if v["rule"] == "policy_state_stop"),
                    "midday_worker_hours": usual_twin["midday_violation_hours"],
                    "withdrawal_worker_hours": usual_twin["withdrawal_work_hours"],
                    "metrics": um}
    out["runtime_s"] = round(time.perf_counter() - t0, 2)
    out["method"] = {"limits": "ISO 7243:2017 / NIOSH 2016 REL and RAL", "sources": workrest.SOURCES,
                     "planning_value": f"upper end of the 90% band (+{HI_MARGIN} °C)",
                     "metabolic_w": workrest.METABOLIC_W, "clothing_adj": workrest.CLOTHING_CAF}
    return out


def _check_previous(previous: dict[str, Any], task_ids: set[str]) -> None:
    """The previous plan comes back from the browser: accept only its shape (it is only used to freeze the
    past, and the whole day is re-checked independently anyway)."""
    try:
        for t in previous.get("tasks", []):
            if t["id"] not in task_ids or any(not (0 <= int(s) < SLOTS) for s in t.get("slots", [])):
                raise LabError("The previous plan does not match this scenario; start the day again")
        for b in previous.get("breaks", []):
            if b["crew"] not in task_ids or not (0 <= int(b["start_q"]) < SLOTS * 2) or not (1 <= int(b["quarters"]) <= 4):
                raise LabError("The previous plan does not match this scenario; start the day again")
        for a in (previous.get("assignments") or {}).values():
            if any(not (0 <= int(s) < SLOTS) for s in a.get("heat_slots", [])):
                raise LabError("The previous plan does not match this scenario; start the day again")
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, LabError):
            raise
        raise LabError("The previous plan does not match this scenario; start the day again") from exc
