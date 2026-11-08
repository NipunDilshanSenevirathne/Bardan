#!/usr/bin/env bash
# Deploy Bardan to Google Cloud Run from source (Cloud Build builds the Dockerfile).
#
#   PROJECT_ID=my-project ./deploy/deploy.sh                 # first deploy and updates
#   PROJECT_ID=my-project REGION=me-central1 ./deploy/deploy.sh
#
# Optional, once:  printf '%s' "$GEMINI_KEY" | gcloud secrets create gemini-api-key --data-file=-
# Without that secret the app runs with AI off: every answer comes from approved templates and the
# deterministic engines, which is a supported mode, not an error.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID to your Google Cloud project ID}"
REGION="${REGION:-europe-west1}"        # Tier 1 price region; me-central1 (Doha) is closer but Tier 2
SERVICE="${SERVICE:-bardan}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Project ${PROJECT_ID}, region ${REGION}, service ${SERVICE}"
gcloud config set project "${PROJECT_ID}" >/dev/null

echo "==> Enabling the APIs Cloud Run needs (idempotent)"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com >/dev/null

PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "==> Letting Cloud Build build the container (Cloud Run Builder role for the default build account)"
# Source deploys build with the Compute Engine default service account; new projects may not grant it this role.
gcloud projects add-iam-policy-binding "${PROJECT_ID}" --member="serviceAccount:${RUNTIME_SA}" \
  --role=roles/run.builder --condition=None >/dev/null

echo "==> Token-signing secret (created once, kept stable so capability tokens survive restarts)"
if ! gcloud secrets describe bardan-token-secret >/dev/null 2>&1; then
  python3 -c 'import secrets; print(secrets.token_hex(32), end="")' | \
    gcloud secrets create bardan-token-secret --replication-policy=automatic --data-file=- >/dev/null
fi
gcloud secrets add-iam-policy-binding bardan-token-secret --member="serviceAccount:${RUNTIME_SA}" \
  --role=roles/secretmanager.secretAccessor >/dev/null

echo "==> Manifest-signing secret for the AI agents' tool manifests (created once)"
if ! gcloud secrets describe bardan-manifest-key >/dev/null 2>&1; then
  python3 -c 'import secrets; print(secrets.token_hex(32), end="")' | \
    gcloud secrets create bardan-manifest-key --replication-policy=automatic --data-file=- >/dev/null
fi
gcloud secrets add-iam-policy-binding bardan-manifest-key --member="serviceAccount:${RUNTIME_SA}" \
  --role=roles/secretmanager.secretAccessor >/dev/null

SECRETS="BARDAN_TOKEN_SECRET=bardan-token-secret:latest,BARDAN_MANIFEST_KEY=bardan-manifest-key:latest"
if gcloud secrets describe gemini-api-key >/dev/null 2>&1; then
  gcloud secrets add-iam-policy-binding gemini-api-key --member="serviceAccount:${RUNTIME_SA}" \
    --role=roles/secretmanager.secretAccessor >/dev/null
  SECRETS="${SECRETS},GEMINI_API_KEY=gemini-api-key:latest"
  echo "==> Gemini key found in Secret Manager: Bardan Intelligence is on"
else
  echo "==> No gemini-api-key secret: deploying with AI off (templates and deterministic engines)"
fi

echo "==> Release tests (the Trust Centre shows this report)"
# Both test suites run when the local toolchain is installed (make setup); a failing test stops the deploy.
# Without it (or with SKIP_TESTS=1) the report bundled in backend/reports/ is deployed as it is.
if [ -x "${ROOT}/.venv/bin/python" ]; then PY="${ROOT}/.venv/bin/python"; else PY=python3; fi
if [ "${SKIP_TESTS:-0}" != "1" ] && [ -d "${ROOT}/frontend/node_modules" ] \
   && "${PY}" -c 'import pytest, fastapi, ortools' >/dev/null 2>&1; then
  (cd "${ROOT}/frontend" && npm run -s test:report)
  (cd "${ROOT}/backend" && "${PY}" -m pytest --bardan-report -q -p no:cacheprovider)
else
  echo "   Skipped here (run 'make setup' to run them); deploying the bundled report in backend/reports/"
fi

echo "==> Building and deploying (Cloud Build + Cloud Run)"
gcloud run deploy "${SERVICE}" \
  --quiet \
  --source "${ROOT}" \
  --region "${REGION}" \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 1 \
  --concurrency 80 \
  --cpu 1 \
  --memory 1Gi \
  --timeout 60 \
  --cpu-throttling \
  --session-affinity \
  --set-env-vars "BARDAN_DATA_CLASS=synthetic,BARDAN_AI_TIER=free,BARDAN_RATE_PER_MIN=900,LOG_LEVEL=INFO" \
  --set-secrets "${SECRETS}" \
  --labels "app=bardan,data=synthetic"

URL="$(gcloud run services describe "${SERVICE}" --region "${REGION}" --format='value(status.url)')"
echo "==> Deployed: ${URL}"
echo "    Health: $(curl -s "${URL}/v1/health" || echo 'not reachable yet')"
