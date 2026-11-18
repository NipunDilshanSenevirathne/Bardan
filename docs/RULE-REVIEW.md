# Heat rules review sheet (pending qualified review)

**Status:** demonstration rules, not yet reviewed by a qualified person. The app labels them "Demo heat rules"
on every staff screen, and the pack (`shared/packs/AE-AD-HEAT.json`, version `0.1.1-demo`) carries
`review.state = pending_qualified_review`.

**Rows 16–21** (added 17 November 2026) cover the Scenario Lab's break planner and the optional wearable; they are
published reference values, not Abu Dhabi rules, and they can only add protection to the rows above.

**Compared on:** 8 November 2026, against the
[ADOSH-SF Technical Guideline "Safety in the Heat", Version 4.0, 15 July 2024](https://www.adphc.gov.ae/-/media/Project/ADPHC/ADPHC/PDF/OSHAD-SF/Technical-Guidelines/Safety-in-the-Heat--Eng.pdf)
(the guideline says regulatory requirements prevail where they differ, §1(a)) and the federal midday-break rule.
The guideline's Table 1 (TWL zones and interventions) is published as an image, so its values could not be read
as text; the TWL numbers below were cross-checked against the health authority's public description
([The National](https://www.thenationalnews.com/uae/what-is-the-thermal-work-limit-1.394827)).

**Before any real use** two qualified people (for example a site HSE professional and an occupational physician)
transcribe Table 1, confirm or correct every row, and sign below. The policy compiler and the two-person approval
in the app are the route for that.

| # | Rule | Encoded in Bardan | Guideline V4.0 | Status |
|---|---|---|---|---|
| 1 | Heat index | TWL in W/m² for live readings; WBGT bands only for forecasting | TWL (§2.1) | Matches for live readings. WBGT forecast bands are a planning addition, not in the guideline |
| 2 | TWL zones | Unrestricted > 220; acclimatization 140–220; buffer 115–140; withdrawal < 115 W/m² | Table 1 (image) | Matches the public description; **transcribe Table 1** |
| 3 | Buffer-zone controls | Shade and ventilation, no lone work, extra rest, assured fluids; workers in their first days moved off heat work | Public description: shade and ventilation, no outdoor lone work, unacclimatized workers off the job, frequent rest, fluids | Matches |
| 4 | Acclimatization-zone controls | Extra breaks and assured fluids for everyone | Acclimatized: no restriction; unacclimatized: not alone | Bardan is stricter; **reviewer to decide** |
| 5 | Withdrawal-zone controls | Essential work only (an authorised exemption is required), no lone work, 40 min rest per hour, fluids | Maintenance and rescue only, specific authorisation, 20 min work per 40 min rest, 600 mL water every 30 min, dehydration testing at the end of the shift | Rest ratio matches. **Gap:** the 600 mL per 30 min and the end-of-shift test are not yet encoded |
| 6 | Acclimatization schedule | New workers 20, 40, 60, 80, 100 %; experienced 50, 60, 80, 100, 100 % over days 1–5 | §3, same values | Exact match |
| 7 | Re-acclimatization after absence | All returning workers follow the experienced schedule | Table by days away or ill (for example more than 20 days: 50, 60, 80, 100 %) | Bardan is stricter for short absences. **Gap:** absence length is not modelled |
| 8 | Drinking water | "Before work and at frequent intervals; about 4–6 litres a day in the Gulf summer; a cup every 15–20 minutes in very hot work; not more than about 1.4 litres an hour" | §5.2: before work and at frequent intervals; 4–6 L a day (2 L every 2–3 hours) | Consistent. The per-cup and hourly-limit advice is NIOSH background, labelled as such |
| 9 | Urine specific gravity (nurse test) | ≤ 1.015 at the start of shift, ≤ 1.029 at other times; 1.016–1.020 slight, 1.021–1.029 moderate, ≥ 1.030 significant (remove from hot work, recheck in 4 h); a failed test holds the work station and retests after 1 h | Appendix 4, same values and actions | Exact match |
| 10 | Heat illness response | Emergency card: stop work, call 998, stay, move to shade or a cool place and start cooling, no drinks if the person cannot swallow safely, never wait for a test | §4.5: call the emergency number, notify the supervisor, move to a cool shaded area and cool | Matches |
| 11 | First aid | Named first aiders on the site map; drills in the pilot | Appendix 6: certified first aider, kit, response within 3 minutes, heat drills | Response time not yet measured (pilot drill kit) |
| 12 | Midday break | 12:30–15:00, 15 June–15 September (federal pack AE-FED-MIDDAY) | Appendix 6 asks for compliance with the federal midday break | Matches |
| 13 | Reading freshness | A measured reading older than 30 minutes is stale ("not confirmed safe") | Measurement method given (§2.2); no frequency stated | Demonstration value; **reviewer to set** |
| 14 | Rest minutes per hour | Acclimatization 10, buffer 15, withdrawal 40 | Table 1 (image) | Withdrawal matches the 20/40 cycle; the others are demonstration values |
| 15 | WBGT planning bands | 28 / 31 / 33 °C | Not in the guideline | Demonstration only |
| 16 | One-hour WBGT limit by work rate (break planner, Scenario Lab) | 56.7 − 11.5·log₁₀M for acclimatized workers, 59.9 − 14.1·log₁₀M for others, as one-hour averages | Not in the guideline (it uses TWL). Source: ISO 7243:2017, NIOSH 2016 REL and RAL, ACGIH TLV and Action Limit | Reference method used alongside the bands; it can only add rest. **Reviewer to confirm** its use next to TWL |
| 17 | Work rates | Rest 115, light 180, moderate 300, heavy 415, walking 300 W (70 kg worker); very heavy work is not offered | ACGIH / OSHA Technical Manual III:4, Table 3 | Published values. **Reviewer to confirm** the task classes for the site |
| 18 | Clothing adjustment | Work clothes 0, coveralls +1, double layer +3 °C-WBGT; vapour-barrier suits are not offered (+11, job-specific assessment) | ACGIH clothing adjustment factors | Published values |
| 19 | How a break is counted | Breaks in 15-minute steps; the walk to and from the rest area counts as heat time; a cooled room is taken at WBGT about 19 °C (25 °C, 45%); planning uses the forecast plus 0.82 °C | Bardan design choices | Demonstration values. **Reviewer to set** the rest-area values from measurements |
| 20 | Workers not yet acclimatized | Heat work only for the part of an hour the lower limit allows; shaded work for the rest; always within the 20–100% schedule | NIOSH RAL; Hong Kong Labour Department guidance (August 2026): 15 more minutes of rest an hour for unacclimatised workers | Stricter than the guideline's acclimatization zone. **Reviewer to decide** |
| 21 | Optional wearable warning signs | Heart rate above 180 − age for 5 minutes; above 120 one minute after work stops; estimated core temperature (ECTemp) 38.5 °C, or 38.0 °C for workers not yet acclimatized; 38.0 °C alone is "rising" | ACGIH TLV documentation; NIOSH 2016; ECTemp (Buller et al. 2013) | Optional feature, simulated in the prototype; it can only add rest and never clears anyone. **Occupational physician to confirm** |

Sign-off (to be completed by qualified reviewers before any pilot use):

| Reviewer | Qualification | Rows confirmed | Rows corrected | Date |
|---|---|---|---|---|
| | | | | |
| | | | | |
