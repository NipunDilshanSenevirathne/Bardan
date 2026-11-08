# Load test

**Question.** Can one Cloud Run instance (1 vCPU, 1 GiB, `--max-instances 1`) carry a judging panel, or a room of
people opening the same link at once?

**Method.** `backend/scripts/load_test.py` runs simulated judges against one server process limited to one CPU core
(`taskset -c 0`), with the client on the same machine. Each simulated judge has its own sandbox and does what a
person does in the tour:

* **Full tour** (arrivals): sign in as three personas, jump to the water scene (which runs the CP-SAT planner for
  the evening-before step), open the worker's screen, report missing water, run offline speech intake, open the
  task list, accept, start and report the fix with evidence, then open operations, forecast, compliance, the AI
  trace and the evaluation report.
* **Light screens** (steady use): the shell state, the task list and the site overview, every half second.

Task actions carry an `Idempotency-Key`, as the app sends them. The client retries a dropped connection once,
as a browser does, and counts it; no retry was needed in the runs below. The per-address limit was raised for
the test because every simulated judge comes from the same local address.

**Results** (8 Nov 2026, Intel Xeon 2.10 GHz, one core; raw files in `backend/reports/load_test_*.json`, also shown
in the Trust Centre under *Release tests*):

| Run | What happened | Result |
|---|---|---|
| 20 judges arrive together, full tour | 341 requests | All done in 5.3 s; planner step median 3.2 s, 95th percentile 3.7 s; 0 errors |
| 50 judges clicking for a minute | 16,446 requests | 270 requests a second; median 11 to 13 ms, 95th percentile 38 to 41 ms, slowest 0.6 s; 0 errors |
| 100 judges in the same second, full tour | 1,701 requests | All done in 30.5 s; planner step median 8.5 s, 95th percentile 10.4 s; 0 errors |
| Memory | after 172 sandboxes | 157 MB at start, about 0.8 MB per sandbox after a full tour (the first 20 add about 2.8 MB each, mostly one-time warm-up); the 300-sandbox cap stays far below 1 GiB |

**Reading it.** A panel of judges, or 50 people using the screens continuously, is comfortable on one instance. The
only slow step under a burst is the CP-SAT planner, which is CPU-bound: when 100 people trigger it in the same
second, each waits up to about 10 to 14 seconds. A real panel arrives over minutes, not in one second.

**Not included.** Network latency between the phone and the server, Cloud Run cold start (the first request after
an idle period), and live AI calls (the test ran with the AI provider not configured, so speech and chat use the
offline paths; live AI calls depend on the provider's free-tier rate limits, which the app meters and falls back
from).

**What a deployment would change.** A site deployment stores state in PostgreSQL with a separate clinical database
(finalsystem.md §19.6 and §21.3, stack table in §28), runs the API stateless behind more than one instance, and moves the planner into a background
job, so a burst of planning requests queues without slowing the screens. The judge sandbox keeps everything in
memory on purpose: every sandbox is synthetic and resets within the hour, so there is nothing to keep, and one
instance means every request reaches the same sandbox. Observed drill results are the one thing worth keeping, and
they are kept by export and publication (docs/DRILL-PROTOCOL.md, step 7).
