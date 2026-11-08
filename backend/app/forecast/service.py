"""Forecast service (Foresee): zone-hour WBGT with intervals and planning bands.

Output contract follows finalsystem.md Appendix B.10. Every value is labelled
``forecast`` and is never used as a live observation (policy.freshness_key).

Modes
-----
scenario  The demonstration day (19 Aug 2025). Archived day-ahead forecasts are
          not used in the prototype, so the forecast "issued the evening before"
          is emulated from the replayed weather plus a seeded forecast-error
          model (site-wide AR(1) error, sigma 0.5 C, rho 0.85, plus a small zone error,
          growing 15% per lead day). The
          scenario script also injects one known error (test T72): Zone A is
          forecast 1.6 C too mild from 08:00 to 10:59, so judges can see live
          readings override a forecast that was wrong. All of this is labelled
          SIMULATION in the API and the interface.
live      Real hourly forecast weather for the site from Open-Meteo (free
          non-commercial tier, CC BY 4.0), turned into WBGT per zone with the
          Liljegren method. Intervals use the same provisional width until
          site calibration (pilot). If the provider fails: "forecast
          unavailable" and the season's standard plan (test T71).
"""
from __future__ import annotations

import math
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .model import actual as season_actual
from .wbgt import cos_solar_zenith, wbgt_liljegren

TZ = "+04:00"
ISSUE_AT = "2025-08-18T18:00:00+04:00"
SIGMA = 0.5          # common (site-wide) forecast error, deg C
RHO = 0.85           # hour-to-hour persistence of the error
ZONE_SIGMA = 0.12    # small zone-specific microclimate error
SEED = 2658          # fixed seed: the scenario is reproducible
INJECTIONS = [  # (zone, local day, hour_from, hour_to_inclusive, delta_c, test id)
    ("A", "2025-08-19", 8, 10, -1.6, "T72"),
]
Z90 = 1.645
SHADE = {"A": 0.25, "B": 0.0, "C": 0.35, "D": 1.0}
BANDS = ("unrestricted", "acclimatization", "buffer", "withdrawal")
THRESH = (28.0, 31.0, 33.0)   # demonstration WBGT planning bands (AE-AD-HEAT pack)


def band_of(v: float) -> str:
    if v < THRESH[0]:
        return BANDS[0]
    if v < THRESH[1]:
        return BANDS[1]
    if v < THRESH[2]:
        return BANDS[2]
    return BANDS[3]


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def band_probs(point: float, sigma: float) -> dict[str, float]:
    edges = [-math.inf, *THRESH, math.inf]
    out = {}
    for i, b in enumerate(BANDS):
        lo = _norm_cdf((edges[i] - point) / sigma) if edges[i] != -math.inf else 0.0
        hi = _norm_cdf((edges[i + 1] - point) / sigma) if edges[i + 1] != math.inf else 1.0
        out[b] = round(max(0.0, hi - lo), 3)
    return out


def _errors(zone: str, n: int) -> list[float]:
    """Common AR(1) site error plus a small independent zone error."""
    rng = random.Random(SEED)
    e = [rng.gauss(0, SIGMA)]
    innov = SIGMA * math.sqrt(1 - RHO * RHO)
    for _ in range(n - 1):
        e.append(RHO * e[-1] + rng.gauss(0, innov))
    zr = random.Random(f"{SEED}:{zone}")
    return [x + zr.gauss(0, ZONE_SIGMA) for x in e]


