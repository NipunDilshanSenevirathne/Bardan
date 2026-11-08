"""Synthetic world generator (finalsystem.md §22.2).

Everything here is fictional and labelled SYNTHETIC: the site, people, tasks and
clinical fixtures. Weather comes from a replay of real past weather (NASA POWER,
Abu Dhabi, summer 2025) with derived per-zone WBGT. Instrument readings are
simulated from that weather with a demonstration WBGT-to-TWL mapping.

Languages: the prototype supports English and Arabic only.
"""
from __future__ import annotations

import copy
import random
from datetime import date as _date
from datetime import datetime, timedelta
from typing import Any

from ..forecast.model import actual as season_actual

TZ = "+04:00"
REPLAY_DAY = "2025-08-19"
EVENING_BEFORE = "2025-08-18"
SEED = 7

# Demonstration WBGT -> TWL mapping for simulated instruments (NOT official).
# Monotone: higher WBGT means lower (harsher) TWL. Consistent with the pack's
# demonstration WBGT planning bands: WBGT 28 ~ TWL 220, 31 ~ 140, 33 ~ 115.
TWL_POINTS = [(26.0, 250.0), (28.0, 220.0), (31.0, 140.0), (33.0, 115.0), (36.0, 80.0), (40.0, 40.0)]


def twl_from_wbgt_demo(wbgt: float) -> float:
    pts = TWL_POINTS
    if wbgt <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if wbgt <= x1:
            return y0 + (y1 - y0) * (wbgt - x0) / (x1 - x0)
    return pts[-1][1]


def zone_wbgt_at(day: str, hhmm: str, zone: str) -> float | None:
    """Derived WBGT for a zone at local HH:MM, interpolated between hourly
    records (records are stamped at HH:22, the mid-point of NASA POWER hours)."""
    d = _date.fromisoformat(day)
    t = int(hhmm[:2]) * 60 + int(hhmm[3:5])
    if t < 22:
        v0, v1 = season_actual(zone, d - timedelta(days=1), 23), season_actual(zone, d, 0)
        frac = (t + 60 - 22) / 60.0
    else:
        h0 = (t - 22) // 60
        v0 = season_actual(zone, d, h0)
        v1 = season_actual(zone, d, h0 + 1) if h0 + 1 <= 23 else season_actual(zone, d + timedelta(days=1), 0)
        frac = (t - (h0 * 60 + 22)) / 60.0
    if v0 is None and v1 is None:
        return None
    if v0 is None:
        return v1
    if v1 is None:
        return v0
    return round(v0 + (v1 - v0) * frac, 2)


# Names are fictional. Language preference is English or Arabic only.
WORKER_NAMES = [
    "Sohel Mia", "Bishnu Thapa", "Rajesh Yadav", "Jomar Santos", "Imran Khan", "Kamal Uddin",
    "Murugan Pandian", "Nuwan Perera", "Khaled Saeed", "Omar Nasser", "Faisal Ahmed", "Hari Gurung",
    "Rodel Reyes", "Anil Nair", "Tariq Raza", "Suresh Sharma", "Gul Afridi", "Deepak Verma",
    "Selvam Raja", "Ramesh Tamang", "Yousef Haddad", "Jahid Islam", "Biju Thomas", "Arnel Cruz",
    "Usman Iqbal", "Krishna Rai", "Ruwan Silva", "Manoj Singh", "Shaji Varghese", "Bilal Hussain",
    "Mizan Hossain", "Karthik Velu", "Wali Shinwari", "Chaminda Fernando", "Amit Kumar", "Dipak Shrestha",
    "Jayson Reyes", "Senthil Raja", "Zarin Afridi", "Vikram Yadav",
]

PERSONAS: dict[str, dict[str, Any]] = {
    "ravi": {"id": "W01", "name": "Ravi Kumar", "lang": "en", "crew": "C2", "role_title": "Rebar fixer helper",
             "acclimatization": "new", "day": 2, "subcontractor": "Subcontractor A", "buddy": "W07",
             "age": 24, "persona_note": "New arrival, first week on site"},
    "anwar": {"id": "W07", "name": "Anwar Hussain", "lang": "ar", "crew": "C2", "role_title": "Steel fixer",
              "acclimatization": "acclimatized", "day": 400, "subcontractor": "Subcontractor A", "buddy": "W01",
              "age": 41, "persona_note": "Experienced; in the voluntary kidney follow-up pathway"},
}

