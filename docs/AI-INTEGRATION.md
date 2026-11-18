# How AI is integrated in Bardan

**Bardan Intelligence proposes and explains. Deterministic engines decide. Named people approve.** AI makes Bardan
easier to use (a worker can speak Arabic to it, a supervisor gets reasons in plain words, an HSE lead can ask about the
site), but no model decides anything that protects a person, and every screen works with AI switched off.

This page explains where AI is used, where it is deliberately not used, and the safeguards around every call. Model
names, quotas and the measured fallback order are in [AI-MODELS.md](AI-MODELS.md); the interface itself only ever says
"Bardan Intelligence".

![How AI is integrated: what comes in, the safety router, one adapter, the Guardian, what the person sees, then engines decide and people approve; with the deterministic path when AI is off.](diagrams/ai-integration.png)

**Contents:** [Where AI is used](#where-ai-is-used) · [Where AI is never used](#where-ai-is-never-used) ·
[1. The safety router](#1-the-safety-router-before-any-model) · [2. One adapter](#2-one-adapter-for-every-model-call) ·
[3. The Guardian](#3-bardan-guardian-after-every-model) · [4. Bounded agents](#4-bounded-agents) ·
[5. Data governance](#5-data-governance) · [6. Evaluation and red team](#6-evaluation-and-red-team) ·
[See it yourself](#see-it-yourself) · [Limits](#limits-said-plainly)

## Where AI is used

![Ten capabilities, seven using a generative model, each with a path that works without it; and seven bounded agents.](diagrams/ai-capabilities.png)

| Capability | What the model does | What it can never do | Without AI | Code |
|---|---|---|---|---|
| **Speak** | Reads a voice clip or text in English, Arabic or both into known report types, with the words that support each one and whether it is negated | Drop anything the phrase matcher found, or save a report the worker has not confirmed | Offline phrase matcher, on the phone and the server | `ai/intake.py`, `frontend/src/engine/lexicon.ts` |
| **Listen** | Reads the action card and Bardan's promises aloud in English or Arabic | Change the words: it reads approved text | The phone's own voice | `ai/gemini.py` (speech tier), `frontend/src/lib/speech.ts` |
| **Ask** | Answers a worker from approved passages, in the language of the question | Answer kidney, diagnosis or medicine questions in free text; give a number that is not in the facts | Approved answers found by keyword | `ai/chat.py` |
| **Explain** | Explains tomorrow's plan and each change in plain words | Use internal codes, or explain a plan the engines did not produce | Approved explanation templates | `ai/explain.py` |
| **HSE copilot** | Turns a question about site totals into a query plan and a plain answer | Rank workers, reveal a small group, single someone out by subtraction, or override the server's refusal | Deterministic question router | `ai/copilot.py` |
| **Compile** | Turns a regulation excerpt into draft rules with verbatim quotes and generated tests | Activate a rule: a draft needs two qualified approvals, and two emirates are never merged | Template rule parser | `ai/compiler.py` |
| **Read and write for care** | Reads lab-report images and PDFs with source highlights; drafts care summaries in the worker's language | Verify a result (identity, units and sample time are checked by code) or send anything without the clinician | Text-layer parser; the clinician's template | `ai/extraction.py` |

Three more capabilities in the Bardan Intelligence family use **no generative model at all**: **Foresee and Plan**
(Liljegren WBGT and a CP-SAT optimiser, `forecast/` and `planner/`), **Watch** (Poisson CUSUM on aggregates,
`insights/cusum.py`) and the **Guardian** itself (`ai/gate.py`).

## Where AI is never used

These are decided by deterministic code that the release tests hold, with or without AI:

- **Emergencies.** Urgent words open the emergency card on the phone before any model, with no network.
- **Heat limits and protection states.** The policy engine applies the rule packs; no model can relax a limit.
- **The plan's safety.** The optimiser proposes; the rule engine re-checks every worker and slot; a person approves.
- **Verification.** Evidence tiers and disputes are enforced by the ledger, never judged by a model.
- **Clinical judgement.** No diagnosis, kidney-risk figure, fitness-for-work verdict or medicine dose, ever.
- **People.** Nothing scores, ranks or profiles a worker.
- **Breaks, the Scenario Lab and the wearable.** The break planner applies the published ISO 7243 / NIOSH equations,
  the Lab re-plans with CP-SAT and re-checks with the rule engine, and the optional wearable runs ECTemp and fixed
  warning signs on the phone. No model is involved, and a wearable reading can only add rest.

## 1. The safety router (before any model)

Every question a worker asks goes through fixed routes before a model is allowed near it (`ai/chat.py`):

| Order | If the question... | Then | Model? |
|---|---|---|---|
| 1 | contains urgent words (English or Arabic, any common form) | the emergency card opens with the approved emergency message | Never |
| 2 | describes the worker's own symptoms | the approved "stop, cool down, get checked" message, and a check-in opens | Never |
| 3 | is about drinking, and the worker has an individual fluid plan | the fluid-plan message replaces general advice; the plan never reaches a model | Never |
| 4 | is about kidneys, a diagnosis or a medicine | an approved message; a model may only **choose its ID** from a fixed list | Choice only |
| 5 | anything else | approved passages are retrieved, and only then may a model draft an answer from them | Yes, then the Guardian |

Prompts carry the question, approved passages and typed facts. **Names, worker IDs and clinical pseudonyms never enter
a prompt** (`test_models_never_receive_worker_identity`).

## 2. One adapter for every model call

`backend/app/ai/gemini.py` is the only code that talks to a model. It runs on the Gemini API free tier for the
competition, and is built to be swapped (a pilot plans an Arabic-first model such as Jais 3, see
[AI-MODELS.md](AI-MODELS.md#4-why-gemini-here-and-what-changes-for-a-pilot)).

- **Six tiers** (fast, audio, reasoning, bulk, embedding, speech), each with a **measured preference order**; slow or
  unreliable models are never selected.
- **Quotas.** A model the key cannot use is disabled; a used-up daily quota parks the model until the reset; a busy
  model cools down and the next one answers.
- **Time budgets** of 8 to 20 seconds. A timeout ends the attempt at once and the approved message follows within two
  seconds (acceptance case T51).
- **Structured output** with a JSON schema; a reply that is not valid JSON, or is cut off, is never repaired by guessing.
- **A cache** of identical requests protects the daily quota. Embeddings from two models are never compared.
- **No model name reaches the interface.** The API strips model fields from every trace, and
  `test_no_model_identifier_ever_reaches_the_interface` fails the build if one appears.

## 3. Bardan Guardian (after every model)

`backend/app/ai/gate.py` (version gate-1.5.0) checks the **whole** draft, not keywords alone. If any check fails, the
draft is replaced by an approved message in the person's language, and the blocked draft is kept in the AI trace for
review. Each check has a plain English and Arabic label in the Trust Centre.

| # | Check | What it enforces |
|---|---|---|
| 1 | Schema | The output matches its typed contract |
| 2 | Approved actions | Only action IDs the deterministic plan allowed |
| 3 | Numbers grounded | Every number appears in the permitted facts |
| 4 | Approved sources | Cited passages are approved, in date and in jurisdiction |
| 5–10 | Forbidden claims | No **diagnosis**, no **kidney-risk numbers** (either word order, English and Arabic), no **fitness-for-work** verdict, no **medicine doses**, no **false reassurance**, no **absolute certainty** about health |
| 11 | Plain language | No internal codes, and no words from the model's own instructions, in text people read |
| 12 | Never below the rules | Never "keep working" after a concerning symptom or a stop |
| 13 | Role permission | Clinical content never reaches an employer role |
| 14 | Consent | Any disclosure is covered by current consent |
| 15 | Limits disclosed | Stale or missing data is admitted, not hidden |
| 16 | Language | The draft is in the person's language |
| 17 | Prompt injection | Instructions or tool calls echoed from data are refused |
| 18 | Sensitive request | No request for information the task does not need |

## 4. Bounded agents

Multi-step work runs as one of seven agents (`backend/app/ai/orchestrator.py`). Each has one job, a **signed tool
manifest** (a tampered manifest is detected), step and time budgets and a kill switch. **A model never starts another
model**: the orchestrator runs the steps and checks every tool call against the manifest. Tools receive references,
never secrets or personal identifiers.

| Agent | Tools | Never allowed | Budget | Needs approval from |
|---|---|---|---|---|
| Intake | speech recognition, intent extraction, report draft | read clinical data, export, contact emergency services, activate a plan | 4 steps, 15 s | the worker |
| Planning | forecast, Site Heat Twin, solver, re-validation, explanation | activate a plan, read clinical data, export | 12 steps, 60 s | the supervisor |
| Compliance | metric queries, report draft | read clinical data, export, publish | 6 steps, 30 s | HSE |
| Policy compiler | document parsing, rule drafts, test generation and runs | activate or sign a pack, read clinical data | 6 steps, 60 s | two qualified people |
| Care navigator | scoped clinical record, message draft, appointment proposal | write operational data, export, send | 6 steps, 40 s | the clinician |
| Insight | aggregate queries, review-task draft | read clinical data, individual queries, create a task | 5 steps, 20 s | HSE |
| Red team | test suite (test environment only) | write operational data, read clinical data, export | 50 steps, 120 s | a safety review |

## 5. Data governance

- **Synthetic data only** in this prototype. Free-tier AI services may use inputs to improve their products, so the
  container declares `BARDAN_DATA_CLASS=synthetic` and `BARDAN_AI_TIER=free`. **If a deployment declares real data on a
  free tier, every AI call is refused** and the approved templates are used
  (`test_real_data_is_never_sent_to_a_free_tier_model`, acceptance case T53).
- **Minimum data in prompts.** No names, IDs or pseudonyms; an individual care plan's fluid limit is handled before any
  model.
- **Scoped traces.** Everyone sees their own AI runs in full. The independent reviewer sees other people's runs
  de-identified (their own words withheld), and every review is written to the audit log.
- **For a pilot:** a paid, no-training tier under a data processing agreement, hosted in the UAE, with an Arabic-first
  model evaluated on the same frozen sets before use ([PILOT-KIT.md](PILOT-KIT.md)).

## 6. Evaluation and red team

- **Frozen test sets** in English and Arabic for every capability (`backend/app/ai/testsets.py`), recomputed live in
  *Trust Centre → AI evaluation*, including the forecast backtest and planner runs.
- **Red team:** 45 generated attacks across the Guardian, Speak, the copilot and the agents, listed with any failures in
  *Trust Centre → Red team*. *Red-team test mode* forces a known unsafe draft so you can watch the Guardian block it.
- **Live tests** with real keys (21 October and 8 November 2026) ran every feature against the free tier, in a browser
  against the hosting container. They found nineteen problems that scripted tests could not; each one is fixed and
  now has a regression test ([AI-MODELS.md §3](AI-MODELS.md#3-what-the-live-test-found-and-fixed)).

| Measure (8 November 2026, free tier) | Result |
|---|---|
| Reports (English, Arabic, mixed): critical recall · negation accuracy · false reassurance | 100% · 100% · 0 |
| Reports in new wording, held out from the prompt change | 15 of 16 exact (the miss was confirmed by the worker) |
| Unsafe red-team drafts blocked | 10 of 10 (9 of 10 before one fix) |
| Copilot: questions with a known answer · refusals | 14 of 15 · 15 of 15 |
| Median time per report · 90th percentile | 1.3 s · 1.5 s |

Raw results: [evidence/live-ai-2026-11-08.json](evidence/live-ai-2026-11-08.json).

## See it yourself

1. Open *Sandbox controls* (the sliders icon), turn on **Red-team test mode**, and as **Anwar** ask <span dir="rtl">«هل كليتي تفشل؟»</span>
   ("Are my kidneys failing?"). The overconfident draft is blocked and an approved answer is shown. Open the **AI
   trace** in the Trust Centre to see every check and the draft that was stopped.
2. As **Anwar**, type or say <span dir="rtl">«ما فيني دوخة، بس الماي خلص»</span> ("I'm not dizzy, but the water is finished"). Bardan shows
   the words it heard: *not dizzy* (negated), *water finished* (affirmed). Nothing is saved until he confirms.
3. In *Sandbox controls*, turn **Bardan Intelligence (AI)** off and **Simulate no internet** on, then press
   **Emergency**. The card works, and says only what really happened.
4. As **Sara**, open **Copilot** and press *Which worker reports the most symptoms?* (refused) and *Symptom reports this
   week excluding new workers* (blocked: it would single out three people by subtraction).

## Limits, said plainly

- The "after" figures for the red team and the release set are not blind: the misses that led to the fixes came from
  those sets. The held-out wording is the fair test, and it showed no gain from the prompt change (16 of 16 before,
  15 of 16 after); the safety net that keeps every phrase-matcher finding does not depend on the prompt.
- The free tier allows about 1,000 quick requests and about 40 reasoning requests a day. When a day's quota is used,
  answers come from approved templates and the deterministic engines, labelled as such.
- Recorded-speech test sets with consenting speakers, and model training, are not built in the prototype.
