# Bardan prototype: common commands. Python 3.12+ and Node 22+.
PY ?= .venv/bin/python
PIP ?= .venv/bin/pip

.PHONY: setup dev-api dev-web build run test report docker deploy clean

setup:            ## create the Python venv and install both apps' dependencies
	python3 -m venv .venv
	$(PIP) install -r backend/requirements-dev.txt
	cd frontend && npm ci

dev-api:          ## API on :8080 with reload (run dev-web in a second terminal)
	cd backend && ../$(PY) -m uvicorn app.main:app --reload --port 8080

dev-web:          ## web app on :5173 with hot reload; /v1 is proxied to :8080
	cd frontend && npm run dev

build:            ## production build of the web app (served by the API)
	cd frontend && npm run build

run: build        ## one process, like Cloud Run: http://127.0.0.1:8080
	cd backend && ../$(PY) -m uvicorn app.main:app --port 8080

test:             ## device engine (vitest) and server (pytest) tests
	cd frontend && npx tsc -b --noEmit && npm test
	cd backend && ../$(PY) -m pytest -q

report:           ## release test report shown in the Trust Centre (backend/reports/test_report.json)
	cd frontend && npm run -s test:report
	cd backend && ../$(PY) -m pytest --bardan-report -q -p no:cacheprovider

docker:           ## build and run the production container locally
	docker build -t bardan:local .
	docker run --rm -p 8080:8080 -e BARDAN_TOKEN_SECRET=local-dev-secret bardan:local

deploy:           ## run the release tests, then deploy to Google Cloud Run (needs PROJECT_ID; see docs/DEPLOY-CLOUD-RUN.md)
	./deploy/deploy.sh

clean:
	rm -rf frontend/dist frontend/reports backend/.pytest_cache