STAFF: dict[str, dict[str, Any]] = {
    "joseph": {"id": "S01", "name": "Joseph Mathew", "role": "supervisor", "title": "Site supervisor", "lang": "en"},
    "sara": {"id": "S02", "name": "Sara Al Mansoori", "role": "hse", "title": "HSE lead", "lang": "ar"},
    "fatima": {"id": "S03", "name": "Dr Fatima Al Hashimi", "role": "clinician", "title": "Occupational physician", "lang": "ar"},
    "mariam": {"id": "S04", "name": "Mariam Haddad", "role": "nurse", "title": "Occupational health nurse", "lang": "en"},
    "reviewer": {"id": "S99", "name": "Guest reviewer", "role": "auditor", "title": "Judge and evaluator", "lang": "en"},
}

# Scenario scenes: the sandbox clock can jump between them (labelled SIMULATION).
SCENES = [
    {"id": "evening", "at": f"{EVENING_BEFORE}T18:00:00{TZ}", "title": "Evening before: plan tomorrow",
     "title_ar": "مساء اليوم السابق: خطة الغد"},
    {"id": "start", "at": f"{REPLAY_DAY}T07:00:00{TZ}", "title": "Shift start: plan activated",
     "title_ar": "بداية الوردية: تفعيل الخطة"},
    {"id": "harsh", "at": f"{REPLAY_DAY}T09:05:00{TZ}", "title": "Zone A turns harsher than forecast",
     "title_ar": "المنطقة A أشد حرارة من المتوقع"},
    {"id": "water", "at": f"{REPLAY_DAY}T09:45:00{TZ}", "title": "Water runs out at Zone A",
     "title_ar": "نفاد الماء في المنطقة A"},
    {"id": "ask", "at": f"{REPLAY_DAY}T10:30:00{TZ}", "title": "A worker asks a frightening question",
     "title_ar": "عامل يطرح سؤالاً مقلقاً"},
    {"id": "emergency", "at": f"{REPLAY_DAY}T11:10:00{TZ}", "title": "Emergency drill with AI and internet off",
     "title_ar": "تمرين طوارئ دون ذكاء اصطناعي ودون إنترنت"},
    {"id": "midday", "at": f"{REPLAY_DAY}T12:40:00{TZ}", "title": "Midday break in force",
     "title_ar": "استراحة منتصف النهار سارية"},
    {"id": "clinic", "at": f"{REPLAY_DAY}T14:05:00{TZ}", "title": "Clinic visit and privacy",
     "title_ar": "زيارة العيادة والخصوصية"},
]


