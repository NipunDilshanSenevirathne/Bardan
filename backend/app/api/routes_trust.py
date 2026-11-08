"""Trust Centre routes: AI trace, agents, audit, decision replay and the proof reports (§16.14, §29)."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..ai import evaluation
from ..ai.gemini import CLIENT
from ..ai.orchestrator import public_manifests
from ..core import policy
from ..core.content import LANGUAGE_STATUS
from ..core.scenario import STAFF
from .deps import Ctx, context

router = APIRouter(prefix="/v1")
REPORTS = Path(__file__).resolve().parents[2] / "reports"
_EVAL_CACHE: dict[str, Any] = {"at": 0.0, "data": None}
_EVAL_LOCK = threading.Lock()
_AI_EVAL = {"at": 0.0}


def _strip_models(obj: Any) -> Any:
    """Defence in depth: no model identifiers ever leave through the trace (UI shows Bardan Intelligence only)."""
    if isinstance(obj, dict):
        return {k: _strip_models(v) for k, v in obj.items() if k not in ("model", "model_id", "models", "tier")}
    if isinstance(obj, list):
        return [_strip_models(v) for v in obj]
    return obj


# What a reviewer may see of another person's AI run. Anything not listed (the person's own words, transcripts,
# extracted symptoms, clinical values, worker IDs) never leaves the server for anyone but that person.
_REVIEW_KEYS = ("id", "at", "capability", "lang", "prompt_version", "method", "latency_ms", "gate", "steps",
                "output_source", "draft", "frozen_draft", "redteam", "ai_unavailable", "fallback")
_CLINICAL_CAPS = {"document_extraction", "care_summary"}
_STAFF_ROLE = {s["id"]: s["role"] for s in STAFF.values()}
_REVIEW_AUDIT_EVERY_S = 900          # one audit entry per reviewer per 15 minutes of reading (the page polls)
_last_review_audit: dict[tuple[str, str], float] = {}


def _deidentified(run: dict[str, Any]) -> dict[str, Any]:
    """The reviewer's view of someone else's run: what the AI did and what the gate decided, not who or what
    they wrote (spec §21: traces carry no health values or identities)."""
    subject = _STAFF_ROLE.get(run.get("actor", ""), "worker")
    out = {k: run[k] for k in _REVIEW_KEYS if k in run}
    out["subject"] = subject
    if subject == "worker":
        out["worker_words"] = "withheld"
        if isinstance(run.get("output"), dict) and "candidates" in run["output"]:
            out["candidates_count"] = len(run["output"]["candidates"])
    else:
        # A staff member's work question (for example an HSE copilot query) is part of the safety review.
        for k in ("question", "input_ref", "output"):
            if k in run:
                out[k] = run[k]
    if run.get("capability") in _CLINICAL_CAPS:
        for k in ("draft", "output", "input_ref"):
            out.pop(k, None)
        out["clinical_content"] = "withheld"
    if isinstance(out.get("steps"), list):
        out["steps"] = [{k: v for k, v in s.items() if k in ("step", "method", "result", "passages", "latency_ms",
                                                              "cached")} for s in out["steps"]]
    return out


@router.get("/trace")
def trace(ctx: Ctx = Depends(context)):
    """Scoped on the server: everyone sees their own runs in full; the reviewer (auditor role) sees other people's
    runs de-identified, and every review is written to the audit log; nobody else sees other people's runs."""
    sb = ctx.sb
    runs = sb.trace[-200:]
    own = [r for r in runs if r.get("actor") == ctx.actor]
    if ctx.role == "auditor":
        visible = [r if r.get("actor") == ctx.actor else _deidentified(r) for r in runs]
        scope, withheld = "review_deidentified", 0
        key = (sb.id, ctx.actor)
        if time.time() - _last_review_audit.get(key, 0.0) > _REVIEW_AUDIT_EVERY_S:
            _last_review_audit[key] = time.time()
            sb.audit.append(at=sb.now(), actor=ctx.actor, role=ctx.role, action="ai.trace_review",
                            resource=f"trace ({len(visible)} runs)", category="ai",
                            reason="de-identified safety review: identities and people's own words withheld")
    else:
        visible, scope, withheld = own, "own", len(runs) - len(own)
    return {"runs": _strip_models(visible[-60:]), "scope": scope, "withheld": withheld,
            "adapter": "Bardan Intelligence",
            "note": "Every AI output passes the policy gate before anyone sees it. Blocked drafts are kept for the "
                    "weekly safety review."}


@router.get("/agents")
def agents(ctx: Ctx = Depends(context)):
    return {"manifests": public_manifests(), "runs": ctx.sb.agent_runs[-40:]}


