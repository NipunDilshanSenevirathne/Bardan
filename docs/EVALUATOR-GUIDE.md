# Evaluator guide: Bardan in ten minutes

Bardan is a working prototype with **synthetic data only**: a fictional 40-worker site in Abu Dhabi, real
replayed weather from 19 August 2025, fictional people and a mock dialler that never contacts emergency
services. Everything is in **English and Arabic**: switch language and light or dark theme from the top bar.
The heat rules carry a **Demo heat rules** label until a qualified reviewer has checked them against the current
Abu Dhabi guideline ([RULE-REVIEW.md](RULE-REVIEW.md)). For what is implemented, simulated and planned on one
page, see [ONE-PAGE.md](ONE-PAGE.md).

## 1. Open it

1. Open **[bardan-1049030199952.europe-west1.run.app](https://bardan-1049030199952.europe-west1.run.app)** (or `http://localhost:8080` locally) and press **Open the judge sandbox**.
   After a quiet spell the first page can take a few seconds while the server wakes up.
2. Choose any persona. You get your own sandbox: nothing you do affects other judges, and it resets after an
   hour. **Guided tour** (bottom of the side menu) walks through the story in seven steps.
3. The scene picker in the top bar moves the site clock through the day; the **Emergency** button is always
   one tap away.

| Persona | Role | Language | What to look at |
|---|---|---|---|
| Ravi Kumar | New rebar helper, day 2 of acclimatization | English | Today card (press *Listen*), reports, Ask, private check-in, "This didn't happen" |
| Anwar Hussain | Steel fixer in the kidney pathway | Arabic | Voice or typed report in Arabic, My health, My data (Bardan's promises, read aloud), consent, Kidney Passport |
| Joseph Mathew | Site supervisor | English | Site now, Tomorrow's plan, Tasks, Capacity |
| Sara Al Mansoori | HSE lead | Arabic | Compliance pack, Copilot, Policy packs, Watch, Audit log |
| Dr Fatima Al Hashimi | Clinician | Arabic | Clinic queue, Patient, Document AI |
| Mariam Haddad | Site nurse | English | Hydration check |
| Guest reviewer | Evaluator (independent observer) | English | Trust Centre: every proof report; the drill console |

## 2. The story (scenes)

| Scene | Site time | What happens |
|---|---|---|
| 1. Evening before | 18 Aug 18:00 | Joseph evaluates the draft plan, then lets Bardan optimise and approves it |
| 2. Shift start | 19 Aug 07:00 | The plan is active; required daily actions become tasks |
| 3. Zone A turns harsher | 09:05 | The live reading beats the forecast; Ravi is moved to shaded work automatically |
| 4. Water runs out | 09:45 | A worker reports it in Arabic; heat work in Zone A stops until water is verified |
| 5. A frightening question | 10:30 | "Are my kidneys failing?": an approved answer, never a guess |
| 6. Emergency drill | 11:10 | AI and internet off: the emergency card still works and is honest about what was sent |
| 7. Midday break | 12:40 | The federal 12:30–15:00 rule is enforced by the engine |
| 8. Clinic visit | 14:05 | Results, referral and privacy: the employer sees only "clinic visit 14:00–16:00" |

## 3. A ten-minute walkthrough, by judging criterion

**Real-world health value.** As Joseph, open *Tomorrow's plan*: the 72-hour zone forecast (with its 90 %
interval), *Evaluate draft*, then *Optimise with Bardan*. The slab pour moves out of the harshest hours, breaks are
staggered to fit 20 shaded seats, the new workers stay within their acclimatization schedule, and every
change has a reason. The *Fairness across the week* card flags a crew that keeps getting the hottest slots.

**Technical design.** Jump to scene 3 as Ravi: the zone turned harsher than forecast and the live value
governs; his card changes to a shaded task with the reason. In *Trust Centre → Decision replay*, press
*Run both engines*: the browser's TypeScript engine and the server's Python engine give identical decisions
on all 49 conformance cases (the device engine works offline).

**Working solution.** As Ravi, press *Listen* on the action card (Bardan Intelligence speech, or the phone's own
voice when AI is off). Scene 4 as Anwar: type or say «ما فيني دوخة، بس الماي خلص». Bardan shows the words it
heard ("not dizzy" negated, "water finished" affirmed) and nothing is saved until he confirms. As Joseph,
accept the water task and report it complete; as Ravi, press *This didn't happen*: the task escalates to HSE
and the supervisor never sees who disputed. As Sara, accept it, add your *independent spot check*, write what you
found and *Resolve the dispute*, then complete and verify it. Verification is refused while a dispute is open and
before a fresh independent check; Ravi is told how it was resolved and can still challenge it.

**Responsible AI and data governance.**
* Open *Sandbox controls* (the sliders icon in the top bar) and turn on *Red-team test mode*, then ask as Anwar «هل كليتي تفشل؟». The overconfident draft
  ("40 % chance your kidneys fail") is blocked by Bardan Guardian and an approved answer is shown; open the
  AI trace to see the blocked draft and the rule.
* In *Sandbox controls* turn off *Bardan Intelligence (AI)* and turn on *Simulate no internet*, press *Emergency* and tap *Confused*: the card opens at once and says
  "dialler opened", never "help called". It separates *alert saved on this phone*, *received by the Bardan
  server* (a real receipt) and *seen by the site team* (only after a supervisor or HSE presses *I’m responding* on
  *Site now*). On a real phone, airplane mode works the same way: reports and the alert wait on the phone, survive a
  reload, and send by themselves when the network returns.
* As Joseph, use *Try to open a clinical record* on *Site now*: denied and written to the audit log. As Sara,
  open *Copilot* and press *Which worker reports the most symptoms?* (refused) and *Symptom reports this week
  excluding new workers* (blocked: it would single out three people by subtraction).

**Scale and deploy.** *Trust Centre → AI evaluation* shows the planner solving 200 workers in well under a
second and every plan re-validated independently; *Policy packs* compiles a (paraphrased) Sharjah excerpt
into draft rules with verbatim quotes and generated tests, which need two qualified approvals.

**Pilot readiness.** *Trust Centre → Release tests* lists all 97 acceptance cases from the specification
with the automated tests that check them (577 tests, all passing), and the measured load test at the bottom.
*Drills and comparison* shows what each workflow does in seven situations, checked against the real code when
the report is built, and the observed drill results (none published yet). There is no simulated percentage.

**Run a drill yourself (optional, about 15 minutes with three phones).** As Guest reviewer open *Drills*, set up a
series and open the invite links on two or three phones (worker, supervisor, HSE). Start a drill, act it out,
and tap what you see; the console times everything in real time and the export is tamper-checked. The protocol,
including the safety rules, is in [DRILL-PROTOCOL.md](DRILL-PROTOCOL.md).

## 4. Where the proof is

| Trust Centre tab | What it shows |
|---|---|
| AI trace | Every AI step: inputs by reference, the gate's checks, blocked drafts. Each person sees their own runs; the reviewer sees de-identified runs (a worker's own words are withheld) and that access is audited |
| AI evaluation | Frozen English and Arabic test sets per capability, the forecast backtest, planner runs, and a live AI sample when a key is configured |
| Red team | 45 generated attacks across the gate, Speak, the copilot and the agents; failures are listed |
| Decision replay | The same 49 policy cases on the device engine and the server, compared by meaning |
| Drills and comparison | What each workflow does in seven situations (scripted checks of the real code), and observed drill results from tamper-checked exports |
| Release tests | The 97 Appendix D cases (English and Arabic), the 577 automated tests behind them, and the load test |
| Agents | Signed tool manifests, budgets and approvals for each bounded agent |
| Licences | Every library, data source and photo with its licence |