def build_world(seed: int = SEED) -> dict[str, Any]:
    rng = random.Random(seed)
    site = {
        "id": "site_demo",
        "name": "Al Sahil Residences, Site 1",
        "city": "Abu Dhabi",
        "jurisdiction": "AE-AD",
        "timezone": "Asia/Dubai",
        "lat": 24.45,
        "lon": 54.38,
        "synthetic": True,
        "policy_packs": ["AE-AD-HEAT@0.1.1-demo", "AE-FED-MIDDAY@2026.1-demo"],
        "fallback_plan": "Season standard plan: heavy outdoor work 05:30-10:00 and 16:00-18:30 only; "
                         "15 min shaded rest each hour; water every hour; no lone work.",
        "fallback_plan_ar": "خطة الموسم القياسية: العمل الشاق في الخارج من 05:30 إلى 10:00 ومن 16:00 إلى 18:30 فقط؛ "
                            "راحة 15 دقيقة في الظل كل ساعة؛ ماء كل ساعة؛ لا عمل منفرد.",
    }
    zones = [
        {"id": "A", "name": "Podium rebar", "name_ar": "حديد تسليح المنصة", "outdoor": True, "direct_sun": True,
         "shade_fraction": 0.25, "instrument": "TWL meter A1", "rest_area": "R1", "walk_min": 3,
         "water_point": "WA", "map": {"x": 6, "y": 54, "w": 40, "h": 40}},
        {"id": "B", "name": "Roof slab", "name_ar": "سقف الطابق", "outdoor": True, "direct_sun": True,
         "shade_fraction": 0.0, "instrument": "TWL meter B1", "rest_area": "R1", "walk_min": 4,
         "water_point": "WB", "map": {"x": 52, "y": 6, "w": 42, "h": 40}},
        {"id": "C", "name": "East facade", "name_ar": "الواجهة الشرقية", "outdoor": True, "direct_sun": True,
         "shade_fraction": 0.35, "instrument": "TWL meter C1", "rest_area": "R2", "walk_min": 3,
         "water_point": "WC", "map": {"x": 52, "y": 54, "w": 42, "h": 40}},
        {"id": "D", "name": "Basement and shaded yard", "name_ar": "القبو والساحة المظللة",
         "outdoor": False, "direct_sun": False, "shade_fraction": 1.0, "instrument": "Heat-stress meter D1",
         "rest_area": "R2", "walk_min": 2, "water_point": "WD", "map": {"x": 6, "y": 6, "w": 40, "h": 40}},
    ]
    rest_areas = [
        {"id": "R1", "name": "Cooled shelter 1", "name_ar": "استراحة مكيفة 1", "seats": 20, "cooled": True,
         "working": True, "accessible": True, "near": ["A", "B"], "open": "05:00", "close": "19:00",
         "map": {"x": 48, "y": 48}},
        {"id": "R2", "name": "Shade tent 2", "name_ar": "خيمة مظللة 2", "seats": 24, "cooled": False,
         "working": True, "accessible": True, "near": ["C", "D"], "open": "05:00", "close": "19:00",
         "map": {"x": 48, "y": 96}},
        {"id": "R3", "name": "Cooled canteen", "name_ar": "المقصف المكيف", "seats": 30, "cooled": True,
         "working": True, "accessible": True, "near": ["A", "B", "C", "D"], "open": "11:30", "close": "15:30",
         "map": {"x": 2, "y": 48}},
    ]
    water_points = [
        {"id": z["water_point"], "zone": z["id"], "name": f"Water point {z['id']}",
         "name_ar": f"نقطة الماء {z['id']}", "status": "available", "last_check": f"{REPLAY_DAY}T06:30:00{TZ}",
         "last_check_tier": "E3"}
        for z in zones
    ]
    responders = [
        {"id": "FA1", "name": "First aider 1 (Zones A, B)", "on_shift": True, "response_target_min": 3},
        {"id": "FA2", "name": "First aider 2 (Zones C, D)", "on_shift": True, "response_target_min": 3},
        {"id": "CL1", "name": "Site clinic nurse", "on_shift": True, "response_target_min": 5},
    ]
    toilets = [
        {"id": "T1", "name": "Toilet block 1", "near": ["A", "B"], "working": True},
        {"id": "T2", "name": "Toilet block 2", "near": ["C", "D"], "working": True},
    ]
    crews = [
        {"id": "C1", "name": "Crew 1 Concrete", "name_ar": "الطاقم 1 الخرسانة", "zone": "B", "size": 14,
         "subcontractor": "Subcontractor C"},
        {"id": "C2", "name": "Crew 2 Rebar", "name_ar": "الطاقم 2 حديد التسليح", "zone": "A", "size": 10,
         "subcontractor": "Subcontractor A"},
        {"id": "C3", "name": "Crew 3 Facade", "name_ar": "الطاقم 3 الواجهات", "zone": "C", "size": 8,
         "subcontractor": "Subcontractor B"},
        {"id": "C4", "name": "Crew 4 MEP", "name_ar": "الطاقم 4 الكهروميكانيك", "zone": "D", "size": 8,
         "subcontractor": "Subcontractor B"},
    ]
    workers: list[dict[str, Any]] = []
    for p in PERSONAS.values():
        workers.append({**p, "synthetic": True, "restriction": None})
    names = list(WORKER_NAMES)
    rng.shuffle(names)
    used_ids = {w["id"] for w in workers}
    next_num = 2
    for crew in crews:
        need = crew["size"] - sum(1 for w in workers if w["crew"] == crew["id"])
        for _ in range(need):
            while f"W{next_num:02d}" in used_ids:
                next_num += 1
            wid = f"W{next_num:02d}"
            used_ids.add(wid)
            workers.append({
                "id": wid, "name": names.pop(), "lang": "ar" if rng.random() < 0.35 else "en",
                "crew": crew["id"], "role_title": crew["name"].split(" ", 2)[2] + " worker",
                "acclimatization": "acclimatized", "day": 200 + rng.randint(0, 900),
                "subcontractor": crew["subcontractor"], "synthetic": True, "restriction": None,
                "buddy": None,
            })
    # A few more new and returning workers (status only, never health data).
    others = sorted([w for w in workers if w["id"] not in ("W01", "W07")], key=lambda w: w["id"])
    picks = [others[i] for i in (3, 11, 19, 27)]
    for w, (stage, day) in zip(picks, [("new", 1), ("new", 4), ("returning", 2), ("returning", 3)]):
        w["acclimatization"], w["day"] = stage, day
    # Buddies inside each crew (pairs).
    for crew in crews:
        members = [w for w in workers if w["crew"] == crew["id"] and not w.get("buddy")]
        for a, b in zip(members[::2], members[1::2]):
            a["buddy"], b["buddy"] = b["id"], a["id"]
    workers.sort(key=lambda w: w["id"])

    tasks_plan = [
        {"id": "P1", "name": "Roof slab pour, Level 9", "name_ar": "صب سقف الطابق التاسع", "zone": "B", "crew": "C1",
         "workload": "heavy", "outdoor": True, "draft_start": "10:00", "duration_min": 240, "contiguous": True,
         "earliest": "05:30", "latest_end": "19:00"},
        {"id": "P2", "name": "Podium rebar tying", "name_ar": "ربط حديد المنصة", "zone": "A", "crew": "C2",
         "workload": "moderate", "outdoor": True, "draft_start": "07:00", "duration_min": 300, "contiguous": False,
         "earliest": "05:30", "latest_end": "18:30"},
        {"id": "P3", "name": "Facade anchor drilling", "name_ar": "تثبيت مراسي الواجهة", "zone": "C", "crew": "C3",
         "workload": "heavy", "outdoor": True, "draft_start": "09:00", "duration_min": 240, "contiguous": False,
         "earliest": "05:30", "latest_end": "18:30"},
        {"id": "P4", "name": "Basement cable trays", "name_ar": "حوامل الكابلات في القبو", "zone": "D", "crew": "C4",
         "workload": "light", "outdoor": False, "draft_start": "07:00", "duration_min": 480, "contiguous": False,
         "earliest": "06:00", "latest_end": "17:00"},
    ]
    shaded_task = {"id": "P5", "name": "Rebar cage pre-assembly (shaded yard)", "name_ar": "تجهيز أقفاص الحديد (ساحة مظللة)",
                   "zone": "D", "workload": "light", "outdoor": False, "capacity": 6}
    draft_breaks = [{"crews": ["C1", "C2", "C3", "C4"], "start": "10:00", "minutes": 30, "rest_area": "R1"}]

    return {
        "synthetic": True,
        "label": "SYNTHETIC scenario. Fictional site and people. Replayed real weather (Abu Dhabi, 19 Aug 2025).",
        "site": site,
        "zones": zones,
        "rest_areas": rest_areas,
        "water_points": water_points,
        "responders": responders,
        "toilets": toilets,
        "crews": crews,
        "workers": workers,
        "staff": STAFF,
        "personas": PERSONAS,
        "shaded_task": shaded_task,
        "plan_tomorrow": {"date": REPLAY_DAY, "tasks": tasks_plan, "breaks": draft_breaks, "status": "draft",
                          "created_at": f"{EVENING_BEFORE}T17:40:00{TZ}", "created_by": "S01"},
        "clock": SCENES[0]["at"],
        "scene": SCENES[0]["id"],
        # Physical world state the system does not know until someone reports it.
        "physical": {"water": {"WA": {"empty_from": f"{REPLAY_DAY}T09:40:00{TZ}", "refilled_at": None}}},
        "reading_overrides": {},
        "exemptions": [],
        "settings": {"ai_enabled": True, "ai_capabilities": {}, "forecast_enabled": True, "redteam_mode": False},
    }


