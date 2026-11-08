# Testing and evidence

Six layers of evidence, all reproducible from the repository; the first four are visible in the Trust Centre.

| Layer | Command | Where it shows |
|---|---|---|
| Release tests (server, pytest) | `make report` or `cd backend && pytest --bardan-report` | Trust Centre → Release tests |
| Device engine tests (TypeScript, vitest) | `cd frontend && npm run test:report` | merged into the same report |
| AI evaluation, red team, workflow checks | `GET /v1/reports/evaluation` (computed live) | Trust Centre → AI evaluation, Red team, Drills and comparison |
| Load test | `python backend/scripts/load_test.py` against a running server ([LOAD-TEST.md](LOAD-TEST.md)) | Trust Centre → Release tests (bottom) |
| Browser rehearsals | `python e2e/tour.py`, `e2e/offline_phone.py`, `e2e/drill.py`; with a key, `e2e/ai_live.py` ([e2e/README.md](../e2e/README.md)) | printed, with screenshots |
| Observed drills | the drill console and [DRILL-PROTOCOL.md](DRILL-PROTOCOL.md) (people, real time) | Trust Centre → Drills and comparison, once published |

## Release tests

`backend/tests/` holds 439 server tests in 10 suites; `frontend/src/**/*.test.ts` holds 138 device tests
(577 in all). Together they cover **all 97 acceptance cases** of Appendix D of the specification. Each test names the
cases it checks with a marker, for example `@pytest.mark.tcase("T27")`, and the report lists, per case, its
English and Arabic text, the expected outcome and the tests behind it (`backend/app/data/acceptance_cases.json`).

