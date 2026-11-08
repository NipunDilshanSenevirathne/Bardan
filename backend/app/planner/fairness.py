"""Fairness across the week (finalsystem.md §10.3 objective 3, §11.5; test T78).

The optimiser's fairness objective works inside one day. This report looks
across the last week: which crew carried the most harsh-band heat work per
worker each day under the supervisor's routine schedule, and whether the same
crew keeps getting the hottest slots. It flags the pattern for the supervisor
and HSE; it never ranks individual workers and never changes a plan by itself.

SIMULATION: the week is replayed weather (12-18 Aug 2025) with emulated
day-ahead forecasts, on the synthetic 40-worker site.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

FLAG_MIN_DAYS = 4            # most exposed on at least 4 of 7 days
FLAG_MIN_EXCESS = 0.10       # and at least 10% more harsh hours per worker than the other exposed crews


def assess(days: list[dict[str, Any]], crews: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """days: [{"date", "per_worker": {crew: harsh hours per worker}}]; crews: {id: {"name", "name_ar", "heat"}}."""
    exposed = [c for c, meta in crews.items() if meta.get("heat")]
    most: dict[str, int] = {c: 0 for c in exposed}
    totals: dict[str, float] = {c: 0.0 for c in exposed}
    for d in days:
        vals = {c: float(d["per_worker"].get(c, 0.0)) for c in exposed}
        for c, v in vals.items():
            totals[c] += v
        top = max(vals.values(), default=0.0)
        leaders = [c for c, v in vals.items() if v == top and top > 0]
        if len(leaders) == 1:          # ties are not "the same crew always" evidence
            most[leaders[0]] += 1
    flag = None
    for c in sorted(exposed, key=lambda c: -most[c]):
        others = [totals[o] for o in exposed if o != c]
        mean_others = sum(others) / len(others) if others else 0.0
        excess = (totals[c] - mean_others) / mean_others if mean_others else 0.0
        if most[c] >= FLAG_MIN_DAYS and excess >= FLAG_MIN_EXCESS:
            flag = {"crew": c, "days_most_exposed": most[c], "days": len(days),
                    "harsh_h_per_worker": round(totals[c], 1), "others_mean_h_per_worker": round(mean_others, 1),
                    "excess_percent": round(100 * excess)}
            break
    out = {"crews": [{"crew": c, "name": crews[c]["name"], "name_ar": crews[c].get("name_ar"),
                      "heat_work": bool(crews[c].get("heat")), "days_most_exposed": most.get(c, 0),
                      "harsh_h_per_worker": round(totals.get(c, 0.0), 1),
                      "daily": [round(float(d["per_worker"].get(c, 0.0)), 1) for d in days]} for c in crews],
           "dates": [d["date"] for d in days], "flag": flag,
           "rule": {"min_days": FLAG_MIN_DAYS, "min_excess_percent": round(100 * FLAG_MIN_EXCESS)}}
    if flag:
        meta = crews[flag["crew"]]
        out["message"] = {
            "en": (f"{meta['name']} had the most harsh-band heat work per worker on {flag['days_most_exposed']} of "
                   f"{flag['days']} days ({flag['harsh_h_per_worker']} h per worker against "
                   f"{flag['others_mean_h_per_worker']} h for the other exposed crews). Rotate the hottest slots; "
                   f"the optimiser's fairness objective spreads them within each day."),
            "ar": (f"تحمّل {meta.get('name_ar') or meta['name']} أكبر قدر من العمل في النطاق الحراري القاسي لكل عامل في "
                   f"{flag['days_most_exposed']} من {flag['days']} أيام ({flag['harsh_h_per_worker']} ساعة لكل عامل "
                   f"مقابل {flag['others_mean_h_per_worker']} ساعة للأطقم المعرضة الأخرى). بدّل الفترات الأشد حرارة؛ "
                   f"يوزعها هدف العدالة في المُحسِّن داخل كل يوم."),
        }
    else:
        out["message"] = {"en": "No crew kept getting the hottest slots this week.",
                          "ar": "لم يحصل أي طاقم باستمرار على الفترات الأشد حرارة هذا الأسبوع."}
    return out


def week_report(world: dict[str, Any], end_day: str = "2025-08-18", n_days: int = 7) -> dict[str, Any]:
    """Replay the supervisor's routine schedule over the last week and assess fairness."""
    from ..forecast import service as fs
    from .twin import draft_to_plan, grid, simulate
    zones = {z["id"]: z for z in world["zones"]}
    tasks = {t["crew"]: t for t in world["plan_tomorrow"]["tasks"]}
    crews = {c["id"]: {"name": c["name"], "name_ar": c.get("name_ar"), "size": c["size"],
                       "heat": bool(tasks.get(c["id"]) and (tasks[c["id"]]["outdoor"] or
                                                            zones[tasks[c["id"]]["zone"]]["direct_sun"]))}
             for c in world["crews"]}
    end = date.fromisoformat(end_day)
    days = []
    plan = draft_to_plan(world)
    for i in range(n_days - 1, -1, -1):
        d = end - timedelta(days=i)
        fc = fs.scenario_forecast(issue_at=f"{(d - timedelta(days=1)).isoformat()}T18:00:00+04:00")
        g = grid(world, fc, d.isoformat())
        tw = simulate(world, g, plan)
        days.append({"date": d.isoformat(), "per_worker": {c: v / max(1, crews[c]["size"])
                                                           for c, v in tw["crew_harsh_hours"].items()}})
    out = assess(days, crews)
    out["label"] = "SIMULATION: replayed weather 12-18 Aug 2025, the supervisor's routine schedule each day"
    out["basis"] = "harsh-band (buffer or withdrawal) heat-work hours per worker, by crew"
    return out