def clone_world(world: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(world)


def local_hhmm(iso: str) -> str:
    return iso[11:16]


def advance_clock(iso: str, minutes: int) -> str:
    dt = datetime.fromisoformat(iso) + timedelta(minutes=minutes)
    return dt.isoformat()


def simulated_reading(world: dict[str, Any], zone_id: str, now_iso: str | None = None) -> dict[str, Any]:
    """Simulated instrument reading for a zone at the sandbox clock (5-minute logger)."""
    now_iso = now_iso or world["clock"]
    day, hhmm = now_iso[:10], now_iso[11:16]
    zone = next(z for z in world["zones"] if z["id"] == zone_id)
    minute = int(hhmm[3:5]) - int(hhmm[3:5]) % 5
    observed_at = f"{day}T{hhmm[:2]}:{minute:02d}:00{TZ}"
    override = world.get("reading_overrides", {}).get(zone_id)
    if override:
        return {"zone": zone_id, "kind": override.get("kind", "twl"), "value": override.get("value"),
                "unit": override.get("unit", "W/m2"), "observed_at": override.get("observed_at", observed_at),
                "provenance": override.get("provenance", "measured"), "instrument": zone["instrument"],
                "simulated": True, "override": True}
    wbgt = zone_wbgt_at(day, f"{hhmm[:2]}:{minute:02d}", zone_id)
    if wbgt is None:
        return {"zone": zone_id, "kind": "twl", "value": None, "unit": "W/m2", "observed_at": None,
                "provenance": "measured", "instrument": zone["instrument"], "simulated": True}
    jitter = ((sum(map(ord, zone_id + hhmm[:4])) % 5) - 2) * 0.8
    twl = round(twl_from_wbgt_demo(wbgt) + jitter)
    return {"zone": zone_id, "kind": "twl", "value": twl, "unit": "W/m2", "observed_at": observed_at,
            "provenance": "measured", "instrument": zone["instrument"], "simulated": True,
            "wbgt_derived": wbgt, "quality": {"status": "scenario_defined",
                                               "limitations": ["Simulated instrument; not a real site measurement"]}}
