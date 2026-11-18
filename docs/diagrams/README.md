# Bardan diagrams

Every picture in the README and the guides, with its source. Two kinds:

- **Hand-laid diagrams** (`custom/*.html`, drawn in HTML and rendered to PNG): the README's overview pictures and the
  screenshot collages.
- **Technical diagrams** (`src/*.mmd`, Mermaid): exact flows, sequences and the task state machine, rendered to PNG
  and SVG. They are embedded in [ARCHITECTURE.md](../ARCHITECTURE.md).

All of them use the Bardan palette (navy, blue, cyan, amber, red, and violet for AI) and only English and Arabic. The
screenshots are captured from the prototype itself, running on synthetic data.

## Overview pictures

| Picture | What it shows | Source |
|---|---|---|
| [hero.png](hero.png) | The banner: Bardan's promise, key numbers, two real phone screens | [custom/hero.html](custom/hero.html) |
| [problem-gap.png](problem-gap.png) | What already exists, where it breaks after the warning, and what Bardan adds | [custom/problem-gap.html](custom/problem-gap.html) |
| [how-it-works.png](how-it-works.png) | The loop Foresee → Plan → Live day → Act → Prove, and what happens on a dispute, an abnormal kidney test and a lost network | [custom/how-it-works.html](custom/how-it-works.html) |
| [day-timeline.png](day-timeline.png) | The demonstration day in eight scenes, on a heat strip from the evening before to the clinic visit | [custom/day-timeline.html](custom/day-timeline.html) |
| [ai-integration.png](ai-integration.png) | How AI is integrated: safety router, one adapter, Guardian, engines decide, people approve, AI-off path | [custom/ai-integration.html](custom/ai-integration.html) |
| [ai-capabilities.png](ai-capabilities.png) | Ten capabilities (seven generative, each with an AI-off path) and seven bounded agents | [custom/ai-capabilities.html](custom/ai-capabilities.html) |
| [evidence-ladder.png](evidence-ladder.png) | Evidence tiers E0 to E4 and the rules for verification and disputes | [custom/evidence-ladder.html](custom/evidence-ladder.html) |
| [privacy-matrix.png](privacy-matrix.png) | Who sees what, for each of the five roles, including the optional wearable | [custom/privacy-matrix.html](custom/privacy-matrix.html) |
| [architecture.png](architecture.png) | The layers: people, phone, API, deterministic engines, AI, stores; hosting and outside services | [custom/architecture.html](custom/architecture.html) |
| [proof.png](proof.png) | The measured results, with the method next to each number, and what is not done yet | [custom/proof.html](custom/proof.html) |
| [screens-worker.png](screens-worker.png) | Four worker screens: action card offline, Arabic report heard back, "This didn't happen", emergency card | [custom/screens-worker.html](custom/screens-worker.html) |
| [screens-trust.png](screens-trust.png) | Four trust screens: blocked unsafe draft, honest emergency states, independent verification, who saw my data | [custom/screens-trust.html](custom/screens-trust.html) |
| [screens-console.png](screens-console.png) | Six console screens: plan, site now, escalated task, resolved dispute, AI trace, decision replay | [custom/screens-console.html](custom/screens-console.html) |
| [screens-lab.png](screens-lab.png) | The Scenario Lab and shift simulator: your own scenario, the shift re-planned, every phone, why each break | [custom/screens-lab.html](custom/screens-lab.html) |
| [screens-wearable.png](screens-wearable.png) | The optional wearable: the worker's choices, the worker told first, the supervisor's task with no number | [custom/screens-wearable.html](custom/screens-wearable.html) |
| [../images/hook.gif](../images/hook.gif) | The film's opening: the badge that lied | drawn from the film's stage, captions off |

## Technical diagrams

| Diagram | What it shows | Source |
|---|---|---|
| [01-architecture](01-architecture.png) ([SVG](01-architecture.svg)) | Phone, API, engines, Bardan Intelligence and stores, as a flow | [src/01-architecture.mmd](src/01-architecture.mmd) |
| [02-protection-loop](02-protection-loop.png) ([SVG](02-protection-loop.svg)) | The nine steps from Foresee to Resolve, with escalation and disputes | [src/02-protection-loop.mmd](src/02-protection-loop.mmd) |
| [03-task-lifecycle](03-task-lifecycle.png) ([SVG](03-task-lifecycle.svg)) | The protection ledger's state machine | [src/03-task-lifecycle.mmd](src/03-task-lifecycle.mmd) |
| [04-ai-pipeline](04-ai-pipeline.png) ([SVG](04-ai-pipeline.svg)) | The AI pipeline from request to approval, with the deterministic path | [src/04-ai-pipeline.mmd](src/04-ai-pipeline.mmd) |
| [05-worker-report](05-worker-report.png) ([SVG](05-worker-report.svg)) | Sequence: an Arabic voice report, from the phone to the water task | [src/05-worker-report.mmd](src/05-worker-report.mmd) |
| [06-dispute-story](06-dispute-story.png) ([SVG](06-dispute-story.svg)) | Sequence: a false "done", the worker's dispute and the independent check | [src/06-dispute-story.mmd](src/06-dispute-story.mmd) |
| [07-emergency-offline](07-emergency-offline.png) ([SVG](07-emergency-offline.svg)) | The emergency card and its honest states, with and without a network | [src/07-emergency-offline.mmd](src/07-emergency-offline.mmd) |
| [08-privacy](08-privacy.png) ([SVG](08-privacy.svg)) | Roles against stores: what each role may reach | [src/08-privacy.mmd](src/08-privacy.mmd) |
| [09-deployment](09-deployment.png) ([SVG](09-deployment.svg)) | GitHub to Cloud Build to Cloud Run, with secrets and the optional AI | [src/09-deployment.mmd](src/09-deployment.mmd) |
| [10-evidence](10-evidence.png) ([SVG](10-evidence.svg)) | What is checked by code, what is measured, and what is not claimed yet | [src/10-evidence.mmd](src/10-evidence.mmd) |

## Redrawing them

```bash
# Technical diagrams (needs the Mermaid CLI: npm i -g @mermaid-js/mermaid-cli)
docs/diagrams/render.sh

# Hand-laid diagrams (needs Python with Playwright and Chromium, and `make setup` for the icons)
pip install playwright imagequant && playwright install chromium
python3 docs/diagrams/custom/build.py                  # all of them
python3 docs/diagrams/custom/build.py hero proof       # or just some
```

`custom/build.py` copies the [Lucide](https://lucide.dev) icons into each page, renders it at twice its size, warns about
any label that spills outside its frame, and shrinks the PNG with `imagequant` when it is installed. Shared styles are
in `custom/style.css`; the screenshot collages also use `custom/_screens.css` and the images in `docs/images/screens`.
