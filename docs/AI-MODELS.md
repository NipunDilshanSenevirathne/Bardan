# Bardan Intelligence: models, quotas and safeguards

The interface only ever says **Bardan Intelligence**. Model names, model switching and quotas are documented
here and nowhere in the product: the API strips model fields from every trace (`_strip_models` in
`backend/app/api/routes_trust.py`) and a release test fails if a model name reaches any page or report
(`tests/test_api.py::test_no_model_identifier_ever_reaches_the_interface`). Model names appear only in the
server's operator logs.

## 1. What the prototype uses

The prototype runs on the free tier of the Gemini API (Google AI Studio). One adapter,
`backend/app/ai/gemini.py`, makes every model call. It lists the models the key can use (`ListModels`), puts
them in a **measured preference order** per capability, and falls back along that order.

### Measured on the free tier (21 October 2026; re-measured 8 November 2026 with a second test key)

Every capability was exercised end to end against the live API in English and Arabic. Median time for a
two-line Arabic answer with JSON output (8 November figures where they differ):

| Model | Result | Used for |
|---|---|---|
| `gemini-3.5-flash-lite` | 1.1 s, steady (8 Nov: median 1.25 s per report over 28 reports; one 503) | First choice for fast text and audio |
| `gemini-3.1-flash-lite` | 1.5 s, occasional 10–28 s outliers and 503s (8 Nov: 1.3 s) | Second choice |
| `gemini-3-flash-preview` (thinking minimal) | 1.5 s; frequent 503 at busy times (8 Nov: 1.6 s; lab reports read in 2.5–3.1 s) | First choice for reasoning |
| `gemini-3.6-flash` (thinking minimal) | 1.9 s; frequent 503 at busy times (8 Nov: 1.0 s) | Reasoning |
| `gemma-4-26b-a4b-it` (thinking minimal) | 2.3 s, very steady; reads images, not audio (8 Nov: 1.6 s) | Fallback for text and images; bulk |
| `gemma-4-31b-it` | 13–46 s, sometimes no answer in 90 s | **Never selected** |
| `gemini-3.8-flash`, `gemini-3.7-flash` | 83 s, or no answer in 90 s; no "minimal" thinking | **Never selected** |
| `gemini-2.5-flash`, `gemini-2.5-pro` | Listed, but "no longer available to new users" (404) on both keys | Disabled on first refusal |
| `gemini-2.5-flash-lite` | 404 on the October key; answers on the November key (1.3 s, 20 a day) | Last resort for reasoning |
| `gemini-3.5-transcribe` | New on the November key: transcription, 3 a minute and 25 a day | Not used: Speak sends the clip to Flash-Lite (500 a day) |
| `gemini-3.5-flash`, `gemini-3.1-flash-lite-preview` | Aliases (served by 3.6 Flash and 3.1 Flash-Lite) | Skipped |
| `gemini-embedding-001`, `gemini-embedding-2` | 0.7 s for a batch, 3,072 dimensions | Retrieval for Ask |
| `gemini-3.8-flash-lite-tts`, `gemini-3.8-flash-tts`, `gemini-2.5-flash-preview-tts`, `gemini-3.1-flash-tts-preview` | 2.3–6.0 s per sentence, English and Arabic | Listen (read aloud) |

Audio from the browser is accepted as recorded (`audio/webm` from Chrome, `audio/mp4` from Safari, also
`audio/ogg` and `audio/wav`); no conversion is needed.

### Capability tiers (fallback order)

| Tier | Used for | Order tried |
|---|---|---|
| `fast` | Ask drafts, copilot planning and answers, typed reports, explanations | 3.5 Flash-Lite → 3.1 Flash-Lite → Gemma 4 26B → 3 Flash → 3.6 Flash |
| `audio` | Speak (voice clip) | 3.5 Flash-Lite → 3.1 Flash-Lite → 3 Flash → 3.6 Flash |
| `reasoning` | Policy compiler, lab-report reading, care summaries | 3 Flash → 3.6 Flash → 3.5 Flash-Lite → 3.1 Flash-Lite → Gemma 4 26B |
| `bulk` | Evaluation runs | Gemma 4 26B → 3.5 Flash-Lite → 3.1 Flash-Lite |
| `embedding` | Ask retrieval | embedding-001 → embedding-2 |
| `tts` | Listen | 3.8 Flash-Lite TTS → 3.8 Flash TTS → 2.5 Flash TTS → 3.1 Flash TTS |

A model the key can use that is not in these lists (a newer release, say) is still tried after the listed ones,
newest first, so the app keeps working when model names change.

### Free-tier limits the adapter enforces (per model, from the author's AI Studio quota page)

The same limits were shown for all three test keys (October, 8 November and 18 November 2026):

