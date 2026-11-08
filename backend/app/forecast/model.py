"""Foresee: zone heat forecasting (finalsystem.md §10.3, §14.2, Appendix G26-G28).

Two modes share one output contract (Appendix B.10):

* Live mode: hourly forecast weather from Open-Meteo -> WBGT per zone with the
  Liljegren method (thermofeel) -> bands. See ``service.py``.
* Replay mode (the demonstration scenario, summer 2025): archived day-ahead
  forecasts are not used in the prototype, so the forecast "issued the evening
  before" comes from a small, explainable statistical model trained on the
  2025 season's derived WBGT (NASA POWER weather): damped persistence of the
  latest known anomaly towards a 14-day hourly climatology.

Information cutoff. A forecast issued at 18:00 local uses only readings that are
complete by then. The hour stamped hh:22 may average the following hour, so the
last same-day hour treated as known is 16 (stamped 16:22). For later hours the
latest known same-hour reading is the previous day's, so those hours have a
longer effective lead, and the damping is fitted per effective lead.

Three separate periods, in time order, so nothing is fitted and evaluated on the
same data: FIT (damping by least squares), CALIBRATION (split-conformal 90%
interval: the empirical quantile of absolute errors of the already-fitted model)
and TEST (held out; the backtest below). Planning uses the upper end of the
interval (G26), the conservative side for heat.

The backtest shows how this simple model behaves on past weather. It is not a
claim about any site's instruments, and the demonstration day's forecast in
``service.py`` is emulated separately (labelled SIMULATION).
"""
from __future__ import annotations

import json
import math
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parents[1] / "data"
ZONES = ("A", "B", "C", "D")
CLIM_DAYS = 14
ALPHA = 0.10                 # 90% intervals
ISSUE_HOUR = 18              # forecasts are issued at 18:00 local the evening before
LAST_KNOWN_HOUR = 16         # the last same-day hour complete by 18:00 (stamped 16:22, may average to 17:22)
FIT_FROM, FIT_TO = date(2025, 6, 30), date(2025, 7, 24)     # damping fitted here
CAL_FROM, CAL_TO = date(2025, 7, 25), date(2025, 8, 7)      # conformal calibration only
TEST_FROM, TEST_TO = date(2025, 8, 8), date(2025, 9, 15)    # held-out backtest (includes the 19 Aug demo day)
WORK_HOURS = range(5, 20)    # 05:00-19:59 local, the hours a site plans
LEADS = (1, 2, 3)            # issue day -> target day
EFFECTIVE_LEADS = (1, 2, 3, 4)


@lru_cache(maxsize=1)
def season() -> dict[str, dict[tuple[date, int], float]]:
    with open(DATA / "season2025_hourly.json", encoding="utf-8") as f:
        raw = json.load(f)
    cols = raw["columns"]
    idx = {c: i for i, c in enumerate(cols)}
    out: dict[str, dict[tuple[date, int], float]] = {z: {} for z in ZONES}
    for row in raw["rows"]:
        local = row[idx["local"]]
        d = date.fromisoformat(local[:10])
        h = int(local[11:13])
        for z in ZONES:
            out[z][(d, h)] = float(row[idx[z]])
    return out


def anchor_day(issue_day: date, hour: int) -> date:
    """The latest day whose reading at this hour is complete at the issue time (18:00 on issue_day)."""
    return issue_day if hour <= LAST_KNOWN_HOUR else issue_day - timedelta(days=1)


def _clim(series: dict[tuple[date, int], float], until: date, hour: int) -> float | None:
    """Mean of the CLIM_DAYS readings at this hour ending on `until` (all known at issue time)."""
    vals = [series.get((until - timedelta(days=k), hour)) for k in range(0, CLIM_DAYS)]
    vals = [v for v in vals if v is not None]
    if len(vals) < CLIM_DAYS // 2:
        return None
    return sum(vals) / len(vals)


