"""Bardan prototype server: FastAPI API under /v1 plus the built web app (one Cloud Run container)."""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import re
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import routes_clinical, routes_drill, routes_lab, routes_ops, routes_sandbox, routes_trust, routes_worker
from .api.deps import problem
from .core.clinical import ClinicalError
from .core.drill import DrillError
from .core.ledger import LedgerError
from .core.sandbox import DrillRunning

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                    format='{"t":"%(asctime)s","lvl":"%(levelname)s","log":"%(name)s","msg":"%(message)s"}')
log = logging.getLogger("bardan")

app = FastAPI(title="Bardan API (prototype)", version="1.0.0",
              description="Heat protection that gets done. Kidney care that stays with the worker. "
                          "SYNTHETIC data only; demonstration policy packs; mock dialler.",
              docs_url="/v1/docs", openapi_url="/v1/openapi.json", redoc_url=None)
app.add_middleware(GZipMiddleware, minimum_size=800)

# Simple per-IP rate limit for the public sandbox (§32.11). In-memory; one instance by design.
_BUCKET: dict[str, list[float]] = {}
# Generous enough for a room of judges (or a drill team) behind one shared Wi-Fi address.
RATE = int(os.environ.get("BARDAN_RATE_PER_MIN", "900"))
DIST = Path(os.environ.get("BARDAN_WEB_DIST", Path(__file__).resolve().parents[2] / "frontend" / "dist"))


def _csp() -> str:
    """Content Security Policy. The one inline script (theme and language before first paint) is allowed by
    its hash, computed from the built page, so no 'unsafe-inline' is needed for scripts."""
    hashes = []
    index = DIST / "index.html"
    if index.exists():
        html = index.read_text(encoding="utf-8")
        for m in re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S):
            digest = base64.b64encode(hashlib.sha256(m.group(1).encode()).digest()).decode()
            hashes.append(f"'sha256-{digest}'")
    return ("default-src 'self'; script-src 'self' " + " ".join(hashes) + "; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; media-src 'self' blob:; "
            "worker-src 'self'; manifest-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; "
            "object-src 'none'")


CSP = _csp()


def _client_ip(request: Request) -> str:
    # Cloud Run's front end appends the connecting address last; earlier entries can be set by the client.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[-1].strip()
    return request.client.host if request.client else "?"


@app.middleware("http")
async def guard(request: Request, call_next):
    cid = request.headers.get("x-correlation-id") or uuid.uuid4().hex[:12]
    if request.url.path.startswith("/v1/"):
        ip = _client_ip(request)
        now = time.time()
        b = [t for t in _BUCKET.get(ip, []) if now - t < 60]
        if len(b) >= RATE:
            return problem(429, "Too many requests", "Slow down a little; the sandbox is shared.", "rate_limited")
        b.append(now)
        _BUCKET[ip] = b
        if len(_BUCKET) > 5000:
            _BUCKET.clear()
    t0 = time.perf_counter()
    resp = await call_next(request)
    resp.headers["x-correlation-id"] = cid
    resp.headers["x-bardan-policy"] = "AE-AD-HEAT@0.1.1-demo;AE-FED-MIDDAY@2026.1-demo"
    resp.headers["referrer-policy"] = "no-referrer"
    resp.headers["x-content-type-options"] = "nosniff"
    resp.headers["permissions-policy"] = "geolocation=(), camera=(), microphone=(self)"
    if not request.url.path.startswith("/v1/docs"):     # the interactive API docs load their own assets
        resp.headers["content-security-policy"] = CSP
    resp.headers["strict-transport-security"] = "max-age=31536000; includeSubDomains"
    resp.headers["x-frame-options"] = "DENY"
    resp.headers["cross-origin-opener-policy"] = "same-origin"
    if request.url.path.startswith("/v1/"):
        log.info("%s %s %s %dms", request.method, request.url.path, resp.status_code,
                 int((time.perf_counter() - t0) * 1000))
    return resp


@app.exception_handler(HTTPException)
async def http_exc(request: Request, exc: HTTPException):
    return problem(exc.status_code, _title(exc.status_code), str(exc.detail), f"http_{exc.status_code}",
                   request.url.path)


@app.exception_handler(LedgerError)
async def ledger_exc(request: Request, exc: LedgerError):
    return problem(exc.status, "Task rule", str(exc), exc.code, request.url.path)


@app.exception_handler(DrillError)
async def drill_exc(request: Request, exc: DrillError):
    return problem(exc.status, "Drill rule", str(exc), exc.code, request.url.path)


@app.exception_handler(DrillRunning)
async def drill_running_exc(request: Request, exc: DrillRunning):
    return problem(409, "Drill running", str(exc), "drill_running", request.url.path)


@app.exception_handler(ClinicalError)
async def clinical_exc(request: Request, exc: ClinicalError):
    return problem(exc.status, "Clinical rule", str(exc), exc.code, request.url.path)


@app.exception_handler(RequestValidationError)
async def validation_exc(request: Request, exc: RequestValidationError):
    return problem(422, "Invalid input", "; ".join(f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}"
                                                  for e in exc.errors()[:5]), "validation", request.url.path)


def _title(code: int) -> str:
    return {401: "Choose a persona", 403: "Not allowed", 404: "Not found", 409: "Conflict", 410: "Gone",
            422: "Not accepted", 429: "Slow down", 503: "Unavailable"}.get(code, "Error")


for r in (routes_sandbox.router, routes_worker.router, routes_ops.router, routes_clinical.router,
          routes_trust.router, routes_drill.router, routes_lab.router):
    app.include_router(r)

# ------------------------------------------------------------- web app
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def spa(path: str):
        if path.startswith("v1/"):
            raise HTTPException(404, "Not found")
        f = DIST / path
        if path and f.is_file():
            headers = {"cache-control": "no-cache"} if path in ("sw.js", "manifest.webmanifest") else {}
            return FileResponse(f, headers=headers)
        return FileResponse(DIST / "index.html", headers={"cache-control": "no-cache"})
else:
    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    async def root():
        return JSONResponse({"bardan": "API is running", "docs": "/v1/docs",
                             "note": "Build the web app (frontend) to serve it here."})