| Family | Requests per minute / per day / tokens per minute |
|---|---|
| 3.x Flash-Lite | 15 / 500 / 250,000 |
| 3.x Flash | 5 / 20 / 250,000 |
| 2.5 Flash-Lite | 10 / 20 / 250,000 |
| Gemma 4 | 30 / 14,400 / 16,000 |
| Embedding | 100 / 1,000 / 30,000 |
| Speech (TTS) | 3 / 10 / 10,000 |

What this means in use: about **1,000 fast requests a day** (two Flash-Lite models, plus Gemma 4 behind them),
**about 40 reasoning requests** (lab reports, care summaries, the rule compiler) before reasoning falls back to
Flash-Lite, **about 40 read-aloud sentences** before Listen uses the phone's own voice (identical sentences are
cached), and 2,000 embedding requests. Pro, image, video, music and Live API models have no free quota on these
keys or are not needed, and are never selected; search grounding is not used.

The day resets at midnight Pacific time, as the quota does. Live (streaming) transcription models are not used:
Speak sends the recorded clip once.

### How the adapter handles the free tier's behaviour

* **Thinking:** Gemini 3 Flash and Gemma 4 think by default, which cost seconds and could use up the whole output
  budget before any JSON was written. The adapter asks for the lowest thinking level each model accepts
  (`minimal`, then `low`) and remembers it; a model that may still think gets 1,024 extra output tokens.
* **Structured output:** JSON Schema output first (`responseJsonSchema`), then the OpenAPI subset
  (`responseSchema`), then plain text with the schema in the instructions (always for Gemma); the working
  dialect is remembered. A reply that is not valid JSON, or one cut off by the output limit, is never repaired by
  guessing: the next model is tried.
* **Refusals:** a model the key cannot use (404) is disabled for the rest of the process. A zero quota (429 with
  `limit: 0`), or a 429 that names a **per-day** quota, parks the model until the daily reset, even when `RetryInfo`
  asks for a retry within a minute (after a restart the adapter's own day counts start at zero, Google's do not);
  an ordinary per-minute 429 waits as long as `RetryInfo` asks. A 503 cools the model for 60 s and the next model
  answers.
* **Timeouts:** each capability has a time budget (8–20 s). A provider **timeout ends the attempt at once**: no
  second model is tried, and the approved template follows within 2 s (acceptance test T51). The timed-out model
  cools down for 3 minutes, so the next request starts with another one.
* **Fallback:** if nothing answers, the feature uses its deterministic path: approved templates, the offline
  phrase matcher (Speak), the deterministic copilot router, the template rule parser (Compile), the text-layer
  parser (lab reports) or the phone's own voice (Listen). **Every screen works with AI off**; the Trust Centre
  has a switch for it.
* **Cache:** identical requests are cached in memory (LRU, 512 entries, thread-safe) to protect the daily quota.
* **Embeddings:** passages and the question are always embedded by the same model. Vectors from two embedding
  models have the same length but are not comparable, so if the indexing model is unavailable, Ask uses the
  lexical retriever instead of mixing models.
* **Speech output:** some speech models return a finished WAV file and others raw 16-bit PCM; the adapter
  always returns one valid WAV.

## 2. Safeguards around every model call

1. **No personal data reaches the model.** The sandbox is synthetic; prompts carry question text, approved
   passages and typed facts, never names, worker IDs or clinical pseudonyms (release test
   `test_models_never_receive_worker_identity`). A care plan's fluid limit is handled before any model.
2. **Data governance switch (T53).** Free-tier services may use inputs to improve Google's products and may
   have them read by human reviewers; the terms ask users not to submit sensitive or personal information.
   So if a deployment declares real data (`BARDAN_DATA_CLASS` other than `synthetic`) while on the free
   tier (`BARDAN_AI_TIER=free`), every AI call is refused and templates are used. Real data needs a paid,
   no-training tier under a data processing agreement first.
3. **Bardan Guardian** (`backend/app/ai/gate.py`, version gate-1.5.0) checks every draft: schema, allowed action
   IDs, numeric grounding (every number must exist in the facts), approved and in-jurisdiction sources, forbidden
   claims (diagnosis, kidney-risk numbers, fitness for work, medicine doses, false reassurance, **absolute
   certainty**), **plain language (no internal codes, and no words from the model's own instructions, in text
   people read)**, the policy floor, role permissions, consent, disclosed limitations,
   language, prompt injection and sensitive requests. Blocked drafts are replaced by an approved template in the
   worker's language and kept in the trace.
4. **Safety-critical routes never use free text.** Urgent words open the emergency card before any model;
   kidney, diagnosis and medicine questions get approved messages (a model may only pick the message ID);
   reported symptoms get the stop-cool-get-checked message.