## 5. What is simulated, and what is not built

* **Simulated:** the site, the people, the instruments (derived from replayed NASA POWER weather), the
  forecast error, the lab results, the history behind the copilot and Watch. Every simulated value says so.
* **Live when configured:** Bardan Intelligence (Gemini free tier) and the Open-Meteo forecast mode. The free tier
  allows about 1,000 quick AI requests a day and about 40 for lab reports, summaries and the rule compiler; when
  a day's quota is used up, answers come from approved templates and the deterministic engines, labelled as such,
  and every screen keeps working. The quota resets at midnight Pacific time (12:00 in Abu Dhabi in winter, 11:00 in summer).
* **Mock:** the emergency dialler and all messages; nothing leaves the sandbox.
* **Demonstration values:** the heat rules are demo encodings pending qualified review; the WBGT planning bands
  and some rest minutes are demonstration values ([RULE-REVIEW.md](RULE-REVIEW.md)).
* **Not built in the prototype:** the camera pulse research module, recorded-speech test sets with
  consenting speakers, real lab or HR integrations, and model training. The release tests show how the
  safety rules for these are already enforced (for example, physiological fields cannot change
  acclimatization, and real data cannot reach a free-tier model).

---

## دليل سريع للمقيّمين (بالعربية)

بَرْدًا نموذج أولي يعمل **ببيانات اصطناعية فقط**: موقع بناء وهمي في أبوظبي يضم 40 عاملاً، وطقس حقيقي مُعاد ليوم
19 أغسطس 2025، وأشخاص وهميون، واتصال طوارئ تجريبي لا يتصل بأي جهة. الواجهة كلها بالإنجليزية والعربية.

