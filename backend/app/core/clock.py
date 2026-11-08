"""Wall clock for drills (real time), kept in one place so tests can move it without sleeping.

The sandbox normally runs on a scenario clock that only moves when someone changes the scene. During an
observed drill it runs in real time instead, so the ledger's own timestamps measure what people really did.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

_offset = 0.0


def wall() -> float:
    """Seconds since the epoch (real time, plus any test shift)."""
    return time.time() + _offset


def wall_iso(t: float | None = None) -> str:
    """UTC ISO 8601 to the second."""
    return datetime.fromtimestamp(int(wall() if t is None else t), timezone.utc).isoformat()


def shift(seconds: float) -> None:
    """Tests only: move the wall clock forward."""
    global _offset
    _offset += seconds


def reset() -> None:
    global _offset
    _offset = 0.0
