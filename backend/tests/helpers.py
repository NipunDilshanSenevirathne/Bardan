"""Small shared helpers for the release tests."""
from __future__ import annotations

from typing import Any


def base_input(**over) -> dict[str, Any]:
    """A routine policy input (acclimatized worker, heavy outdoor task, fresh TWL 230)."""
    inp = {"now": "2026-08-06T10:00:00+04:00", "zone": {"outdoor": True, "direct_sun": True},
           "task": {"workload": "heavy", "outdoor": True}, "worker": {"acclimatization": "acclimatized", "day": 30},
           "observation": {"kind": "twl", "value": 230, "observed_at": "2026-08-06T09:55:00+04:00",
                           "provenance": "measured"},
           "resources": {"water_available": True}, "symptoms": [], "exemption": None}
    inp.update(over)
    return inp
