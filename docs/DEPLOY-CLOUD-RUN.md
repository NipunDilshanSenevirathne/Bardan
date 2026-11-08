# Deploying Bardan on Google Cloud Run

One container serves the API (`/v1`) and the web app. It runs on Cloud Run's request-based billing with one
instance at most and scales to zero when idle, so judging traffic stays inside the monthly free allowance.

**Checked on 8 November 2026:** this `Dockerfile` was built and run locally with a free-tier Gemini key, and every
AI feature was rehearsed in a browser against the running container in English and Arabic (`e2e/ai_live.py`),
along with the guided tour, a phone losing its network and the drill console. All passed.

**Quick path** (nothing to install: everything runs in Cloud Shell, the terminal inside the Google Cloud console)

1. Create a Google Cloud project, link billing, and set a budget alert (section 6).
2. Open **Cloud Shell**, upload `bardan-prototype.zip` (⋮ → Upload), then `unzip -q bardan-prototype.zip && cd bardan`.
3. Store the Gemini key as a secret (section 2). Keys from Google AI Studio work in either format (`AIza…` or
   `AQ.…`); the app sends the key in the `x-goog-api-key` header.
4. Run `PROJECT_ID=your-project-id bash deploy/deploy.sh` (section 3) and open the URL it prints.
5. Check it: `curl $URL/v1/health` should show `"ai_configured": true`; then take the guided tour.

## What it uses, and the free allowances

| Service | Used for | Free allowance (per billing account, per month) |
|---|---|---|
| Cloud Run (request-based) | The app | 180,000 vCPU-seconds, 360,000 GiB-seconds, 2 million requests |
| Cloud Build | Building the image | 2,500 build-minutes on the default `e2-standard-2` pool |
| Secret Manager | Gemini key and token secret | 6 active secret versions, 10,000 access operations |
| Artifact Registry | Stores the image | A small free storage allowance; one image of about 135 MB compressed |
| Gemini API (AI Studio) | Bardan Intelligence (optional) | Free-tier quotas, see `docs/AI-MODELS.md` |

Cloud Run's free tier is applied as a discount at Tier 1 prices, wherever the service runs. A Tier 1 region
such as `europe-west1` (Belgium) stretches it furthest; `me-central1` (Doha) is closest to the UAE but is a
Tier 2 region, so the same allowance covers less usage. A billing account must be linked to the project even
when usage stays within the free tier. Prices and allowances change: check the pricing pages before
deploying, and **set a budget alert** (step 6).

## 1. Prerequisites

* A Google Cloud project with billing linked, and the `gcloud` CLI signed in (`gcloud auth login`).
* Optional: a Gemini API key from Google AI Studio. Without it the app runs with AI off (approved templates
  and deterministic engines), which is a supported mode.

## 2. Store the secrets (once)

```bash
export PROJECT_ID=your-project-id
gcloud config set project $PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com

# Token-signing secret: keeps capability tokens valid across restarts.
python3 -c 'import secrets; print(secrets.token_hex(32), end="")' | \
  gcloud secrets create bardan-token-secret --replication-policy=automatic --data-file=-

# Optional: the Gemini key (never put it in code, images or environment files).
printf '%s' "PASTE_THE_KEY" | gcloud secrets create gemini-api-key --replication-policy=automatic --data-file=-

# Later, to replace the key (for example after it was shared): add a version, then redeploy.
printf '%s' "NEW_KEY" | gcloud secrets versions add gemini-api-key --data-file=-
```

The Cloud Run runtime service account (by default `PROJECT_NUMBER-compute@developer.gserviceaccount.com`)
needs `roles/secretmanager.secretAccessor` on both secrets; `deploy/deploy.sh` grants it.

## 3. Deploy with one command

```bash
PROJECT_ID=your-project-id ./deploy/deploy.sh            # region defaults to europe-west1
PROJECT_ID=your-project-id REGION=me-central1 ./deploy/deploy.sh
```

The script enables the APIs, gives the default build account the Cloud Run Builder role that source deploys
need in new projects, creates the token and manifest-signing secrets if missing, runs the release tests when the local
toolchain is installed (`make setup`; a failing test stops the deploy), then runs `gcloud run deploy --source .`.
Without the toolchain, or with `SKIP_TESTS=1`, it deploys the release report already in `backend/reports/`
(the Trust Centre shows it). Cloud Build builds the `Dockerfile` (Node builds the web app; a slim Python image
runs it as a non-root user) and Cloud Run serves it with:

| Setting | Value | Why |
|---|---|---|
| `--max-instances` | 1 | Judge sandboxes live in memory; every request must reach the same instance. |
| `--min-instances` | 0 | Scale to zero when idle (free). A cold start resets sandboxes, which the app tells the user. |
| `--session-affinity` | on | Keeps a browser on the same instance. |
| `--cpu-throttling` | on | Request-based billing: CPU is only billed while serving. |
| `--memory` / `--cpu` | 1 GiB / 1 | Enough for the CP-SAT planner at 200 workers. |
| `--concurrency` | 80 | One instance handles a judging panel comfortably. |
| `--timeout` | 60 s | The slowest call (live AI evaluation) stays well under it. |
| Env | `BARDAN_DATA_CLASS=synthetic`, `BARDAN_AI_TIER=free` | The governance switch: real data never goes to a free-tier model. |
| Secrets | `BARDAN_TOKEN_SECRET`, `BARDAN_MANIFEST_KEY`, `GEMINI_API_KEY` | From Secret Manager, not the image. |

