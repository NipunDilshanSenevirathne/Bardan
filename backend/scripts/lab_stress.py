"""Stress the Scenario Lab and shift simulator with random days (docs/TESTING.md).

    cd backend && python scripts/lab_stress.py

Random weather, tasks, workers, clothing and mid-shift changes. Every plan shown must pass the independent re-check.
When a day has no protected plan, the run lets work wait until tomorrow (one of the permitted options) and goes on;
if that is not enough, the day is reported as waiting for another permitted option (more seats or shaded places).
Exits non-zero if any plan shown failed the re-check, or if the planner raised an error.
"""
import copy
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.planner import lab  # noqa: E402

KINDS = ["hotter", "humid", "calm", "cloud", "water_out", "ac_fails", "symptom", "wearable"]
SEEDS = (42, 7, 2026, 99)
DAYS = 30


def random_scenario(rng: random.Random) -> dict:
    sc = copy.deepcopy(rng.choice(lab.presets()))
    sc["weather"].update(peak_c=rng.randint(30, 47), humidity_pct=rng.randint(15, 70),
                         wind_ms=rng.choice([0.5, 1, 2, 3.5, 6]), sky=rng.choice(["clear", "haze", "cloud"]))
    for t in sc["tasks"]:
        t.update(hours=rng.choice([1, 2, 3, 4, 5]), exposure=rng.choice(["sun", "partial", "shade", "indoor"]),
                 workload=rng.choice(["light", "moderate", "heavy"]), can_wait=rng.random() < 0.8,
                 one_piece=rng.random() < 0.2, clothing=rng.choice(["work_clothes", "coveralls", "double_layer"]))
    for w in sc["workers"]:
        w.update(status=rng.choice(["new", "returning", "acclimatized"]), day=rng.randint(1, 5))
    return sc


def random_event(rng: random.Random, sc: dict, at: str) -> dict | None:
    kind = rng.choice(KINDS)
    target = None
    if kind == "water_out":
        target = rng.choice(sc["tasks"])["id"]
    elif kind == "ac_fails":
        cooled = [r for r in sc["rest_areas"] if r["type"] == "cooled"]
        if not cooled:
            return None
        target = cooled[0]["id"]
    elif kind in ("symptom", "wearable"):
        target = rng.choice(sc["workers"])["id"]
    return {"type": kind, "at": at, "target": target}


def main() -> int:
    failures = 0
    for seed in SEEDS:
        rng = random.Random(seed)
        bad, waiting, steps, t0 = [], 0, 0, time.time()
        for day in range(DAYS):
            sc = random_scenario(rng)
            r = lab.run(sc)
            if not r.get("plan"):
                waiting += 1
                continue
            if r["revalidation"]["result"] != "valid":
                bad.append(("initial plan", day, r["revalidation"]["violations"][:2]))
            prev, events, now = r["plan"], [], 0
            while now < 27:
                now += rng.choice([1, 1, 1, 2])
                if now > 27:
                    break
                at = lab.slot_label(now)
                if rng.random() < 0.35:
                    ev = random_event(rng, sc, at)
                    if ev:
                        events.append(ev)
                steps += 1
                try:
                    r = lab.run(sc, now=at, previous=prev, events=list(events))
                except Exception as exc:  # noqa: BLE001
                    bad.append(("error", day, at, repr(exc)))
                    break
                if not r.get("plan"):
                    waiting += 1
                    for t in sc["tasks"]:
                        t["can_wait"] = True
                    r = lab.run(sc, now=at, previous=prev, events=list(events))
                if r.get("plan"):
                    if r["revalidation"]["result"] != "valid":
                        bad.append(("invalid", day, at, r["revalidation"]["violations"][:2]))
                    prev = r["plan"]
                else:
                    print(f"  seed {seed} day {day} {at}: waiting for another permitted option "
                          f"{[x['remedy'] for x in r['diagnosis']['permitted_remedies']]}", flush=True)
        failures += len(bad)
        print(f"seed {seed}: {steps} steps, {waiting} times no protected plan, {len(bad)} failures, "
              f"{time.time() - t0:.0f} s", flush=True)
        for b in bad[:6]:
            print("  ", b, flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