1. افتح الرابط [bardan-1049030199952.europe-west1.run.app](https://bardan-1049030199952.europe-west1.run.app) واضغط **افتح بيئة التجربة**، ثم اختر شخصية. لكل مقيّم بيئته الخاصة، وتُعاد تهيئتها كل ساعة.
2. **جولة إرشادية** في أسفل القائمة الجانبية تعرض القصة في سبع خطوات، ومنتقي المشاهد في الأعلى يحرك ساعة الموقع.
3. أهم ما يمكن تجربته:
   * بصفة جوزيف: «خطة الغد» ثم «قيّم المسودة» ثم «حسّن مع بَرْدًا»؛ يبتعد العمل الشاق عن أشد الساعات وتتوزع الاستراحات على المقاعد المظللة.
   * بصفة أنور: اكتب أو قل «ما فيني دوخة، بس الماي خلص» وراجع الكلمات قبل التأكيد.
   * بصفة رافي: اضغط «هذا لم يحدث» على مهمة الماء فتُصعَّد إلى مسؤول السلامة دون كشف هويته.
   * بصفة رافي: اضغط «استمع» على بطاقة «ماذا تفعل الآن» لسماعها، وبصفة أنور افتح «بياناتي والمشاركة» لسماع وعود بَرْدًا للعامل.
   * افتح «عناصر التحكم في بيئة التجربة» من أعلى الشاشة وفعّل «وضع اختبار الفريق الأحمر»، ثم اسأل بصفة أنور «هل كليتي تفشل؟»: تُمنع المسودة غير الآمنة ويظهر رد معتمد.
   * أوقف «ذكاء بَرْدًا» وفعّل «محاكاة انقطاع الإنترنت»، ثم اضغط «طوارئ» ثم «ارتباك»: تعمل البطاقة فوراً وتقول بصدق «فُتح الاتصال».
   * بصفة المقيّم الضيف: «مركز الثقة» يعرض التقييمات والاختبارات (97 حالة قبول و577 اختباراً آلياً) واختبار الحمل والتراخيص، وتبويب «التمارين والمقارنة» يعرض ما يفعله كل أسلوب عمل ونتائج التمارين المرصودة (لم تُنشر أي تمارين بعد).
   * بصفة مسؤول السلامة: بعد اعتراض العامل، أضف «فحصاً ميدانياً مستقلاً» واكتب ما وجدته ثم «حلّ الاعتراض»؛ لا يمكن التحقق من المهمة قبل ذلك، ويُبلَّغ العامل ويمكنه الاعتراض مجدداً.
   * قواعد الحرارة معروضة بعلامة «قواعد حرارة للعرض» إلى أن يراجعها مختص مؤهل مقابل الدليل الحالي في أبوظبي.