def scenario_forecast(issue_at: str = ISSUE_AT, hours: int = 72, enabled: bool = True) -> dict[str, Any]:
    issued = datetime.fromisoformat(issue_at)
    if not enabled:
        return unavailable(issue_at, "Forecast service switched off for this sandbox (test T71).")
    start = issued.replace(minute=0, second=0) + timedelta(hours=1)
    zones: dict[str, list[dict[str, Any]]] = {}
    for z in ("A", "B", "C", "D"):
        errs = _errors(z, hours)
        rows = []
        for i in range(hours):
            t = start + timedelta(hours=i)
            d = t.date()
            obs = season_actual(z, d, t.hour)
            if obs is None:
                continue
            lead_days = max(1, math.ceil((t - issued).total_seconds() / 86400))
            sigma = SIGMA * (1 + 0.15 * (lead_days - 1))
            e = errs[i] * (1 + 0.15 * (lead_days - 1))
            injected = None
            for iz, iday, h0, h1, delta, tid in INJECTIONS:
                if iz == z and d.isoformat() == iday and h0 <= t.hour <= h1:
                    e += delta
                    injected = tid
            point = round(obs + e, 2)
            half = round(Z90 * sigma, 2)
            hi = round(point + half, 2)
            rows.append({
                "zone_id": z, "valid_hour": t.isoformat(), "lead_days": lead_days,
                "wbgt_c": point, "wbgt_c_interval_90": [round(point - half, 2), hi],
                "twl_band_probs": band_probs(point, sigma),
                "planning_band": band_of(hi), "median_band": band_of(point),
                "provenance": "forecast", **({"scenario_injection": injected} if injected else {}),
            })
        zones[z] = rows
    return {
        "mode": "scenario",
        "issued_at": issue_at,
        "provenance": "forecast",
        "available": True,
        "zones": zones,
        "method": {
            "wbgt": "liljegren@thermofeel, per-zone shade blend",
            "forecast": "emulated day-ahead forecast: replayed weather + seeded error model (site AR(1) sigma 0.5 C, rho 0.85; zone sigma 0.12 C)",
            "interval": "90% interval = point +/- 1.645 sigma (sigma 0.5 C, +15% per lead day)",
            "planning_band": "band of the upper end of the 90% interval (Appendix G26)",
            "version": "foresee-scenario@1.0.0",
        },
        "label": "SIMULATION: synthetic site, replayed Abu Dhabi weather, emulated forecast error",
        "injections": [{"zone": iz, "day": iday, "hours": f"{h0:02d}:00-{h1:02d}:59", "delta_c": delta, "test": tid}
                       for iz, iday, h0, h1, delta, tid in INJECTIONS],
    }


def unavailable(issue_at: str, reason: str) -> dict[str, Any]:
    return {"mode": "unavailable", "issued_at": issue_at, "available": False, "provenance": "forecast",
            "zones": {}, "reason": reason, "label": "Forecast unavailable: the season's standard plan applies"}


def slot_value(fc: dict[str, Any], zone: str, when: datetime, key: str = "hi") -> float | None:
    """Interpolate a forecast value (point or upper bound) at a local time."""
    rows = fc.get("zones", {}).get(zone) or []
    if not rows:
        return None
    pts = []
    for r in rows:
        t = datetime.fromisoformat(r["valid_hour"]) + timedelta(minutes=30)  # hour centre
        v = r["wbgt_c"] if key == "point" else r["wbgt_c_interval_90"][1]
        pts.append((t, v))
    if when <= pts[0][0]:
        return pts[0][1]
    for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
        if t0 <= when <= t1:
            f = (when - t0).total_seconds() / max(1.0, (t1 - t0).total_seconds())
            return round(v0 + (v1 - v0) * f, 2)
    return pts[-1][1]


# ---------------------------------------------------------------- live mode --
_LIVE_CACHE: dict[str, Any] = {"at": 0.0, "data": None}
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"


