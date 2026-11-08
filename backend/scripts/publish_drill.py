"""Publish an observed drill series with the release (docs/DRILL-PROTOCOL.md, step 7).

    python scripts/publish_drill.py path/to/bardan-drills-drs_xxxx.json --where "Role-play, Colombo, 4 adults"

The export is checked first: its hash, and every drill's result and the summary recomputed from the recorded
moments. A file that fails any check is refused, so the Trust Centre can only ever show what the drill console
recorded. Nothing in the export is edited; a short description of the conditions is stored beside it.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.drill import check_export, published_path  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("export", type=Path, help="JSON file downloaded from the drill console")
    ap.add_argument("--where", required=True, help="Conditions in a few words (no names), e.g. 'Role-play, 4 adults'")
    args = ap.parse_args()
    body = json.loads(args.export.read_text(encoding="utf-8"))
    problems = check_export(body)
    if problems:
        print("Refused: the export does not check out:", ", ".join(problems))
        return 1
    if not any(d.get("state") == "ended" for d in body.get("drills", [])):
        print("Refused: the series has no completed drill.")
        return 1
    path = published_path()
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"note": "", "series": []}
    if any(s.get("sha256") == body["sha256"] for s in data["series"]):
        print("Already published.")
        return 0
    body["published"] = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                         "conditions": args.where.strip()[:160]}
    data["series"].append(body)
    data["note"] = ("Observed drill results published with this release. Each entry is an unedited export from the "
                    "drill console; the app re-checks its hash and recomputes every result from the recorded "
                    "moments before showing it.")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    arms = body["summary"]["arms"]
    print(f"Published {body['series']['id']}: current {arms['current']['drills_run']} drills, "
          f"Bardan {arms['bardan']['drills_run']} drills -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
