# Bardan (بَرْدًا) · one-page summary

**Heat protection that gets done. Kidney care that stays with the worker.** Future Health Digital Innovation
Challenge 2026, Challenge 07. Individual entry by Nipun Dilshan Senevirathne. Working prototype, **synthetic data
only**, English and Arabic. Bardan plans heat-safe work the evening before, turns the heat rules into tasks that
are assigned, evidenced, escalated and independently checked, lets workers say "this didn't happen" safely, and
keeps kidney care private and continuous. In the **Scenario Lab** anyone can enter sample workers, weather and
tasks, watch the plan, the breaks and every phone respond, and play the shift as conditions change.

| Implemented and tested | Simulated or mocked (labelled in the app) | Planned, not built |
|---|---|---|
| Zone heat forecast (Liljegren WBGT) and a CP-SAT plan that respects shade seats, acclimatization and the midday break; every plan re-validated by the rule engine and approved by a named person | The site, its 40 workers, the zone instruments (derived from replayed 2025 weather), lab results and history | Qualified review of the heat rules (review sheet ready) and an occupational clinician's review (form ready) |
| Live readings govern: a harsher reading tightens the plan; a stale one is "not confirmed safe" | The demonstration day's forecast error | Comprehension testing in English and Arabic (protocol ready) |
| Protection tasks with start-by times, escalation, evidence tiers, worker disputes the supervisor cannot trace, and resolution only by an independent check made after the dispute | The emergency dialler and every outgoing message (mock) | Observed drills with real people (console and protocol ready; none published yet) |
| Worker app: voice or typed reports with the heard words shown back, private check-ins, Ask behind a safety gate, an emergency card that works with AI and network off | Heat rules: demo encodings until reviewed | Pilot hosting inside the UAE, PostgreSQL with a separate clinical database, DoH ADHICS application |
| Offline: reports and alerts wait on the phone, survive a reload and send themselves when the network returns; "received by the server" and "seen by the site team" are separate | AI on a free tier with synthetic data only; everything works with AI off | Push notifications or SMS; HR, lab and health-information-exchange integrations |
| Clinical workspace: lab import checks, document AI with source highlights, referrals with clinic capacity enforced at booking; the employer sees only "clinic visit 14:00-16:00" | | Recorded-speech test sets, the camera pulse research module, model training |
| Trust Centre: AI trace (scoped per person), evaluation and red team, decision replay on two engines, workflow checks, drill results, release tests, load test | | A licensed clinical partner, a pilot site and worker representatives |
| Scenario Lab and shift simulator: your own workers, weather and tasks; breaks sized to the ISO 7243 / NIOSH limit for each job; mid-shift changes re-planned from that minute; every plan re-checked. Optional wearable, off by default: processed on the phone, it can only add rest, and the supervisor gets "needs a break" only by the worker's choice, never a number | The wearable's heart rate (a labelled generator on the phone) | A real wearable integration, and a field check of the estimate on the pilot's workers |

**Measured, as it is**

* **639 automated tests** (486 server, 153 device), all passing, covering all **97 acceptance cases** of the
  specification. Browser rehearsals of the guided tour, a lost network, a drill and the Scenario Lab with the
  wearable pass with no unexpected failed call.
* **Forecast, held out:** 90% interval coverage **89.1%** on 2,340 zone-hours; mean error **0.76 °C** against
  0.84 °C for persistence (fitted, calibrated and tested on separate periods; replayed weather).
* **Scenario Lab:** across **1,722** random half-hour steps on 120 random days, every plan shown passed the
  independent re-check; when no protected plan exists it says so and names the permitted options.
* **Live AI (free tier, 8 Nov 2026):** every AI feature ran in English and Arabic; 100% critical recall and 0 false
  reassurance over 44 reports; red-team drafts blocked 10/10 after one fix. **What each workflow does:** 7 of 7
  scripted situations behave as designed in the real code (behaviour, not speed).
* **Load, one CPU core:** 270 requests a second for 50 judges (95th percentile under 45 ms); 100 arriving at once,
  0 errors. **Watch:** 93% of sudden supply failures caught within 2 days; slow rises often cannot be, and this is shown.

**Not yet, said plainly:** no observed drill, no qualified review of the heat rules or the break limits, and no
clinical partner, customer, approval or pilot; `docs/PILOT-KIT.md` sets out the market, UAE hosting, the
health-data law and the review forms.
