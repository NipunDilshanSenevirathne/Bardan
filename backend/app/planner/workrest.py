"""Break planner: rest needed in each hour of hot work (programme feedback, November 2026).

The demonstration rule pack (AE-AD-HEAT) sets a minimum rest per hour by heat band only. The published
international method also makes rest depend on how hard the job is, how hot the work spot and the rest spot
are, what the worker wears and whether the worker is acclimatized. ISO 7243:2017, the NIOSH 2016 criteria
(REL/RAL) and the ACGIH TLV/Action Limit use the same two limits, each a one-hour time-weighted average:

    acclimatized workers           WBGT_lim = 56.7 - 11.5 * log10(M)
    workers not yet acclimatized   WBGT_lim = 59.9 - 14.1 * log10(M)

with M the hour's time-weighted metabolic rate in watts (valid for 115-520 W). For one hour of work this
module finds the shortest break, in 15-minute steps, that keeps the hour's average WBGT within the limit
for the hour's average metabolic rate. Walking to and from the rest area is counted as work in the heat
(normal walking, 300 W), not as rest. Clothing adds the ACGIH clothing adjustment to the WBGT.

It can only add rest: the site's official rules (the band minimum, the withdrawal band, the federal midday
break and the acclimatization schedule) stay in force as a floor. Deterministic, no AI. The values are
published reference values that a qualified reviewer must confirm before any real use
(docs/RULE-REVIEW.md, rows 16-20).
"""
from __future__ import annotations

import math
from typing import Any

# ISO 8996 / ACGIH metabolic rate classes for a 70 kg worker (OSHA Technical Manual III:4, Table 3).
METABOLIC_W = {"rest": 115.0, "light": 180.0, "moderate": 300.0, "heavy": 415.0}
WALK_W = 300.0
M_MIN, M_MAX = 115.0, 520.0
# ACGIH clothing adjustment factors (degrees C-WBGT): work clothes 0; polyolefin coveralls 1;
# double-layer woven clothing 3. Vapour-barrier suits (11) need a job-specific assessment and are not offered.
CLOTHING_CAF = {"work_clothes": 0.0, "coveralls": 1.0, "double_layer": 3.0}
QUARTER = 15

SOURCES = [
    {"id": "ISO7243", "text": "ISO 7243:2017 Ergonomics of the thermal environment: WBGT reference values"},
    {"id": "NIOSH2016", "text": "NIOSH Criteria for a Recommended Standard: Occupational Exposure to Heat and Hot "
                                "Environments (DHHS 2016-106): REL and RAL"},
    {"id": "ACGIH", "text": "ACGIH TLV and Action Limit for heat stress, clothing adjustment factors "
                            "(OSHA Technical Manual Section III Chapter 4)"},
]


def limit_wbgt(m_w: float, acclimatized: bool) -> float:
    """The one-hour WBGT limit for a time-weighted metabolic rate (ISO 7243 / NIOSH REL and RAL)."""
    m = min(M_MAX, max(M_MIN, float(m_w)))
    if acclimatized:
        return 56.7 - 11.5 * math.log10(m)
    return 59.9 - 14.1 * math.log10(m)


def hour_average(work_min: int, wbgt_work: float, wbgt_rest: float, m_work: float, walk_each_way_min: float,
                 caf: float) -> tuple[float, float]:
    """Time-weighted WBGT and metabolic rate for one hour split into work, walking and rest.

    The rest block (60 - work_min) starts and ends with the walk to and from the rest area; the walk is spent
    at the work spot's WBGT and at walking pace. Clothing is worn for the whole hour."""
    rest_block = 60 - work_min
    walk = min(float(rest_block), 2.0 * walk_each_way_min) if rest_block > 0 else 0.0
    rest = rest_block - walk
    wbgt = ((work_min + walk) * (wbgt_work + caf) + rest * (wbgt_rest + caf)) / 60.0
    m = (work_min * m_work + walk * WALK_W + rest * METABOLIC_W["rest"]) / 60.0
    return wbgt, m


def rest_needed(wbgt_work: float, wbgt_rest: float, workload: str, acclimatized: bool = True,
                clothing: str = "work_clothes", walk_each_way_min: float = 3.0) -> dict[str, Any]:
    """The shortest rest (in 15-minute steps) that keeps one hour of this work within the limit.

    Returns quarters of rest (0-3), or workable=False when even 45 minutes of rest per hour is not enough:
    then no work of this kind is planned in that hour."""
    if workload not in ("light", "moderate", "heavy"):
        raise ValueError("workload must be light, moderate or heavy")
    if clothing not in CLOTHING_CAF:
        raise ValueError("unknown clothing")
    m_work = METABOLIC_W[workload]
    caf = CLOTHING_CAF[clothing]
    for q in range(4):
        work = 60 - QUARTER * q
        wbgt, m = hour_average(work, wbgt_work, wbgt_rest, m_work, walk_each_way_min, caf)
        lim = limit_wbgt(m, acclimatized)
        if wbgt <= lim + 1e-9:
            return {"workable": True, "quarters": q, "rest_min": QUARTER * q, "work_min": work,
                    "wbgt_avg": round(wbgt, 2), "m_avg": round(m), "limit": round(lim, 2),
                    "margin": round(lim - wbgt, 2), "acclimatized": acclimatized, "clothing_adj": caf}
    wbgt, m = hour_average(QUARTER, wbgt_work, wbgt_rest, m_work, walk_each_way_min, caf)
    lim = limit_wbgt(m, acclimatized)
    return {"workable": False, "quarters": 4, "rest_min": 60, "work_min": 0, "wbgt_avg": round(wbgt, 2),
            "m_avg": round(m), "limit": round(lim, 2), "margin": round(lim - wbgt, 2), "acclimatized": acclimatized,
            "clothing_adj": caf}


def floor_quarters(band_rest_min: int) -> int:
    """The rule pack's minimum rest for the band, in 15-minute steps (never rounded down)."""
    return int(math.ceil(max(0, band_rest_min) / QUARTER))


def check_hour(work_min: int, wbgt_work: float, wbgt_rest: float, workload: str, acclimatized: bool,
               clothing: str, walk_each_way_min: float) -> dict[str, Any]:
    """Re-check an hour as planned (used by the independent re-validation, not by the solver)."""
    wbgt, m = hour_average(work_min, wbgt_work, wbgt_rest, METABOLIC_W[workload], walk_each_way_min,
                           CLOTHING_CAF[clothing])
    lim = limit_wbgt(m, acclimatized)
    return {"ok": wbgt <= lim + 1e-9, "wbgt_avg": round(wbgt, 2), "m_avg": round(m), "limit": round(lim, 2)}
