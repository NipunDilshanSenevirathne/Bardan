# Pilot kit: market, hosting, outreach and reviews

Everything a first pilot conversation needs, with sources. Figures marked **(source)** are published numbers;
everything else is a hypothesis to test, and is labelled so. Nothing here is a quote, a forecast or a sale.

Contents: [1 Market](#1-market) · [2 Pricing hypothesis and questions](#2-pricing-hypothesis-and-questions) ·
[3 Hosting and health-data law](#3-hosting-and-health-data-law) · [4 Outreach email](#4-outreach-email) ·
[5 Letter of interest template](#5-letter-of-interest-template) · [6 Safety lead review form](#6-safety-lead-review-form) ·
[7 Occupational clinician review form](#7-occupational-clinician-review-form) ·
[8 Comprehension test protocol](#8-comprehension-test-protocol)

---

## 1. Market

**Who pays.** Employers with outdoor workers and a legal duty to control heat: construction contractors first,
then utilities, oil and gas, logistics yards and facilities management. Workers never pay.

**Published numbers**

| Figure | Value | Source |
|---|---|---|
| Construction workers registered with MoHRE, UAE private sector (end of 2022; free zones excluded) | **1,386,498** of 5,477,366 private-sector workers | MoHRE Labour Market Information System, compiled by [GLMM](https://gulfmigration.grc.net/uae-total-labour-force-in-the-private-sector-by-economic-activity-2017-2022/) |
| Construction workers registered with MoHRE, Abu Dhabi (end of 2019, the latest split by emirate in that series) | **420,654** of 1,381,819 | MoHRE LMIS via [GLMM](https://gulfmigration.grc.net/uae-total-labour-force-in-the-private-sector-by-economic-activity-and-emirate-2019/?print=pdf) |
| Abu Dhabi workforce, end of 2024 | 2.76 million (+9.1% in a year); population 4,135,985 | SCAD, reported by [The National](https://www.thenationalnews.com/news/uae/2025/07/03/abu-dhabi-population-four-million) (3 Jul 2025) |
| UAE workforce growth | +10.9% in 2024, +12.4% in 2025 | MoHRE, reported by [Gulf News](https://gulfnews.com/uae/government/uae-workforce-jumps-124-in-2025-as-new-firms-surge-mohre-says-1.500416665) (Jan 2026) |
| Midday break | 12:30 to 15:00, 15 June to 15 September; AED 5,000 per worker, up to AED 50,000; file suspension, downgrading, referral to prosecution if workers are hurt; employers must provide shaded rest areas sized for the workforce, cold water, electrolytes, cooling and first aid | MoHRE 2026 rules, reported by [Khaleej Times](https://www.khaleejtimes.com/uae/midday-break-violators-dh50000-fine-suspension-legal-action) (6 Jul 2026) |

The construction figures are older than the workforce totals and leave out free zones. They have not been
grown forward here: the workforce has grown since, so they understate today's market.

**Sizing (hypothesis price, heat season only)**

The price used here is the planning input from finalsystem.md §33.4, **AED 12 per active worker per month**,
charged for a six-month heat season (AED 72 per worker per year). It is a hypothesis to test in the interviews
below, not a price. AED is pegged at 3.6725 to the US dollar.

| Layer | Workers | Annual value at the hypothesis price |
|---|---:|---:|
| UAE construction (MoHRE-registered, 2022) | 1,386,498 | AED 99.8 million (about US$27.2 million) |
| Abu Dhabi construction (MoHRE-registered, 2019) | 420,654 | AED 30.3 million (about US$8.2 million) |
| Beachhead by the third season (illustration: 10 sites of 500 workers, plus AED 2,000 a month per site in season) | 5,000 | AED 480,000 (about US$131,000) |

A year-round price would double the first two rows. Other outdoor sectors, other emirates' free zones and the
other GCC states (which have their own summer midday rules) are left out; they are the expansion path, not the
business case.

**For scale, not as a promise:** one maximum midday-break fine (AED 50,000) equals the season fee for about 690
workers at the hypothesis price. Bardan does not replace the midday break, and it does not prevent fines by
itself; it turns the heat duties into tasks with evidence, so gaps are found and fixed while they are small.

## 2. Pricing hypothesis and questions

**Hypothesis.** A site licence plus a fee per active worker during the heat season, with clinical integration
priced separately with the clinical partner. Government or programme licences can sponsor small contractors.
Never: selling data, rankings or risk scores (finalsystem.md §33.3).

**Questions for HSE managers and project directors** (record answers word for word; an interview is not a sale)

1. Today, how many supervisor and HSE hours a day go into heat controls: water, shade, rest, checks, records?
2. What did heat controls cost last season (water, electrolytes, shade, cooling, medical cover, any wearables)?
3. Who holds the budget and signs: HSE, the project director, procurement, the main client?
4. Would you pay per site, per active worker, or per season? Why?
5. Price sensitivity, per worker per month:
   * At what price would it be so expensive that you would not consider it?
   * At what price would it be expensive, but you would still consider it?
   * At what price would it be good value?
   * At what price would it be so cheap that you would doubt it works?
6. Would you pay a fixed fee for a defined eight-week pilot? What evidence at the end would make you renew?
7. What would stop you: phone rules on site, data protection review, worker representatives, union or client
   requirements, DoH requirements for the clinical part?

## 3. Hosting and health-data law

**Prototype (now).** Google Cloud Run, one instance, synthetic data only, no personal data and no health data.
Google Cloud has no operational region in the UAE at the time of writing (its nearest regions are Doha and
Dammam; a UAE region was reported as in build-out in 2026 by
[PDP Spectra](https://pdpspectra.com/blog/uae-cloud-aws-azure-g42-2026)). That is acceptable for a synthetic
prototype and not for a pilot with real workers.

**Pilot (real people).** The same container moves to a region inside the UAE, with managed PostgreSQL for
operations and a separate PostgreSQL instance with its own keys for clinical data (finalsystem.md §19, §28).

| Option in the UAE | Notes |
|---|---|
| Microsoft Azure UAE North (Dubai) | General region since 2019. UAE Central (Abu Dhabi) is access-restricted, reserved for UAE North customers who need in-country disaster recovery ([Azure restricted regions](https://www.azurespeed.com/Information/AzureRestrictedRegions)) |
| AWS Middle East (UAE), `me-central-1` | Opened in 2022 ([AWS](https://aws.amazon.com/cn/blogs/china/now-open-aws-region-in-the-united-arab-emirates-uae/)) |
| Oracle Cloud Dubai and Abu Dhabi | Dubai opened in 2020; Abu Dhabi is Oracle's second UAE region ([Oracle](https://www.oracle.com/ae/cloud/cloud-regions/abu-dhabi/)) |
| G42 / Microsoft sovereign arrangements | For the most sensitive workloads; scope with the provider |

Check, service by service, that compute, the database, key management, backups, logs, support access and any
AI model used in the pilot all stay in the country. A resource labelled "UAE" is not enough on its own.

**Health data rules to meet** (to be confirmed with counsel and the clinical partner; not legal advice)

* **Federal Law No. 2 of 2019** (ICT in health fields), **Article 13**: health data relating to health services
  provided in the UAE may not be stored, processed, generated or transferred outside the country, except as
  allowed ([Baker McKenzie](https://resourcehub.bakermckenzie.com/en/resources/uae-health-data-law---permitted-transfers-of-health-data)).
* **Ministerial Resolution No. 51 of 2021** lists the permitted exceptions (for example treatment abroad with
  consent, or anonymised research approved by the emirate's health authority), each with conditions
  ([CMS](https://cms.law/en/are/legal-updates/uae-health-data-new-data-transfer-permissions), 22 Jun 2021).
* **Abu Dhabi DoH, ADHICS version 2.0 (2024)** recognises cloud storage and processing of health data inside the
  UAE. In May 2025 DoH said no exemption is needed to store and process health data in a UAE cloud, but the
  entity should apply to DoH for it (by email to the AAMEN team, using DoH's template); exemptions for
  processing abroad last up to a year and require a localisation plan
  ([U.S.-U.A.E. Business Council](https://usuaebusiness.org/?p=35610), a summary of a DoH webinar; check the
  official texts).
* Personal data that is not health data falls under the federal personal data protection law (Federal
  Decree-Law No. 45 of 2021); confirm with counsel which parts of Bardan's operational data it covers.

Bardan already keeps the two kinds of data apart: operational records (tasks, evidence, plans) carry no
clinical content, and the clinical record sits behind its own permissions and audit (Trust Centre, privacy tests).

## 4. Outreach email

Personalise every bracket. Send from your own address. Do not suggest that the challenge organisers or any
authority endorse Bardan.

> **Subject:** 20 minutes on heat protection at [site or company]: a prototype to try, nothing to buy
>
> Dear [name],
>
> I am Nipun Dilshan Senevirathne, an individual entrant in the Future Health Digital Innovation Challenge 2026
> (climate-resilient worker health). I have built a working prototype called Bardan that turns a site's heat
> rules into daily tasks with evidence: water, shade, rest and checks are assigned, timed, escalated when
> missed, and confirmed by someone other than the person who fixed them. Workers can report a problem by
> voice in English or Arabic, and their health check-ins stay private from the employer.
>
> The prototype runs on synthetic data only. I would value 20 minutes of your time to:
>
> 1. walk you through it (a link you can open on your phone), and
> 2. hear where it would or would not fit how your sites work today.
>
> If it looks useful, a short role-play drill (about an hour, no heat exposure, no personal data) would let us
> compare your current way of handling a water or shade failure with Bardan, and a non-binding letter of
> interest would help my submission. Neither is expected.
>
> Would [two time options] suit you?
>
> Kind regards,
> Nipun Dilshan Senevirathne
> [phone] · [email] · [link to the prototype]

**Follow-up (after a week, once):**

> Dear [name], a short follow-up on my note about heat protection at [site]. If a call is not possible, I would be
> grateful for a one-line reply on whether heat controls on your sites are tracked today, and by whom. Thank you.

## 5. Letter of interest template

To be written by the organisation on its own letterhead, in its own words if it prefers. It must be true, signed
by someone entitled to sign, and it must not be presented as more than it is.

> [Organisation letterhead]
>
> [Date]
>
> **Letter of interest: Bardan heat-protection prototype**
>
> [Organisation] has reviewed a demonstration of Bardan, a prototype developed by Nipun Dilshan Senevirathne for
> managing heat protection tasks and evidence on outdoor work sites.
>
> We are interested in discussing a pilot at [site or business unit], involving about [number] workers during
> the [year] heat season, subject to: a data protection review; the requirements of the relevant authorities,
> including the Abu Dhabi Department of Health for any clinical component; consultation with worker
> representatives; hosting inside the UAE; and agreed terms.
>
> This letter expresses interest only. It is not an order, a commitment to purchase or an endorsement, and it
> creates no legal obligation for either party.
>
> [Name], [Role]
> [Signature]
> [Contact details]

## 6. Safety lead review form

For a qualified HSE professional, after a walk-through of the app and the rule review sheet (docs/RULE-REVIEW.md).
About 60 minutes. One form per reviewer.

**Reviewer:** role, qualification, years in heat-exposed work, any conflict of interest, date.

Rate each step: **Safe as it is** / **Needs a change** (say what) / **Unsafe** (say why).

| # | Step | Rating | Comment |
|---|---|---|---|
| 1 | Evening-before plan: forecast, draft plan, optimised plan, capacity check, approval by a named person | | |
| 2 | Live readings take over from the forecast when they are harsher; a stale reading is "not confirmed safe" | | |
| 3 | Worker reports (water, shade, cooling, feeling unwell) by voice or tap, in English or Arabic, also offline | | |
| 4 | Tasks have start-by times, escalate to the HSE lead when missed, and stay "queued" if the owner cannot be reached | | |
| 5 | Evidence tiers: a supervisor's word alone cannot close a mandatory control; photos must be current and in place | | |
| 6 | Workers can dispute a completion; only someone outside the supervisor's line can resolve it, after a fresh check | | |
| 7 | Emergency card: stop work, call 998, move to shade, cool; "dialler opened" is not "help called"; received is not acknowledged | | |
| 8 | Acclimatization and new-worker rules, midday break, withdrawal zone controls (see the rule sheet) | | |
| 9 | What a supervisor sees about a worker (no health details) and what only clinical staff see | | |
| 10 | Anything missing that your site would need on day one | | |

**Overall:** Ready for a supervised pilot / Ready after the changes listed / Not ready. Signature and date.

## 7. Occupational clinician review form

For an occupational physician or nurse licensed in the UAE. About 60 minutes. Covers clinical safety, not
software quality.

**Reviewer:** role, licence (authority and number, kept off any public document), conflict of interest, date.

| # | Item | Rating | Comment |
|---|---|---|---|
| 1 | Emergency card wording, English and Arabic: the red flags, the order of actions, cooling first, never wait for a test | | |
| 2 | Symptom check-in questions and the escalation thresholds behind them (Appendix F of finalsystem.md) | | |
| 3 | Urine specific gravity handling and the hold-and-retest rule (rule sheet row 9) | | |
| 4 | Clinic referral urgency (urgent same day; soon today or next day) and what happens when no slot is free | | |
| 5 | Kidney-care continuity messages: what the worker is told, in what words, and what is never said | | |
| 6 | The AI's limits: no diagnosis, no reassurance about symptoms, the frozen red-team answers in the Trust Centre | | |
| 7 | Privacy: the employer sees only a time window for a clinic visit, never the reason or results | | |
| 8 | Hazard log (finalsystem.md §27): the top hazards and whether the mitigations are enough | | |
| 9 | What a clinical partner would need before any real patient data is used | | |

**Overall:** Clinically acceptable for a supervised pilot / Acceptable after the changes listed / Not acceptable.
Signature and date.

## 8. Comprehension test protocol

**Why.** A safety message that is read but misunderstood is a hazard. Each critical message must be understood
by the people it is for, in the language they will use, before the pilot.

**Messages to test** (English and Arabic, the languages in the app):

1. The emergency card: what to do, in order.
2. "Stop heat work until water is restored."
3. The report confirmation: "This is what Bardan heard. Is it right?"
4. "This didn't happen": what pressing it does, and that the supervisor will not see who pressed it.
5. The private check-in promise: who sees the answers and who does not.
6. "Dialler opened" versus "help called", and "received by the server" versus "seen by the site team".

**People.** Adult volunteers who agreed to take part, at least 20 per language per round, including people for
whom the language is a second language and people who are not comfortable reading. No names are recorded;
note only the language, whether it is the person's first language, and a self-rated reading comfort (1 to 5).

**Method.** Show one screen (or play the audio) at a time, without hints. Ask: "In your own words, what does this
mean?" and "What would you do now?" (the teach-back method, as in
[AHRQ's teach-back tool](https://www.ahrq.gov/teamstepps-program/curriculum/communication/tools/teachback.html)).
Record the answer word for word. The test design follows the comprehension-testing method of ISO 9186-1.

**Scoring.** Two people score every answer separately as **correct**, **partly correct**, **wrong** or
**critical confusion** (an answer that would lead to an unsafe action, for example waiting for a test before
cooling someone). Report their agreement, then settle differences together.

**Threshold.** A message passes when at least **85%** of answers are correct and no more than **5%** are critical
confusions, the criterion used for safety symbols in ANSI Z535.3 (see the
[symbol comprehension testing protocol](https://www.iiid.net/wp-content/uploads/Symbol-Comprehension-Testing-Protocol.pdf)).
A message that fails is rewritten and tested again with new people. Text stays "Draft" or "Reviewed" in the app's
language register until it passes (finalsystem.md §26.2).

**Report.** Per message and language: number of people, percentage correct, percentage of critical confusions,
the most common misunderstanding, and what was changed.
