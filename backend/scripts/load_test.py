"""Load test: many judges using the sandbox at once, against one server process.

    # one CPU, like the Cloud Run setting (--cpu 1); the per-address limit is raised because every simulated
    # judge comes from the same local address
    BARDAN_RATE_PER_MIN=100000 taskset -c 0 python -m uvicorn app.main:app --port 8092 --workers 1
    python scripts/load_test.py --base http://127.0.0.1:8092 --pid <uvicorn pid>

Phase 1 ("panel"): N judges arrive together and each runs the full tour once, including the scene jump that runs
the CP-SAT planner. Phase 2 ("steady"): M judges keep clicking through the light screens for a fixed time.
Latency is reported per step (median, 95th percentile, worst), with errors, throughput and the server's memory.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import platform
import statistics
import time
from collections import defaultdict
from pathlib import Path

import httpx

LAT: dict[str, list[float]] = defaultdict(list)
ERR: dict[str, int] = defaultdict(int)
CODES: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
DETAIL: list[str] = []
RETRIES: dict[str, int] = defaultdict(int)


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


def rss_mb(pid: int | None) -> float | None:
    if not pid:
        return None
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return round(int(line.split()[1]) / 1024, 1)
    return None


async def call(c: httpx.AsyncClient, name: str, method: str, path: str, token: str | None = None, body=None,
               idem: str | None = None):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    if idem:
        h["Idempotency-Key"] = idem          # as the app sends it: a retried request is answered, not repeated
    t0 = time.perf_counter()
    r, ok = None, False
    # Like a browser, retry once when a reused connection was dropped. Only GETs and requests carrying an
    # Idempotency-Key are retried, so a retry can never repeat an action; retries are counted.
    for attempt in range(2 if (method == "GET" or idem or path.endswith("/session")) else 1):
        try:
            r = await c.request(method, path, json=body, headers=h)
            ok = r.status_code < 400
            break
        except httpx.HTTPError:
            if attempt == 0:
                RETRIES[name] += 1
    LAT[name].append((time.perf_counter() - t0) * 1000)
    if not ok:
        ERR[name] += 1
        CODES[name][str(r.status_code if r is not None else "network")] += 1
        if len(DETAIL) < 10:
            DETAIL.append(f"{name} {method} {path} {body} -> {r.status_code if r is not None else 'network'} "
                          f"{(r.text[:200] if r is not None else '')}")
    return r


async def judge(c: httpx.AsyncClient, full: bool) -> None:
    r = await call(c, "session", "POST", "/v1/sandbox/session", body={"persona": "ravi"})
    if r is None or r.status_code >= 400:
        return
    sid, w = r.json()["sandbox_id"], r.json()["token"]
    s = (await call(c, "session", "POST", "/v1/sandbox/session", body={"persona": "joseph", "sandbox_id": sid})).json()["token"]
    h = (await call(c, "session", "POST", "/v1/sandbox/session", body={"persona": "sara", "sandbox_id": sid})).json()["token"]
    if full:
        await call(c, "scene_jump_with_planner", "POST", "/v1/sandbox/scene", s, {"scene": "water"})
    await call(c, "sandbox_state", "GET", "/v1/sandbox/state", w)
    await call(c, "worker_today", "GET", "/v1/worker/today", w)
    r = await call(c, "worker_report", "POST", "/v1/worker/reports", w, {"intent": "RESOURCE_WATER_UNAVAILABLE"})
    task = (r.json().get("task") or {}).get("id") if r is not None and r.status_code < 400 else None
    await call(c, "speak_intake_offline", "POST", "/v1/assist/intake", w, {"text": "water finished, my head hurts"})
    await call(c, "tasks", "GET", "/v1/tasks", s)
    if task:
        for action in ("accept", "start"):
            await call(c, "task_event", "POST", f"/v1/tasks/{task}/events", s, {"action": action}, idem=action)
        await call(c, "task_event", "POST", f"/v1/tasks/{task}/events", s,
                   {"action": "report_complete", "evidence": {"kind": "water_point_check",
                                                              "water_actually_delivered": True}}, idem="done")
    await call(c, "operations", "GET", "/v1/sites/site_demo/operations", s)
    await call(c, "forecast", "GET", "/v1/sites/site_demo/forecast", s)
    await call(c, "compliance", "GET", "/v1/sites/site_demo/compliance", h)
    await call(c, "trace", "GET", "/v1/trace", h)
    await call(c, "evaluation_report", "GET", "/v1/reports/evaluation")


async def steady(c: httpx.AsyncClient, seconds: float) -> int:
    r = await call(c, "session", "POST", "/v1/sandbox/session", body={"persona": "joseph"})
    if r is None or r.status_code >= 400:
        return 0
    s = r.json()["token"]
    n = 0
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        for name, path in (("sandbox_state", "/v1/sandbox/state"), ("tasks", "/v1/tasks"),
                           ("operations", "/v1/sites/site_demo/operations")):
            await call(c, name, "GET", path, s)
            n += 1
        await asyncio.sleep(0.5)        # a person reading the screen
    return n


def summary() -> dict:
    out = {}
    for k, v in sorted(LAT.items()):
        v = sorted(v)
        out[k] = {"n": len(v), "p50_ms": round(statistics.median(v)), "p95_ms": round(v[int(0.95 * (len(v) - 1))]),
                  "max_ms": round(v[-1]), "errors": ERR.get(k, 0), "retried": RETRIES.get(k, 0),
                  **({"error_codes": dict(CODES[k])} if k in CODES else {})}
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8092")
    ap.add_argument("--pid", type=int, default=None, help="server process id, to read its memory")
    ap.add_argument("--panel", type=int, default=20, help="judges arriving together (full tour)")
    ap.add_argument("--steady", type=int, default=50, help="judges clicking through light screens")
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--out", default=None)
    ap.add_argument("--server-cpus", default="1 core (taskset -c 0)", help="how the server was limited, for the record")
    a = ap.parse_args()
    limits = httpx.Limits(max_connections=200, max_keepalive_connections=200)
    async with httpx.AsyncClient(base_url=a.base, timeout=120, limits=limits) as c:
        await call(c, "warm_up", "GET", "/v1/reports/evaluation")
        m0 = rss_mb(a.pid)
        t0 = time.perf_counter()
        await asyncio.gather(*(judge(c, True) for _ in range(a.panel)))
        panel_s = time.perf_counter() - t0
        panel = summary()
        m1 = rss_mb(a.pid)
        LAT.clear()
        ERR.clear()
        CODES.clear()
        RETRIES.clear()
        t0 = time.perf_counter()
        counts = await asyncio.gather(*(steady(c, a.seconds) for _ in range(a.steady)))
        steady_s = time.perf_counter() - t0
        m2 = rss_mb(a.pid)
        result = {
            "run": {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "server_cpus": a.server_cpus,
                    "cpu_model": _cpu_model(), "python": platform.python_version(),
                    "note": "Local run, one server process, client on the same machine (no network latency, no cold "
                            "start). The per-address limit was raised for the test; every simulated judge has its "
                            "own sandbox."},
            "panel": {"judges": a.panel, "wall_s": round(panel_s, 1), "steps": panel},
            "steady": {"judges": a.steady, "seconds": round(steady_s, 1), "requests": sum(counts),
                       "requests_per_s": round(sum(counts) / steady_s, 1), "steps": summary()},
            "first_errors": DETAIL,
            "memory_mb": {"start": m0, "after_panel": m1, "after_steady": m2,
                          "per_sandbox_full_tour": round((m1 - m0) / a.panel, 2) if m0 and m1 else None},
        }
    print(json.dumps(result, indent=1))
    if a.out:
        Path(a.out).write_text(json.dumps(result, indent=1) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