The command prints the service URL. Check it with `curl $URL/v1/health`.

## 4. Continuous delivery (optional)

`deploy/cloudbuild.yaml` runs the device-engine tests, the server tests, builds and pushes the image to
Artifact Registry and deploys it. A failing test stops the pipeline before anything is deployed. Run
`deploy/deploy.sh` once first: it creates the token secret and gives the runtime account access to it.

```bash
gcloud artifacts repositories create bardan --repository-format=docker --location=europe-west1   # once
gcloud builds submit --config deploy/cloudbuild.yaml --substitutions=_REGION=europe-west1 .
```

The Cloud Build service account needs `roles/run.admin` and `roles/iam.serviceAccountUser` to deploy, and
`roles/secretmanager.viewer` to see the optional Gemini secret (without it the pipeline deploys with AI off).
The pipeline leaves the build machine type at the default `e2-standard-2`, the only one the free
build-minutes cover.

## 5. Run the same container locally

```bash
docker build -t bardan:local .
docker run --rm -p 8080:8080 -e BARDAN_TOKEN_SECRET=local-dev-secret bardan:local
# optional AI: add  -e GEMINI_API_KEY=...
```

Open http://localhost:8080. For development without Docker see the README (`make setup`, `make run`).

## 6. Keep it free: guardrails

* **Budget alert:** Billing → Budgets & alerts → create a budget (for example 5 USD) with e-mail alerts at
  50 %, 90 % and 100 %.
* **One instance** (`--max-instances 1`) caps the worst case; the app also rate-limits each client address
  (900 requests per minute by default, `BARDAN_RATE_PER_MIN`: generous enough for a room of judges, or a drill
  team, sharing one Wi-Fi address; see docs/LOAD-TEST.md for measured capacity).
* **AI quota:** the adapter respects the per-model limits, caches repeated requests and limits the live AI
  evaluation to once every 10 minutes. On the free tier that is about 1,000 fast requests a day, about 40 for lab
  reports, care summaries and the rule compiler, and about 40 read-aloud sentences (see docs/AI-MODELS.md). When a
  quota runs out, the next model or the approved templates take over; nothing breaks. Keep one instance: the
  adapter counts quota in memory, and a daily quota found used up after a restart parks that model until the
  reset (midnight Pacific time).
* **Logs:** structured JSON lines; no request bodies, tokens or health data are logged.

## 7. Configuration reference

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | 8080 | Set by Cloud Run. |
| `GEMINI_API_KEY` | empty | Turns Bardan Intelligence on. Empty means AI off. |
| `BARDAN_TOKEN_SECRET` | random per process | HMAC key for capability tokens. Set it so tokens survive restarts. |
| `BARDAN_DATA_CLASS` | `synthetic` | Anything else blocks free-tier AI calls (T53). |
| `BARDAN_AI_TIER` | `free` | Set to `paid` only with a no-training tier and a data processing agreement. |
| `BARDAN_RATE_PER_MIN` | 900 | Per-address request limit for the shared sandbox (people behind one Wi-Fi share an address). |
| `BARDAN_MANIFEST_KEY` | demo key | Signs agent tool manifests; `deploy/deploy.sh` stores one in Secret Manager. |
| `BARDAN_CLINICAL_KEY` | random per process | Key for clinical pseudonyms (kept apart from operational IDs). |
| `BARDAN_WEB_DIST`, `BARDAN_SHARED_DIR` | set in the image | Where the built web app and the policy packs live. |
| `LOG_LEVEL` | `INFO` | Python logging level. |

## 8. If something goes wrong

| What you see | What to do |
|---|---|
| `PERMISSION_DENIED` while building | A new role can take two minutes to apply. Wait, then run `bash deploy/deploy.sh` again (it is safe to repeat). |
| `Billing account ... not found` or `billing is disabled` | Billing → My projects → link the billing account to this project, then run the script again. |
| `/v1/health` shows `"ai_configured": false` | The secret must be named exactly `gemini-api-key`. Create it (section 2), then run the script again. |
| AI answers come from templates during the day | A free-tier daily quota was used up. Nothing is broken; it resets at midnight Pacific time. |
| A new Gemini key | `read -rsp "Key: " K && printf '%s' "$K" \| gcloud secrets versions add gemini-api-key --data-file=- && unset K`, then run the script again. |
| Remove everything | `gcloud run services delete bardan --region europe-west1`, then delete the secrets and the `cloud-run-source-deploy` repository in Artifact Registry. |

Sources: [Cloud Run pricing](https://cloud.google.com/run/pricing), [Cloud Build pricing](https://cloud.google.com/build/pricing),
[Secret Manager pricing](https://cloud.google.com/secret-manager/pricing).
