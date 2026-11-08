# Bardan (بَرْدًا) · one-page summary

**Heat protection that gets done. Kidney care that stays with the worker.** Future Health Digital Innovation
Challenge 2026, Challenge 07. Individual entry by Nipun Dilshan Senevirathne. Working prototype, **synthetic data
only**, English and Arabic. Bardan plans heat-safe work the evening before, turns the heat rules into tasks that
are assigned, evidenced, escalated and independently checked, lets workers say "this didn't happen" safely, and
keeps kidney care private and continuous.

| Implemented and tested | Simulated or mocked (labelled in the app) | Planned, not built |
|---|---|---|
| Zone heat forecast (Liljegren WBGT) and a CP-SAT plan that respects shade seats, acclimatization and the midday break; every plan re-validated by the rule engine and approved by a named person | The site, its 40 workers, the zone instruments (derived from replayed 2025 weather), lab results and history | Qualified review of the heat rules (review sheet ready) and an occupational clinician's review (form ready) |
| Live readings govern: a harsher reading tightens the plan; a stale one is "not confirmed safe" | The demonstration day's forecast error | Comprehension testing in English and Arabic (protocol ready) |
| Protection tasks with start-by times, escalation, evidence tiers, worker disputes the supervisor cannot trace, and resolution only by an independent check made after the dispute | The emergency dialler and every outgoing message (mock) | Observed drills with real people (console and protocol ready; none published yet) |
| Worker app: voice or typed reports with the heard words shown back, private check-ins, Ask behind a safety gate, an emergency card that works with AI and network off | Heat rules: demo encodings until reviewed | Pilot hosting inside the UAE, PostgreSQL with a separate clinical database, DoH ADHICS application |
| Offline: reports and alerts wait on the phone, survive a reload and send themselves when the network returns; "received by the server" and "seen by the site team" are separate | AI on a free tier with synthetic data only; everything works with AI off | Push notifications or SMS; HR, lab and health-information-exchange integrations |
| Clinical workspace: lab import checks, document AI with source highlights, referrals with clinic capacity enforced at booking; the employer sees only "clinic visit 14:00-16:00" | | Recorded-speech test sets, the camera pulse research module, model training |
| Trust Centre: AI trace (scoped per person), evaluation and red team, decision replay on two engines, workflow checks, drill results, release tests, load test | | A licensed clinical partner, a pilot site and worker representatives |

**Measured, as it is**

* **577 automated tests** (439 server, 138 device), all passing, covering all **97 acceptance cases** of the
  specification. Browser rehearsals of the full guided tour and of a phone losing its network pass with no
  unexpected failed call.
* **Forecast, held out:** fitted, calibrated and tested on separate periods, with only data available at the 18:00
  issue time: 90% interval coverage **89.1%** on 2,340 zone-hours; mean error **0.76 °C** against 0.84 °C for
  persistence; 1.5% of harsh hours underestimated. Replayed weather, not site instruments.
* **What each workflow does:** 7 of 7 scripted situations behave as designed when run through the real code. They
  show behaviour, not speed; no simulated percentage is claimed.
* **Live AI (free tier, 8 Nov 2026):** every AI feature ran in English and Arabic in a browser against the hosting
  container; 100% critical recall, 0 false reassurance over 44 reports; red-team drafts blocked 10/10 after one fix.
* **Load, one CPU core:** 50 judges clicking for a minute at 270 requests a second (95th percentile under 45 ms);
  100 judges arriving in the same second all finished, 0 errors.
* **Watch:** a sudden supply failure is caught within 2 days in 93% of synthetic cases (0.18 false alerts per site
  per month); a slow rise from a low baseline often cannot be, because no event has happened yet; this is shown.

**Not yet, said plainly:** no drill has been observed, no qualified person has reviewed the heat rules, and there
is no clinical partner, customer, approval or pilot. The pilot kit (`docs/PILOT-KIT.md`) sizes the market from
published figures (about 1.39 million MoHRE-registered construction workers in the UAE in 2022, 0.42 million in Abu
Dhabi in 2019) and sets out UAE hosting, the health-data law, outreach and the review forms.