def _features(series, issue_day: date, target_day: date, hour: int) -> tuple[float, float, int, float] | None:
    """(climatology, latest known anomaly, effective lead in days, latest known reading) at the issue time."""
    a = anchor_day(issue_day, hour)
    clim = _clim(series, a, hour)
    last = series.get((a, hour))
    if clim is None or last is None:
        return None
    return clim, last - clim, (target_day - a).days, last


def _pairs(lo: date, hi: date, hours) -> list[tuple[str, date, int, int, float, float, float, float]]:
    """(zone, target day, hour, effective lead, climatology, anomaly, latest reading, actual) for lead days 1-3."""
    s = season()
    out = []
    for z in ZONES:
        d = lo
        while d <= hi:
            for lead in LEADS:
                issue = d - timedelta(days=lead)
                for h in hours:
                    feat = _features(s[z], issue, d, h)
                    y = s[z].get((d, h))
                    if feat is None or y is None:
                        continue
                    clim, anom, eff, last = feat
                    out.append((z, d, h, eff, clim, anom, last, y))
            d += timedelta(days=1)
    return out


@lru_cache(maxsize=1)
def fitted() -> dict[str, Any]:
    """Damping per effective lead on FIT; conformal 90% half-width per effective lead on CALIBRATION."""
    fit = _pairs(FIT_FROM, FIT_TO, range(24))
    params: dict[int, dict[str, float]] = {}
    for eff in EFFECTIVE_LEADS:
        num = sum(anom * (y - clim) for _, _, _, e, clim, anom, _, y in fit if e == eff)
        den = sum(anom * anom for _, _, _, e, clim, anom, _, y in fit if e == eff)
        phi = max(0.0, min(1.0, num / den)) if den else 0.0
        params[eff] = {"phi": round(phi, 4), "n_fit": sum(1 for p in fit if p[3] == eff)}
    cal = _pairs(CAL_FROM, CAL_TO, range(24))
    for eff in EFFECTIVE_LEADS:
        resid = sorted(abs(y - (clim + params[eff]["phi"] * anom)) for _, _, _, e, clim, anom, _, y in cal if e == eff)
        n = len(resid)
        k = min(n - 1, math.ceil((n + 1) * (1 - ALPHA)) - 1)
        params[eff].update(q90=round(resid[k], 3), n_cal=n)
    return {"params": params, "method": {
        "point": "damped persistence of the latest known anomaly towards a 14-day hourly climatology",
        "cutoff": "issued 18:00 local; same-day readings up to the 16:00 hour only",
        "interval": f"split-conformal, 90%, calibrated on {CAL_FROM.isoformat()}..{CAL_TO.isoformat()} "
                    f"(damping fitted on {FIT_FROM.isoformat()}..{FIT_TO.isoformat()})",
        "wbgt": "liljegren@thermofeel from NASA POWER hourly weather, per-zone shade blend",
        "version": "foresee-replay@1.1.0",
    }}


def point_forecast(zone: str, issue_day: date, target_day: date, hour: int) -> dict[str, Any] | None:
    lead = (target_day - issue_day).days
    if lead not in LEADS:
        return None
    feat = _features(season()[zone], issue_day, target_day, hour)
    if feat is None:
        return None
    clim, anom, eff, _ = feat
    p = fitted()["params"][eff]
    f = clim + p["phi"] * anom
    return {"wbgt": round(f, 2), "lo": round(f - p["q90"], 2), "hi": round(f + p["q90"], 2), "lead_days": lead,
            "effective_lead_days": eff}


def actual(zone: str, day: date, hour: int) -> float | None:
    return season()[zone].get((day, hour))


def band_of_wbgt(v: float) -> str:
    # Mirrors AE-AD-HEAT wbgt_planning_bands_demo (kept in sync by a unit test).
    if v < 28.0:
        return "unrestricted"
    if v < 31.0:
        return "acclimatization"
    if v < 33.0:
        return "buffer"
    return "withdrawal"


