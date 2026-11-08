"""Four weeks of SYNTHETIC operational history for the demo site (22 Jul - 18 Aug 2025).

Used by the compliance pack, the HSE copilot's metrics layer and the Watch
detectors. Operational only: no clinical field exists in any record. Symptom
reports exist only as daily crew-level counts, never per worker.

The last week contains scenario-defined events so the copilot's gold questions
have exact, hand-checkable answers. Earlier weeks are random with a fixed seed.
One pattern is injected for Watch (test T94): Subcontractor C's water gaps rise
over the last three days.
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from functools import lru_cache
from typing import Any

from ..forecast.model import actual as season_actual

START = date(2025, 7, 22)
END = date(2025, 8, 18)
ZONE_SUB = {"A": ("Subcontractor A", "C2"), "B": ("Subcontractor C", "C1"), "C": ("Subcontractor B", "C3"),
            "D": ("Subcontractor B", "C4")}
CREW_SIZE = {"C1": 14, "C2": 10, "C3": 8, "C4": 8}

# Scenario-defined events for the last week (12-18 Aug). (date, zone, kind, start, gap_min, final_tier, disputed)
LAST_WEEK = [
    ("2025-08-12", "B", "water", "10:05", 24, "E3", False),
    ("2025-08-13", "D", "water", "09:40", 18, "E4", False),
    ("2025-08-14", "A", "shade", "11:10", 12, "E3", False),
    ("2025-08-15", "C", "water", "08:50", 9, "E3", False),
    ("2025-08-16", "B", "water", "09:30", 21, "E3", True),
    ("2025-08-16", "B", "water", "16:20", 12, "E3", False),
    ("2025-08-16", "B", "cooling", "13:00", 35, "E2", False),
    ("2025-08-17", "B", "water", "07:10", 9, "E3", False),
    ("2025-08-17", "B", "water", "10:20", 27, "E2", True),
    ("2025-08-17", "A", "water", "07:45", 16, "E4", False),
    ("2025-08-18", "B", "water", "09:55", 31, "E3", False),
    ("2025-08-18", "B", "water", "17:05", 14, "E3", False),
    ("2025-08-18", "C", "shade", "10:30", 22, "E3", False),
]


# Subcontractor C's usual water gaps in the baseline weeks (scenario-defined, so the Watch baseline is realistic).
EARLY_C = [("2025-07-23", "10:40", 14), ("2025-07-26", "09:15", 22), ("2025-07-30", "16:05", 11),
           ("2025-08-01", "08:30", 19), ("2025-08-04", "10:10", 16), ("2025-08-07", "09:45", 25),
           ("2025-08-10", "17:20", 12)]


@lru_cache(maxsize=1)
def history() -> dict[str, Any]:
    rng = random.Random(42)
    gaps: list[dict[str, Any]] = []
    n = 1
    d = START
    last_week_start = date(2025, 8, 12)
    while d < last_week_start:
        for zone in "ABCD":
            for kind, rate in (("water", 0.10), ("shade", 0.06), ("cooling", 0.04)):
                if rng.random() < rate:
                    sub, crew = ZONE_SUB[zone]
                    gap = max(4, int(rng.lognormvariate(2.4, 0.5)))
                    tier = rng.choice(["E2", "E3", "E3", "E4"])
                    gaps.append(_gap(n, d.isoformat(), zone, kind, f"{rng.randint(7, 16):02d}:{rng.choice(['05', '20', '35', '50'])}",
                                     gap, tier, rng.random() < 0.12, sub, crew))
                    n += 1
        d += timedelta(days=1)
    for (day, start, gap) in EARLY_C:
        gaps.append(_gap(n, day, "B", "water", start, gap, "E3", False, "Subcontractor C", "C1"))
        n += 1
    for (day, zone, kind, start, gap, tier, disputed) in LAST_WEEK:
        sub, crew = ZONE_SUB[zone]
        gaps.append(_gap(n, day, zone, kind, start, gap, tier, disputed, sub, crew))
        n += 1

    # Daily operational aggregates.
    days = []
    d = START
    while d <= END:
        # Heat hours per zone from the replayed weather (real), using the demo bands.
        band_hours = {}
        for zone in "ABCD":
            harsh = sum(1 for h in range(5, 20) if (season_actual(zone, d, h) or 0) >= 31.0)
            withdrawal = sum(1 for h in range(5, 20) if (season_actual(zone, d, h) or 0) >= 33.0)
            band_hours[zone] = {"buffer_or_harsher_h": harsh, "withdrawal_h": withdrawal}
        crews = {}
        for crew, size in CREW_SIZE.items():
            req = 8 if crew != "C4" else 0
            delivered = req - (1 if rng.random() < 0.15 else 0) if req else 0
            cut_short = 1 if rng.random() < 0.08 and req else 0
            crews[crew] = {"breaks_required": req, "breaks_delivered_full": max(0, delivered - cut_short),
                           "breaks_cut_short": cut_short,
                           "symptom_reports": sum(1 for _ in range(size) if rng.random() < 0.03),
                           "workers": size}
        midday_minutes = 0
        if d == date(2025, 8, 4):
            midday_minutes = 10   # a short violation in Zone C, recorded and investigated
        days.append({"date": d.isoformat(), "band_hours": band_hours, "crews": crews,
                     "midday_outdoor_minutes": midday_minutes,
                     "midday_note": "Zone C: scaffold tie-off finished 10 min into the window; investigated"
                     if midday_minutes else None})
        d += timedelta(days=1)
    training = {"due": 4, "completed": 3, "overdue": 1}
    return {"gaps": gaps, "days": days, "training": training,
            "label": "SYNTHETIC operational history (fixed seed); not a real site"}


def _gap(n, day, zone, kind, start, gap, tier, disputed, sub, crew):
    sh, sm = int(start[:2]), int(start[3:])
    end_m = sh * 60 + sm + gap
    return {"id": f"hist_task_{n:03d}", "date": day, "zone": zone, "kind": kind, "start": start,
            "end": f"{end_m // 60:02d}:{end_m % 60:02d}", "gap_min": gap, "final_tier": tier, "disputed": disputed,
            "verified": tier in ("E3", "E4") and not disputed or (disputed and tier in ("E3", "E4")),
            "subcontractor": sub, "crew": crew, "action_code": {"water": "WATER_RESTORE", "shade": "SHADE_EXTEND",
                                                                "cooling": "COOLING_FIX"}[kind]}