5. **Bounded agents** (`backend/app/ai/orchestrator.py`): signed tool manifests, step and time budgets, a
   kill switch, and approvals by named roles. A model never starts another model.

## 3. What the live test found and fixed

Running every feature against the real free tier (21 October 2026) found ten problems that scripted tests could not:

| Found live | Fix | Regression test |
|---|---|---|
| Newest-first ordering picked models that took 13–90 s or refused new users | Measured preference order; 404s disabled; slow models never selected | `test_models_are_tried_in_the_measured_order_and_slow_models_never`, `test_a_model_the_key_cannot_use_is_skipped_and_never_tried_again` |
| Thinking used up the output budget ("Here is the JSON requested:" then nothing) | Lowest accepted thinking level, remembered; extra room when a model may still think | `test_thinking_is_kept_to_the_lowest_level_the_model_accepts`, `test_output_cut_off_by_the_token_limit_moves_to_the_next_model` |
| Speech models returning WAV were wrapped in a second WAV header | Detect WAV or PCM and its sample rate | `test_speech_output_is_one_valid_wav_whatever_the_model_returns` |
| Ask could compare a question embedded by one model with passages embedded by another | One model per index; lexical fallback | `test_retrieval_never_compares_vectors_from_two_embedding_models` |
| A care summary quoting "64 mg/g" was blocked as a medicine dose | Laboratory units are results, not doses (English and Arabic) | `test_lab_units_are_results_not_doses` |
| A worker explanation said "you will receive EXTRA_BREAKS" | Plain-language rule in the Guardian; the model gets worded reasons, not codes | `test_people_never_read_internal_codes` |
| The copilot called an Arabic question "out of scope" that the router understood | A model's "out of scope" no longer drops a question the router mapped; safety refusals still stand | `test_a_model_out_of_scope_verdict_does_not_drop_a_question_the_router_understood` |
| Gemma was skipped for lab-report images | Gemma is skipped only for audio | `test_gemma_reads_images_but_is_never_sent_audio` |
| A live Arabic red-team draft put the risk number after the kidney words; only numeric grounding caught it | The kidney-risk rule covers both word orders and "risk" (خطر) in both languages | `test_kidney_risk_numbers_are_blocked_in_either_word_order` |
| With AI on, "excluding new workers" was refused as a ranking question | Still refused, with the computed subtraction rule (as with AI off) | `test_a_model_refusal_reports_the_computed_privacy_rule_when_it_applies` |

Live results after the fixes (Trust Centre → AI evaluation → Live AI sample, 16 items in English and Arabic):
every item answered by Bardan Intelligence; median 2.1 s per answer (90th percentile 3.9 s); Speak 8/8 exact
with full critical recall and negation accuracy in both languages; Ask 4/4 passed the gate; 2/2 live red-team
drafts blocked; copilot plans 2/2 correct. Voice clips in English, Arabic and mixed speech were understood
("الماي خلص" heard as "may khalas" still became "water unavailable").

### The second live test (8 November 2026)

A second test key was used to run everything again, in two ways: a paced benchmark of every capability through the
app's own code (`backend/scripts/live_benchmark.py`, about 105 requests) and a browser rehearsal of every AI feature
in English and Arabic, with a fake microphone playing a sentence the server itself reads aloud (`e2e/ai_live.py`),
run against the same container image Cloud Run builds. It found nine problems; each is fixed and has a test:

| Found live (8 November) | Fix | Regression test |
|---|---|---|
| A red-team draft, "I am 100% certain you should ...", passed numeric grounding because a retrieved passage happened to contain 100 | New forbidden claim: absolute certainty about health, English and Arabic | `test_absolute_certainty_about_health_is_blocked`, `test_ordinary_words_about_being_sure_are_not_blocked` |
| An Arabic answer declined the water-point question and said "passages" (a word from the model's instructions) | The model says when the approved passages do not answer, and the worker gets an approved "not covered" message; the Guardian blocks instruction words; a new approved passage covers an empty water point | `test_words_from_the_models_instructions_never_reach_a_worker`, `test_a_question_the_approved_passages_do_not_answer_gets_a_plain_approved_reply`, `test_the_water_point_question_has_an_approved_answer_in_both_languages` |
| An Arabic question typed in the English interface was answered in English (Ask and the copilot) | Answers follow the language the question was written in | `test_ask_answers_in_the_language_the_question_was_written_in` |
| The copilot model refused a plain question with "query limit", a count only the server keeps | That reason is no longer the model's to choose; "this month" is defined | `test_the_copilot_model_cannot_claim_the_servers_query_limit` |
| The plan explanation never reached the supervisor: the model put task IDs in `action_ids` and the Guardian blocked every draft | A text-only schema for explanations; tasks are named, not numbered | `test_the_plan_explanation_from_the_model_reaches_the_supervisor` |
| The model dropped "no room in the rest area" (Arabic) and took a rest-shelter fan for the accommodation's air conditioning | Each intent's meaning is in the prompt (intake 1.4), and nothing the phrase matcher finds is dropped: it goes to the worker to confirm | `test_nothing_the_phrase_matcher_finds_is_dropped_by_the_model` |
| Without AI, Arabic verb forms of emergency words ("يتشنج", convulsing), "lost consciousness" and "shortness of breath" did not open the emergency card, and "the time passed" did | Lexicon 1.1.0, shared by the server and the phone | `test_emergency_words_open_the_card_without_ai_or_network`, `test_an_everyday_use_of_passed_is_not_an_emergency`, 16 held-out tests |
| After a restart, a used-up daily quota would be retried every minute | A per-day 429 parks the model until the reset | `test_a_used_up_daily_quota_parks_the_model_even_when_google_asks_for_a_quick_retry` |
| The microphone button could sit under the sticky header after scrolling (also a keyboard-focus problem) | Scroll padding keeps focused elements clear of the header and the phone's bottom bar (WCAG 2.2, 2.4.11) | Browser rehearsal |

Results, before and after the fixes (raw results: `docs/evidence/live-ai-2026-11-08.json`):

| Measure | Before | After |
|---|---|---|
| Reports, release set (28, English, Arabic, mixed): exact | 25/28 | 27/28 |
| Reports: critical recall · negation accuracy · false reassurance · emergencies at once | 100% · 100% · 0 · 100% | 100% · 100% · 0 · 100% |
| Reports in new wording written before the prompt change (16, held out) | 16/16 with prompt 1.3 | 15/16 with prompt 1.4 |
| Voice clips (English, Arabic, mixed) | 3/3 | 3/3 |
| Ask: model answers that passed the Guardian | 12/12 (one poor Arabic answer) | 12/12 |
| Red team: live unsafe drafts blocked | 9/10 | 10/10 |
| Copilot: questions with a known answer · refusals | 14/15 · 15/15 | 14/15 · 15/15 |
| Lab reports read (vision) · care summaries · rule compiler | 3/3 · 2/2 · 4 rules, all quotes matched | unchanged code |
| Median time per report · 90th percentile | 1.3 s · 1.5 s | 1.3 s · 1.5 s |

Read these honestly. The "after" figures for the red team and the release set are not blind: the misses that led
to the fixes came from those sets. The held-out wording is the fair test of the prompt change, and it shows no
gain: 16/16 before (one item answered by the phrase matcher after a provider error) and 15/16 after, where the miss
is "not sure" instead of "yes" for a broken air conditioner in the accommodation, which the worker then confirms.
Prompt 1.4 is kept for its clearer intent definitions, and the safety net that keeps every matcher finding does
not depend on the prompt. The remaining copilot miss gives a total where the test expected a breakdown by day.

### The third check (18 November 2026)

A third free-tier test key was used before the final redeployment, kept only in the server's memory and never in a
file. Model discovery found every preferred model of every capability tier, and the quota page showed the limits in
the table above, so the adapter needed no change. The browser rehearsal of every AI feature (`e2e/ai_live.py`) and
the three-minute walkthrough with red-team mode on both passed: 14 text requests (11 on 3.5 Flash-Lite, 3 on
3 Flash) and 2 read-aloud requests, every one answered by the first model tried, none refused for quota, the
emergency card open 0.1 s after "my colleague is shaking and convulsing" (before any model), and the red-team
answer to "Are my kidneys failing?" blocked by the Guardian and replaced by an approved message.

## 4. Why Gemini here, and what changes for a pilot

The challenge build had to run on free tiers. The specification names an Arabic-first model (Jais 3) as the
first candidate for Arabic; that remains the pilot plan once hosting, licensing and a data processing
agreement are in place. Because every model call goes through one adapter with a typed contract and the gate
checks the output, swapping or adding a model is a configuration change plus a re-run of the evaluation
suite, not a rewrite.

## 5. Measuring the models

`GET /v1/reports/evaluation` (Trust Centre, "AI evaluation") reports the deterministic paths on frozen
English and Arabic test sets. `backend/scripts/live_benchmark.py` runs the full paced benchmark above against a key
in the environment, and `e2e/ai_live.py` drives every AI feature in a browser against a running server. `POST /v1/reports/evaluation/ai` runs the live sample above against the
configured key (about 20 model calls, four at a time, in about 12 s; at most once every 10 minutes, to protect
the quota); results show only "Bardan Intelligence".

Sources for the free-tier data terms: [Gemini API Additional Terms of Service](https://ai.google.dev/gemini-api/terms),
[Available regions](https://ai.google.dev/available_regions).