| Suite | Covers |
|---|---|
| `test_policy.py` | The policy engine: emergency precedence, bands, midday window in site time, freshness, unknown workload, conflicting sources, signed packs, review dates, plus the 49-case conformance suite |
| `test_worker.py` | Check-ins, emergency path and its honest states (received is not acknowledged), offline outbox and clock checks, Speak (English, Arabic, code-switching), the shared offline lexicon, Ask, fluid plans, kiosk privacy |
| `test_ledger.py` | Evidence tiers, disputes without retaliation signals, disputes only on one's own tasks, independent dispute resolution with a fresh check, escalation, unreachable owners, retried actions answered once, report validation |
| `test_privacy.py` | Clinical boundary, the AI trace scoped on the server (staff never read a worker's words), bulk export, small cells and complementary suppression, anti-differencing, consent, exports and the passport |
| `test_ai.py` | The frozen gate, Speak and copilot sets; red-team drafts; timeouts; governance; the policy compiler; document AI and care summaries; the model adapter's handling of the real free tier (scripted HTTP, no network) |
| `test_planner.py` | Forecast unavailable or stale, live-over-forecast, wrong units, out-of-experience inputs, CP-SAT plans, fault injection, re-validation, fairness, the forecast's information cutoff and separate fit, calibration and test periods |
| `test_clinical.py` | Lab import, referrals, clinic capacity enforced at booking (two urgent referrals never share a slot), nurse hydration checks, restrictions, clinician-written summaries |
| `test_watch_agents.py` | Aggregate signals, the individual-output guard, detector evaluation, bounded agents |
| `test_drill.py` | Observed drills: counterbalanced plan, sealed false reports, real-time clock, ledger-derived and observer moments, the fixer cannot be their own independent check, tamper-checked export and publication; the scripted workflow checks, and that they fail when a rule is broken |
| `test_api.py` | Tokens, the permission matrix, problem details, security headers, rate limits, no model names in any response |

Rules the suite follows:

* **No network and no model calls.** The AI key is cleared before the app loads. Where a model step matters,
  a scripted stand-in returns the kind of draft a model might produce (including unsafe ones), so the
  deterministic gate is tested against realistic failures. Live model behaviour is measured separately.
* **Expected outcomes come from the specification**, never from running the code under test.
* **English and Arabic only.** Cases that used another language in the specification were adapted to Arabic;
  the report says which.
* **Honest scope.** Two cases test modules that are not built (a camera pulse research module; model
  training). Their tests prove the safety rule holds anyway: physiological fields cannot change
  acclimatization, and real data cannot be sent to a free-tier model.

## Findings the tests produced

Writing the suite found and fixed real defects, each now a regression test:

* The planner treated indoor work as unaffected by a zone's withdrawal band; independent re-validation
  rejected one replayed day's plan (15 August). The solver now applies the band to all work in the zone.
* Re-validation ignored clinician restriction labels stored with their dates; it now reads the label, and
  the planner schedules restricted workers individually.
* A Watch evaluation counted only the first alarm per series; the detector now restarts after each alarm,
  as in use, and is reported on a held-out seed.
* A provider timeout could try a second model; it now ends the attempt so the template follows within 2 s.
* Arabic «تشنجات» alone could mean a seizure; it is treated as urgent, while «تشنجات عضلية» or «شد عضلي» is
  recorded as cramps, and the emergency card uses the unambiguous wording.
* Consent events were compared as text; they are now compared as instants, with withdrawal winning ties.

A second review (November 2026) reproduced and fixed more, each now a regression test or a rehearsal:

* A supervisor could read the exact words a worker sent to Ask through the AI trace. The trace is now scoped on
  the server: each person sees their own runs; the independent reviewer sees de-identified runs, and that access
  is audited.
* A worker could dispute a task that did not concern them; a dispute stayed open even after an independent check,
  so verification was impossible. Disputes are now limited to the worker's own tasks, and only someone outside the
  supervisor's line can resolve one, with their own check made after it; the worker is told and can challenge again.
* An emergency alert received by the server was shown as delivered to the site team. The phone now separates
  "saved on this phone", "received by the server" (a real receipt) and "seen by the site team" (a responder's
  acknowledgement, with role and time), and the alert stays visible after closing the card or reloading.
* A help request typed offline was rejected at sync. It is now accepted.
* Two urgent referrals could be booked into one remaining clinic slot. Capacity is now enforced at booking.
* The forecast backtest used readings after the 18:00 issue time and fitted and evaluated on the same days. It
  now respects the cutoff and uses separate fit, calibration and test periods (coverage 89.1% held out).
* Queued reports waited until the next manual action after a real loss of network. They now send by themselves
  when the network returns, on reload, and every 10 seconds while anything waits, each as the persona that made it.
* Switching persona let the previous screen refetch with the new persona's permissions (harmless 403s). The
  previous screen now unmounts first; the tour runs with no failed call except the intended denial.
* A retried task action (a dropped connection) could be done twice. Task actions, disputes and confirmations now
  carry an idempotency key and are answered once.

Preparing the README screenshots (9 November 2026) found two small display defects, both fixed:

* The AI trace showed two newer Guardian checks by their internal codes (`rule.plain_language`,
  `rule.forbidden_claim.certainty`). They now have plain English and Arabic labels, and
  `test_people_never_read_internal_codes` also fails if any Guardian check lacks a label in either language.
* An HSE finding typed without a full stop ran into the next sentence ("refilled and cold The worker can still
  challenge this"). The finding now always ends as its own sentence.

## Live tests with a real key (21 October and 8 November 2026)

Every AI feature was also run end to end against the live Gemini free tier, in English and Arabic: Speak from
typed text and from voice clips (webm, mp4; English, Arabic and mixed speech), Ask (including kidney, medicine,
secrecy, prompt-injection and off-topic questions, and red-team mode), the copilot (gold and forbidden
questions), worker and plan explanations, the policy compiler, document AI on all three lab reports, care
summaries, read-aloud speech and the live evaluation. No response contained a model name. The run found ten
problems that scripted tests could not (models that refuse new users or take 13–90 s, thinking that used up the
output budget, double-wrapped WAV audio, mixed embedding models, a lab unit read as a dose, internal codes in a
worker's explanation, an Arabic copilot question dropped as "out of scope", Gemma skipped for images, an Arabic
kidney-risk sentence that only numeric grounding caught, and a less precise privacy refusal with AI on). Each is
fixed and now has an offline regression test; the details and measured latencies are in
[AI-MODELS.md](AI-MODELS.md) §1 and §3. The worker's "read aloud" feature from the specification (§7.5) was
added during this pass and checked in a real browser with AI on and off.

A second key was used on 8 November 2026 to run everything again: a paced benchmark of every capability
(`backend/scripts/live_benchmark.py`; 200 live requests over two runs) and a browser rehearsal of every AI feature
in English and Arabic (`e2e/ai_live.py`, with a fake microphone playing a sentence the server reads aloud), run
against the same container image Cloud Run builds; the guided tour, the phone losing its network and the drill
console were also rehearsed against that image with AI on. Nine problems were found and fixed, each with a
regression test: an overconfident red-team draft that passed the Guardian, an Arabic answer that leaked a word from
the model's instructions, answers in the interface language instead of the question's, a copilot refusal the model
should not make, a plan explanation that the Guardian always blocked, report items the model dropped, emergency
words the offline matcher missed, daily-quota handling after a restart, and the microphone button hidden under the
sticky header. A forecast test that failed after 15:00 Gulf time was also fixed. Details, before-and-after
figures and an honest reading of them: [AI-MODELS.md](AI-MODELS.md) §3; raw results:
[evidence/live-ai-2026-11-08.json](evidence/live-ai-2026-11-08.json).

## AI evaluation (computed live)

`GET /v1/reports/evaluation` recomputes, in about two seconds (the live sample, `POST /v1/reports/evaluation/ai`,
adds a balanced English and Arabic run against the configured key):

* **Conformance:** 49 policy cases on the server engine (the browser engine is compared in Decision replay).
* **Speak:** the frozen English and Arabic set (offline matcher; the live model when configured).
* **Guardian gate:** 30 frozen drafts, unsafe and safe, in both languages.
* **Copilot:** 15 gold questions and 15 forbidden ones.
* **Compile:** quote match and agreement with an independent transcription of the demonstration excerpt.
* **Foresee:** a backtest on held-out days of the 2025 season (interval coverage, error against climatology
  and persistence, harsh-hour underestimation).
* **Plan:** 8 replayed days (12–19 August 2025); every proposed plan re-validated independently. Days with
  no protected plan are re-solved only with a permitted remedy (deferring work), never by relaxing a rule.
  On each directly solved day, 3 injected faults (midday work, work in a withdrawal band, an over-full rest
  area) must all be rejected.
* **Watch:** detection delay and false alerts on synthetic series, on a held-out seed. A sudden supply failure is
  caught within 2 days in 93% of cases (0.18 false alerts per site-month). A slow fourfold rise from a low
  baseline is caught within 2 days in only 33% and within 7 days in 72%: in 21% of cases no event at all happens
  in the first 2 days, so no detector that waits for evidence can do better than 79%. Reported as it is.
* **Red team:** 45 generated attacks across the gate, Speak, the copilot and the agents.
* **What each workflow does:** 7 scripted situations through the real ledger, evidence rules, emergency states and
  plan re-validation, beside a description of the alert-only comparator. Behaviour only; no speed is claimed.

Recorded-speech and noisy-audio test sets need consenting speakers and are part of the pilot plan.
