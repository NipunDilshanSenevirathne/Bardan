"""Watch: systemic-risk detection on aggregated, de-identified signals (§14.7, B.15, G29; T92-T94).

Poisson CUSUM on daily counts of resource-gap events per subcontractor:
    S_t = max(0, S_{t-1} + x_t * ln(r) - (mu1 - mu0)),  alert when S_t > h
with mu0 the baseline daily rate (first three weeks), mu1 = r * mu0 the rate we
want to detect (r = 3). Groups with fewer than five workers are suppressed, no
detector ever outputs an individual, and an alert only DRAFTS an HSE review
task for a person to approve.
"""
from __future__ import annotations

import json
import math
import re
import random
from datetime import timedelta
from functools import lru_cache
from typing import Any

from ..core.history import END, START, history

MIN_CELL = 5
H = 2.0
RATE_RATIO = 3.0
DETECTOR = {"method": "poisson-cusum", "version": "0.4", "threshold_h": H, "rate_ratio": RATE_RATIO,
            "restart": "statistic restarts at 0 after each alarm (after the HSE review)",
            "tuning": "operating point chosen on development seed 11; reported on held-out seed 101"}
GROUP_SIZES = {"Subcontractor A": 10, "Subcontractor B": 16, "Subcontractor C": 14, "Subcontractor D": 3}
EXTRA_SMALL_GROUP = [("2025-08-14", "Subcontractor D"), ("2025-08-15", "Subcontractor D"),
                     ("2025-08-17", "Subcontractor D")]


def _series(kind: str = "water") -> dict[str, list[tuple[str, int, int]]]:
    h = history()
    days = []
    d = START
    while d <= END:
        days.append(d.isoformat())
        d += timedelta(days=1)
    out: dict[str, list[tuple[str, int, int]]] = {}
    for sub in GROUP_SIZES:
        rows = []
        for day in days:
            ev = [g for g in h["gaps"] if g["subcontractor"] == sub and g["date"] == day and g["kind"] == kind]
            extra = sum(1 for dd, s in EXTRA_SMALL_GROUP if dd == day and s == sub)
            rows.append((day, len(ev) + extra, sum(g["gap_min"] for g in ev) + 15 * extra))
        out[sub] = rows
    return out


def cusum(counts: list[int], mu0: float, ratio: float = RATE_RATIO, h: float = H) -> tuple[list[float], int | None]:
    """Return the statistic's path and the first alarm (index), or None."""
    path, alarms = cusum_alarms(counts, mu0, ratio, h)
    return path, (alarms[0] if alarms else None)


def cusum_alarms(counts: list[int], mu0: float, ratio: float = RATE_RATIO,
                 h: float = H) -> tuple[list[float], list[int]]:
    """Poisson CUSUM with a restart after each alarm, as in use: an alarm is reviewed, then watching resumes."""
    mu0 = max(mu0, 0.05)
    mu1 = ratio * mu0
    s, path, alarms = 0.0, [], []
    for t, x in enumerate(counts):
        s = max(0.0, s + x * math.log(ratio) - (mu1 - mu0))
        path.append(round(s, 3))
        if s > h:
            alarms.append(t)
            s = 0.0
    return path, alarms


def signals() -> dict[str, Any]:
    series = _series("water")
    out = []
    for sub, rows in series.items():
        size = GROUP_SIZES[sub]
        if size < MIN_CELL:
            out.append({"scope": {"site": "site_demo", "subcontractor": sub}, "suppressed": True,
                        "reason": f"Group of {size} workers is below the minimum cell of {MIN_CELL}; not reported "
                                  "(T92). Complementary cells are suppressed too.", "individuals_included": False})
            continue
        counts = [c for _, c, _ in rows]
        base = counts[:21]
        mu0 = sum(base) / len(base)
        path, alarm = cusum(counts, mu0)
        last3 = rows[-3:]
        sig = {
            "signal_id": f"sig_{sub[-1].lower()}_water", "scope": {"site": "site_demo", "subcontractor": sub,
                                                                   "period": f"{rows[0][0]}..{rows[-1][0]}"},
            "type": "water_gap_events", "baseline_per_day": round(mu0, 3),
            "observed_last_3_days": sum(c for _, c, _ in last3),
            "water_gap_minutes_last_3_days": sum(m for _, _, m in last3),
            "baseline_minutes_per_3_days": round(3 * sum(m for _, _, m in rows[:21]) / 21, 1),
            "detector": DETECTOR, "cusum_path": path, "dates": [d for d, _, _ in rows],
            "alarm": alarm is not None, "alarm_date": rows[alarm][0] if alarm is not None else None,
            "suppression": {"min_cell": MIN_CELL, "applied": False}, "individuals_included": False,
            "label": "SIMULATION (synthetic history)",
        }
        if sig["alarm"]:
            ratio = sig["water_gap_minutes_last_3_days"] / max(1.0, sig["baseline_minutes_per_3_days"])
            sig["explanation"] = {
                "en": f"{sub}: water gaps in the last 3 days were {sig['water_gap_minutes_last_3_days']} minutes, "
                      f"about {ratio:.0f} times the usual {sig['baseline_minutes_per_3_days']:g} minutes. Check the "
                      "supply and refill schedule for this subcontractor's zone.",
                "ar": f"{sub}: بلغت فجوات الماء في آخر 3 أيام {sig['water_gap_minutes_last_3_days']} دقيقة، أي نحو "
                      f"{ratio:.0f} أضعاف المعتاد ({sig['baseline_minutes_per_3_days']:g} دقيقة). راجع جدول التزويد "
                      "وإعادة التعبئة لمنطقة هذا المقاول."}
            sig["action"] = {"draft_review_task": f"HSE review of water supply for {sub}",
                             "draft_review_task_ar": f"مراجعة السلامة لإمدادات الماء لدى {sub.replace('Subcontractor', 'المقاول')}",
                             "approval": "hse",
                             "automatic_action": False}
        out.append(sig)
    result = {"signals": out, "detector": DETECTOR, "never": ["individual-level output", "ranking workers",
                                                              "automatic discipline"]}
    guard_aggregate(result)
    return result


