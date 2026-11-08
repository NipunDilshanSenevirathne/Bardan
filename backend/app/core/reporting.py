"""Compliance report validation (finalsystem.md §11.9, §22.6; tests T64, T65).

A report that hides failures is worse than no report. Before a compliance
report is shown or exported it must pass these checks:

  tiers_separate        evidence tiers are reported one by one; a completion rate
                        that merges, for example, E2 attestations with E4 independent
                        checks is refused (T65)
  exclusions_disclosed  failed alerts and rejected readings are counted and shown,
                        never silently dropped (T64)
  denominators          every rate comes with its numerator and denominator
"""
from __future__ import annotations

import re
from typing import Any

TIER = re.compile(r"^E[0-4]$")


def validate(report: dict[str, Any]) -> dict[str, Any]:
    problems: list[dict[str, str]] = []
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": ok})
        if not ok:
            problems.append({"check": name, "detail": detail})

    # 1. Evidence tiers are never merged.
    tiers = report.get("verified_by_tier")
    merged = [k for k in (tiers or {}) if not TIER.match(str(k))]
    rates = report.get("rates") or []
    mixed = [r.get("name", "?") for r in rates if len(set(r.get("tiers") or [])) > 1]
    check("tiers_separate", tiers is not None and not merged and not mixed and report.get("tiers_never_merged") is True,
          "merged tiers: " + ", ".join(merged + mixed) if (merged or mixed) else "tier breakdown missing")
    # 2. Exclusions are disclosed.
    ex = report.get("exclusions")
    ok = isinstance(ex, dict) and all(k in ex for k in ("rejected_readings", "failed_alerts")) and \
        ex.get("disclosed") is True
    check("exclusions_disclosed", ok, "failed alerts or rejected readings are not disclosed")
    # 3. Every rate has a numerator and a denominator.
    bad = [r.get("name", "?") for r in rates if r.get("numerator") is None or not r.get("denominator")]
    check("denominators", not bad, "rates without a denominator: " + ", ".join(bad) if bad else "")
    return {"valid": not problems, "problems": problems, "checks": checks, "validator": "report-validation@1.0"}