@router.get("/audit")
def audit(ctx: Ctx = Depends(context)):
    ctx.require("audit.read") if ctx.role != "worker" else None
    entries = ctx.sb.audit.scoped(role=ctx.role, actor=ctx.actor)
    return {"entries": entries[-200:], "total": len(entries), "verify": ctx.sb.audit.verify()}


@router.get("/audit/verify")
def audit_verify(ctx: Ctx = Depends(context)):
    return ctx.sb.audit.verify()


@router.get("/replay/{scenario}")
def replay(scenario: str):
    """Decision Replay Pack (§29.2): frozen typed inputs with expected outcomes and the server's results."""
    if scenario != "conformance":
        raise HTTPException(404, "Unknown scenario")
    with open(policy.shared_dir() / "conformance.json", encoding="utf-8") as f:
        suite = json.load(f)
    rows = []
    for c in suite["cases"]:
        got = policy.evaluate(c["input"])
        rows.append({"id": c["id"], "description": c["description"], "input": c["input"], "expected": c["expected"],
                     "server": got})
    return {"suite": suite["suite"], "version": suite["version"], "packs": suite.get("packs"),
            "engine": "python", "cases": rows,
            "versions": {"AE-AD-HEAT": policy.heat_pack()["version"], "AE-FED-MIDDAY": policy.midday_pack()["version"]}}


class CompareIn(BaseModel):
    device: str = Field(default="browser-ts-engine", max_length=60)
    results: list[dict[str, Any]] = Field(..., max_length=500)


@router.post("/replay/compare")
def replay_compare(body: CompareIn):
    """Meanings are compared, not JSON formatting: state, band and the required action set."""
    server = {r["id"]: r for r in replay("conformance")["cases"]}
    diffs, same = [], 0
    for d in body.results:
        s = server.get(d.get("id"))
        if not s:
            continue
        sv = s["server"]
        match = d.get("state") == sv["state"] and d.get("band") == sv["band"] and \
            sorted(d.get("actions", [])) == sorted(sv["actions"])
        same += match
        if not match:
            diffs.append({"id": d["id"], "device": {k: d.get(k) for k in ("state", "band", "actions")},
                          "server": {k: sv[k] for k in ("state", "band", "actions")}})
    return {"device": body.device, "compared": len(body.results), "identical": same, "differences": diffs,
            "verdict": "identical required action sets" if not diffs else "MISMATCH: fix or disable the feature"}


@router.get("/reports/evaluation")
def report_eval(refresh: bool = False):
    with _EVAL_LOCK:
        if refresh or not _EVAL_CACHE["data"] or time.time() - _EVAL_CACHE["at"] > 900:
            _EVAL_CACHE["data"] = evaluation.run_all(use_ai=False)
            _EVAL_CACHE["at"] = time.time()
    data = dict(_EVAL_CACHE["data"])
    if evaluation.LAST.get("ai"):
        data["ai_sample"] = evaluation.LAST["ai"]
    data["ai_configured"] = CLIENT.configured
    return data


@router.post("/reports/evaluation/ai")
def report_eval_ai(ctx: Ctx = Depends(context)):
    if not CLIENT.configured:
        raise HTTPException(503, "AI is not configured on this server; deterministic results are shown.")
    if time.time() - _AI_EVAL["at"] < 600:
        raise HTTPException(429, "A live AI evaluation ran in the last 10 minutes. Results are cached to protect "
                                 "the free-tier quota.")
    _AI_EVAL["at"] = time.time()
    return evaluation.run_ai_bounded(limit=8)


@router.get("/reports/tests")
def report_tests():
    p = REPORTS / "test_report.json"
    if not p.exists():
        return {"available": False, "note": "Run `make test` (pytest) to produce the release test report."}
    return {"available": True, **json.loads(p.read_text())}


@router.get("/reports/load")
def report_load():
    """Measured load tests (scripts/load_test.py), as recorded. Nothing here is extrapolated."""
    out = {}
    for name in ("panel20", "burst100"):
        p = REPORTS / f"load_test_{name}.json"
        if p.exists():
            out[name] = json.loads(p.read_text())
    return {"available": bool(out), **out}


@router.get("/reports/licences")
def licences():
    p = REPORTS / "licences.json"
    return json.loads(p.read_text()) if p.exists() else {"items": []}


@router.get("/reports/language")
def language():
    return {"languages": LANGUAGE_STATUS, "policy": "Draft -> Reviewed -> Released (§26.2). English and Arabic "
            "only in this prototype; nothing is 'released' before teach-back testing in the pilot."}