HARSH = {"buffer", "withdrawal"}
RANK = {"unrestricted": 0, "acclimatization": 1, "buffer": 2, "withdrawal": 3}


@lru_cache(maxsize=1)
def backtest() -> dict[str, Any]:
    """Held-out evaluation for lead day 1 over work hours (Appendix G27-G28). Baselines obey the same cutoff."""
    s = season()
    stats: dict[str, Any] = {}
    tot = {"n": 0, "covered": 0, "abs_err": 0.0, "abs_err_persist": 0.0, "abs_err_clim": 0.0,
           "harsh_ref": 0, "under": 0, "plan_harsh": 0, "false_alarm": 0}
    for z in ZONES:
        zs = dict.fromkeys(tot, 0)
        zs["abs_err"] = zs["abs_err_persist"] = zs["abs_err_clim"] = 0.0
        d = TEST_FROM
        while d <= TEST_TO:
            issue = d - timedelta(days=1)
            for h in WORK_HOURS:
                fc = point_forecast(z, issue, d, h)
                y = actual(z, d, h)
                feat = _features(s[z], issue, d, h)
                if fc is None or y is None or feat is None:
                    continue
                clim, _, _, last = feat
                zs["n"] += 1
                zs["covered"] += int(fc["lo"] <= y <= fc["hi"])
                zs["abs_err"] += abs(fc["wbgt"] - y)
                zs["abs_err_persist"] += abs(last - y)
                zs["abs_err_clim"] += abs(clim - y)
                ref_band = band_of_wbgt(y)
                plan_band = band_of_wbgt(fc["hi"])
                if ref_band in HARSH:
                    zs["harsh_ref"] += 1
                    if RANK[plan_band] < RANK[ref_band]:
                        zs["under"] += 1
                if plan_band in HARSH:
                    zs["plan_harsh"] += 1
                    if ref_band not in HARSH:
                        zs["false_alarm"] += 1
            d += timedelta(days=1)
        for k in tot:
            tot[k] += zs[k]
        stats[z] = _summarise(zs)
    stats["all"] = _summarise(tot)
    return {
        "lead_days": 1,
        "period": f"{TEST_FROM.isoformat()}..{TEST_TO.isoformat()} (held out)",
        "periods": {"fit": f"{FIT_FROM.isoformat()}..{FIT_TO.isoformat()}",
                    "calibration": f"{CAL_FROM.isoformat()}..{CAL_TO.isoformat()}",
                    "test": f"{TEST_FROM.isoformat()}..{TEST_TO.isoformat()}"},
        "issue_time": "18:00 local the evening before; readings complete by then only",
        "hours": "05:00-19:59 Asia/Dubai",
        "targets": {"underestimation_max": 0.05, "coverage_90": [0.85, 0.95]},
        "by_zone": stats,
        "fit": fitted(),
        "label": "Backtest on derived WBGT from replayed 2025 weather (one season, four zones); not site "
                 "instruments. Day-one evidence: a pilot recalibrates on the site's own readings.",
    }


def _summarise(zs: dict[str, Any]) -> dict[str, Any]:
    n = max(zs["n"], 1)
    return {
        "zone_hours": zs["n"],
        "coverage_90": round(zs["covered"] / n, 3),
        "mae_model": round(zs["abs_err"] / n, 3),
        "mae_persistence": round(zs["abs_err_persist"] / n, 3),
        "mae_climatology": round(zs["abs_err_clim"] / n, 3),
        "harsh_reference_hours": zs["harsh_ref"],
        "underestimated_harsh_hours": zs["under"],
        "underestimation_rate": round(zs["under"] / zs["harsh_ref"], 3) if zs["harsh_ref"] else None,
        "planning_harsh_hours": zs["plan_harsh"],
        "false_alarm_rate": round(zs["false_alarm"] / zs["plan_harsh"], 3) if zs["plan_harsh"] else None,
    }