def live_forecast(lat: float = 24.45, lon: float = 54.38, timeout_s: float = 8.0,
                  enabled: bool = True) -> dict[str, Any]:
    now = datetime.now(timezone(timedelta(hours=4)))
    if not enabled:
        return unavailable(now.isoformat(), "Forecast service switched off for this sandbox (test T71).")
    if _LIVE_CACHE["data"] and time.time() - _LIVE_CACHE["at"] < 3600:
        return _LIVE_CACHE["data"]
    params = {
        "latitude": lat, "longitude": lon, "timezone": "Asia/Dubai", "forecast_days": 4,
        "wind_speed_unit": "ms",
        "hourly": "temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m,"
                  "shortwave_radiation,direct_radiation",
    }
    try:
        with httpx.Client(timeout=timeout_s) as client:
            r = client.get(OPEN_METEO, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as exc:  # network, quota or format problems
        return unavailable(now.isoformat(), f"Forecast provider unavailable ({type(exc).__name__}).")
    try:
        out = _from_open_meteo(data, lat, lon, now)
    except Exception as exc:
        return unavailable(now.isoformat(), f"Forecast data failed validation ({type(exc).__name__}); quarantined.")
    _LIVE_CACHE.update(at=time.time(), data=out)
    return out


_EXPERIENCE: dict[str, tuple[float, float]] = {}


def experience_range(zone: str) -> tuple[float, float]:
    """WBGT range the forecast method has seen for this zone (2025 replayed season). Outside it, values are
    flagged and the interval is widened (test T74)."""
    if zone not in _EXPERIENCE:
        from .model import season
        vals = list(season()[zone].values())
        _EXPERIENCE[zone] = (min(vals), max(vals))
    return _EXPERIENCE[zone]


OOD_MARGIN_C = 1.0      # tolerance outside the seen range
OOD_WIDEN = 1.5         # interval widening when outside experience


def _from_open_meteo(data: dict[str, Any], lat: float, lon: float, now: datetime) -> dict[str, Any]:
    h = data["hourly"]
    units = data.get("hourly_units", {})
    # Unit checks (test T73): refuse silently converted data.
    if units.get("temperature_2m") not in ("°C", "C", None):
        raise ValueError("unexpected temperature unit")
    if units.get("wind_speed_10m") not in ("m/s", None):
        raise ValueError("unexpected wind unit")
    zones: dict[str, list[dict[str, Any]]] = {z: [] for z in SHADE}
    issued = now.replace(minute=0, second=0, microsecond=0)
    for i, t in enumerate(h["time"]):
        local = datetime.fromisoformat(t).replace(tzinfo=timezone(timedelta(hours=4)))
        if local <= issued or local > issued + timedelta(hours=72):
            continue
        vals = [h[k][i] for k in ("temperature_2m", "relative_humidity_2m", "surface_pressure", "wind_speed_10m",
                                  "shortwave_radiation", "direct_radiation")]
        if any(v is None for v in vals):
            continue
        ta, rh, p, wind, sw, direct = vals
        if not (-10 < ta < 60 and 0 <= rh <= 100 and 800 < p < 1100 and 0 <= wind < 60):
            raise ValueError("value out of physical range")
        mid_utc = (local - timedelta(minutes=30)).astimezone(timezone.utc)
        cz = cos_solar_zenith(mid_utc, lat, lon)
        lead_days = max(1, math.ceil((local - issued).total_seconds() / 86400))
        sigma = 0.8 * (1 + 0.15 * (lead_days - 1))  # provisional, uncalibrated for NWP
        for z, sf in SHADE.items():
            if z == "D":
                w = wbgt_liljegren(ta, rh, p, wind, sw, direct, cz, shade_fraction=1.0) - 1.5
            else:
                w = wbgt_liljegren(ta, rh, p, wind, sw, direct, cz, shade_fraction=sf)
            w = round(w, 2)
            lo_x, hi_x = experience_range(z)
            ood = not (lo_x - OOD_MARGIN_C <= w <= hi_x + OOD_MARGIN_C)
            sig = sigma * (OOD_WIDEN if ood else 1.0)
            half = round(Z90 * sig, 2)
            zones[z].append({
                "zone_id": z, "valid_hour": local.isoformat(), "lead_days": lead_days, "wbgt_c": w,
                "wbgt_c_interval_90": [round(w - half, 2), round(w + half, 2)],
                "twl_band_probs": band_probs(w, sig), "planning_band": band_of(w + half),
                "median_band": band_of(w), "provenance": "forecast", "estimate": "physics_only",
                **({"flags": ["outside_model_experience"]} if ood else {}),
            })
    return {
        "mode": "live", "issued_at": issued.isoformat(), "available": True, "provenance": "forecast",
        "zones": zones,
        "method": {"wbgt": "liljegren@thermofeel from Open-Meteo hourly forecast weather",
                   "interval": "provisional 90% interval (sigma 0.8 C); site calibration pending (pilot); widened "
                               "x1.5 and flagged outside the method's experience",
                   "planning_band": "band of the upper end of the 90% interval (Appendix G26)",
                   "version": "foresee-live@1.0.0"},
        "label": "Live forecast for the site location. Weather data by Open-Meteo.com (CC BY 4.0).",
        "attribution": "Weather data by Open-Meteo.com, CC BY 4.0",
    }