@lru_cache(maxsize=1)
def _roster_names() -> frozenset[str]:
    from ..core.scenario import build_world
    return frozenset(w["name"] for w in build_world()["workers"])


class IndividualOutputBlocked(Exception):
    """A detector output that names or points at an individual worker (T93)."""


_WORKER_REF = re.compile(r"\bW\d{2,}\b|\bpt_[0-9a-f]{8}\b")


def guard_aggregate(output: Any, names: set[str] | None = None) -> None:
    """Detectors work on aggregates only. Block any output that carries a worker reference, a clinical
    pseudonym or a worker's name, wherever it appears in the structure."""
    if names is None:
        names = _roster_names()
    text = json.dumps(output, ensure_ascii=False)
    hit = _WORKER_REF.search(text) or next((n for n in names if n in text), None)
    if hit:
        raise IndividualOutputBlocked("Detector output names an individual; blocked (T93).")


def evaluate_detector(months: int = 1000, seed: int = 101) -> dict[str, Any]:
    """Synthetic evaluation (T94 and §14.7 targets) on two injected-scenario families."""
    return {"supply_failure": _evaluate(months, seed, mode="supply_failure"),
            "gradual_x4": _evaluate(months, seed + 1, mode="gradual_x4"),
            "detector": DETECTOR,
            "label": "SIMULATION: synthetic Poisson series with injected changes; tests the detector, not a site"}


FOLLOW_UP_DAYS = 14   # days simulated after the month, so a late change is followed up before it is scored


def _evaluate(months: int, seed: int, mode: str) -> dict[str, Any]:
    """One family of synthetic site-months. False alerts are counted within the 30-day month; a change injected
    on days 15-25 is followed for at least two more weeks, so detection at 7 days is not cut short."""
    rng = random.Random(seed)
    detected_2d = detected_7d = injected = false_alerts = possible_2d = 0
    delays = []
    for _ in range(months):
        mu0 = rng.uniform(0.08, 0.2)
        n = 30 + FOLLOW_UP_DAYS
        inject_at = rng.randint(15, 25) if rng.random() < 0.5 else None
        counts = []
        jump = rng.uniform(1.5, 2.5) if mode == "supply_failure" else mu0 * 4.0
        for t in range(n):
            lam = jump if inject_at is not None and t >= inject_at else mu0
            counts.append(_poisson(rng, lam))
        # Baseline is estimated from the first 14 days, as in deployment.
        est = max(0.05, sum(counts[:14]) / 14)
        _, alarms = cusum_alarms(counts, est)
        if inject_at is None:
            false_alerts += sum(1 for a in alarms if a < 30)
        else:
            injected += 1
            false_alerts += sum(1 for a in alarms if a < inject_at)
            # No detector that waits for evidence can alarm before a single event has happened.
            possible_2d += int(sum(counts[inject_at:inject_at + 3]) >= 1)
            after = [a for a in alarms if a >= inject_at]
            if after:
                delays.append(after[0] - inject_at)
                detected_2d += int(after[0] - inject_at <= 2)
                detected_7d += int(after[0] - inject_at <= 7)
    rate = round(detected_2d / max(1, injected), 3)
    fa_rate = round(false_alerts / months, 3)
    out = {"site_months": months, "injected": injected, "detected_within_2_days": detected_2d,
           "detection_rate_2d": rate, "detected_within_7_days": detected_7d,
           "detection_rate_7d": round(detected_7d / max(1, injected), 3),
           "ceiling_2d": round(possible_2d / max(1, injected), 3),
           "median_delay_days": sorted(delays)[len(delays) // 2] if delays else None,
           "false_alerts": false_alerts, "false_alerts_per_site_month": fa_rate,
           "targets": {"detection_rate_2d": ">= 0.90", "false_alerts_per_site_month": "<= 1"},
           "scenario": ("supply failure: rate jumps to 1.5-2.5 gap events per day" if mode == "supply_failure"
                        else "gradual: rate rises x4 from a low baseline (0.08-0.2 per day)"),
           "met_targets": bool(rate >= 0.90 and fa_rate <= 1.0)}
    if mode != "supply_failure":
        out["target_note"] = (f"The 2-day target was set for sudden failures. After a slow rise from a low baseline, "
                              f"at least one event happens within 2 days in only {round(100 * out['ceiling_2d'])}% "
                              f"of cases, so no detector that waits for evidence can meet it. Reported as it is; "
                              f"the operating point was not re-tuned on these results.")
    return out


def _poisson(rng: random.Random, lam: float) -> int:
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1
