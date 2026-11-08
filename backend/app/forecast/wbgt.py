"""WBGT from standard weather variables (Liljegren method via ECMWF thermofeel).

Inputs follow Open-Meteo / ERA5 conventions:
  temperature_2m [C], relative_humidity_2m [%], surface_pressure [hPa],
  wind_speed_10m [m/s], shortwave_radiation [W/m2], direct_radiation [W/m2].

Outputs are labelled "forecast-derived" or "derived": they are estimates,
never instrument readings (finalsystem.md §10.3, §21.2).
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import numpy as np
import thermofeel


def cos_solar_zenith(when_utc: datetime, lat: float, lon: float) -> float:
    """NOAA approximate solar position. Returns cos(zenith), floored at 0."""
    if when_utc.tzinfo is None:
        when_utc = when_utc.replace(tzinfo=timezone.utc)
    when_utc = when_utc.astimezone(timezone.utc)
    doy = when_utc.timetuple().tm_yday
    hour = when_utc.hour + when_utc.minute / 60.0 + when_utc.second / 3600.0
    gamma = 2.0 * math.pi / 365.0 * (doy - 1 + (hour - 12) / 24.0)
    eqtime = 229.18 * (
        0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma)
    )
    decl = (
        0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma)
    )
    time_offset = eqtime + 4.0 * lon
    tst = hour * 60.0 + time_offset
    ha = math.radians(tst / 4.0 - 180.0)
    lat_r = math.radians(lat)
    cosz = math.sin(lat_r) * math.sin(decl) + math.cos(lat_r) * math.cos(decl) * math.cos(ha)
    return max(0.0, cosz)


def wbgt_liljegren(
    t_c: float, rh: float, pressure_hpa: float, wind_ms: float,
    ssrd: float, direct: float, cosz: float, shade_fraction: float = 0.0,
) -> float:
    """WBGT in Celsius. shade_fraction 0 = full sun, 1 = full shade."""
    t_k = np.array([t_c + 273.15])
    rh_a = np.array([max(1.0, min(100.0, rh))])
    p = np.array([pressure_hpa])
    va = np.array([max(0.1, wind_ms)])
    cz = np.array([max(cosz, 0.0)])

    def run(ssrd_val: float, fdir_val: float) -> float:
        out = thermofeel.calculate_wbgt_liljegren(
            t_k, rh_a, p, va, np.array([max(0.0, ssrd_val)]), np.array([fdir_val]), cz
        )
        val = float(out[0]) - 273.15
        if math.isnan(val):
            # Non-convergence: fall back to the no-radiation screening estimate.
            val = float(thermofeel.calculate_wbgt_simple(t_k, rh_a)[0]) - 273.15
        return val

    fdir = 0.0 if ssrd <= 1 else max(0.0, min(0.9, direct / ssrd))
    sun = run(ssrd, fdir)
    if shade_fraction <= 0:
        return round(sun, 2)
    diffuse = max(0.0, ssrd - direct)
    shade = run(diffuse * 0.6, 0.0)
    return round(shade_fraction * shade + (1 - shade_fraction) * sun, 2)


def hourly_series(hourly: dict, lat: float, lon: float, utc_offset_hours: int = 4) -> list[dict]:
    """Turn an Open-Meteo hourly block (local times) into WBGT records."""
    out = []
    times = hourly["time"]
    for i, t in enumerate(times):
        local = datetime.fromisoformat(t)
        # Radiation is the mean over the preceding hour: use the mid-point sun angle.
        mid_utc = (local - timedelta(hours=utc_offset_hours, minutes=30)).replace(tzinfo=timezone.utc)
        cosz = cos_solar_zenith(mid_utc, lat, lon)
        rec = {
            "time": t,
            "t": hourly["temperature_2m"][i],
            "rh": hourly["relative_humidity_2m"][i],
            "p": hourly["surface_pressure"][i],
            "wind": hourly["wind_speed_10m"][i],
            "ssrd": hourly["shortwave_radiation"][i],
            "direct": hourly["direct_radiation"][i],
            "cosz": round(cosz, 4),
        }
        if None in (rec["t"], rec["rh"], rec["p"], rec["wind"], rec["ssrd"], rec["direct"]):
            rec["wbgt_sun"] = None
        else:
            rec["wbgt_sun"] = wbgt_liljegren(rec["t"], rec["rh"], rec["p"], rec["wind"], rec["ssrd"], rec["direct"], cosz)
        out.append(rec)
    return out
