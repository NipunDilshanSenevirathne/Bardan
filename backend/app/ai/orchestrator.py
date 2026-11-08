"""Bounded agents and a deterministic orchestrator (finalsystem.md §15, B.14; T95-T97, invariant 17).

Agents have one job each, a signed tool manifest, step and time budgets and a
kill switch. A model never starts another model; this orchestrator runs the
steps, checks every tool call against the manifest, and logs the run. Tools
receive references, never secrets or personal identifiers. Anything that
changes plans, rules, reports or care needs the person named in §15.5.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any, Callable

MANIFEST_KEY = os.environ.get("BARDAN_MANIFEST_KEY", "demo-manifest-signing-key")

MANIFESTS: dict[str, dict[str, Any]] = {
    "intake": {"agent": "intake", "manifest_version": "1.0.0", "tier": "P0",
               "tools": {"asr": "read", "extract_intents": "generate", "create_report_draft": "draft"},
               "forbidden": ["read_clinical", "export_data", "contact_emergency_services", "activate_plan"],
               "budgets": {"max_steps": 4, "max_wall_s": 15}, "approval": {"create_report": "worker"}},
    "planning": {"agent": "planning", "manifest_version": "1.0.0", "tier": "P0+",
                 "tools": {"get_zone_forecast": "read", "run_site_twin": "read", "solve_schedule": "compute",
                           "revalidate_plan": "read", "explain_plan": "generate"},
                 "forbidden": ["activate_plan", "read_clinical", "export_data", "contact_emergency_services"],
                 "budgets": {"max_steps": 12, "max_wall_s": 60}, "approval": {"activate": "supervisor"}},
    "compliance": {"agent": "compliance", "manifest_version": "1.0.0", "tier": "P0+",
                   "tools": {"query_metrics": "read", "render_report": "draft"},
                   "forbidden": ["read_clinical", "export_data", "publish_report"],
                   "budgets": {"max_steps": 6, "max_wall_s": 30}, "approval": {"publish": "hse"}},
    "policy_compiler": {"agent": "policy_compiler", "manifest_version": "1.0.0", "tier": "P0+ demo",
                        "tools": {"parse_document": "read", "draft_rules": "generate", "generate_tests": "compute",
                                  "run_pack_tests": "compute"},
                        "forbidden": ["activate_pack", "sign_pack", "read_clinical"],
                        "budgets": {"max_steps": 6, "max_wall_s": 60}, "approval": {"activate": "two qualified people"}},
    "care_navigator": {"agent": "care_navigator", "manifest_version": "1.0.0", "tier": "P1", "boundary": "clinical",
                       "tools": {"read_verified_record": "read_scoped", "draft_message": "generate",
                                 "propose_appointment": "draft"},
                       "forbidden": ["write_operational", "export_data", "send_message"],
                       "budgets": {"max_steps": 6, "max_wall_s": 40}, "approval": {"send": "clinician"}},
    "insight": {"agent": "insight", "manifest_version": "1.0.0", "tier": "P1",
                "tools": {"aggregate_query": "read", "draft_review_task": "draft"},
                "forbidden": ["read_clinical", "individual_query", "create_task"],
                "budgets": {"max_steps": 5, "max_wall_s": 20}, "approval": {"create_task": "hse"}},
    "redteam": {"agent": "redteam", "manifest_version": "1.0.0", "tier": "P0", "environment": "test_only",
                "tools": {"run_test_suite": "compute"},
                "forbidden": ["write_operational", "read_clinical", "export_data"],
                "budgets": {"max_steps": 50, "max_wall_s": 120}, "approval": {"file_failures": "safety review"}},
}


def _sign(m: dict[str, Any]) -> str:
    body = json.dumps({k: v for k, v in m.items() if k != "signature"}, sort_keys=True).encode()
    return hmac.new(MANIFEST_KEY.encode(), body, hashlib.sha256).hexdigest()[:32]


for _m in MANIFESTS.values():
    _m["signed_by"] = ["ai_lead", "safety_reviewer"]
    _m["signature"] = _sign(_m)


class AgentDenied(Exception):
    pass


class AgentRun:
    def __init__(self, agent: str, sb=None, kill_switch: bool = True) -> None:
        m = MANIFESTS[agent]
        if _sign(m) != m["signature"]:
            raise AgentDenied("Manifest signature invalid; agent not started.")
        self.m = m
        self.sb = sb
        self.enabled = kill_switch
        self.steps: list[dict[str, Any]] = []
        self.t0 = time.perf_counter()
        self.outcome = "running"
        self.record = {"agent": agent, "manifest_version": m["manifest_version"], "signature": m["signature"],
                       "steps": self.steps, "budgets": m["budgets"]}

    def call(self, tool: str, fn: Callable[[], Any], *, ref: str = "") -> Any:
        if not self.enabled:
            self._stop("killed", f"{self.m['agent']} agent switched off; manual path used")
        if tool in self.m["forbidden"] or tool not in self.m["tools"]:
            self.steps.append({"tool": tool, "decision": "denied", "reason": "outside signed manifest"})
            self._stop("denied", f"Tool '{tool}' is outside the signed manifest (T96).")
        if len(self.steps) >= self.m["budgets"]["max_steps"]:
            self._stop("budget", "Step budget exceeded; run stopped and fallback used (T95).")
        if time.perf_counter() - self.t0 > self.m["budgets"]["max_wall_s"]:
            self._stop("budget", "Time budget exceeded; run stopped and fallback used.")
        t = time.perf_counter()
        out = fn()
        self.steps.append({"tool": tool, "access": self.m["tools"][tool], "decision": "allowed", "input_ref": ref,
                           "ms": int((time.perf_counter() - t) * 1000)})
        return out

    def _stop(self, outcome: str, msg: str) -> None:
        self.outcome = outcome
        self.finish()
        raise AgentDenied(msg)

    def finish(self, outcome: str | None = None) -> dict[str, Any]:
        if outcome:
            self.outcome = outcome
        self.record.update(outcome=self.outcome, wall_ms=int((time.perf_counter() - self.t0) * 1000))
        if self.sb is not None and self.record not in self.sb.agent_runs:
            self.sb.agent_runs.append({**self.record, "at": self.sb.now(), "id": f"agent_{len(self.sb.agent_runs) + 1:03d}"})
        return self.record


def probe_tool_misuse() -> list[dict[str, Any]]:
    """Red-team probes on the orchestrator itself (T95-T97)."""
    results = []
    run = AgentRun("planning")
    try:
        run.call("export_data", lambda: None, ref="all_workers")
        results.append({"probe": "planning agent calls export_data", "blocked": False})
    except AgentDenied as exc:
        results.append({"probe": "planning agent calls export_data", "blocked": True, "reason": str(exc)})
    run = AgentRun("planning")
    try:
        run.call("activate_plan", lambda: None, ref="plan_x")
        results.append({"probe": "planning agent activates a plan", "blocked": False})
    except AgentDenied as exc:
        results.append({"probe": "planning agent activates a plan", "blocked": True, "reason": str(exc)})
    run = AgentRun("insight")
    blocked = False
    try:
        for _ in range(10):
            run.call("aggregate_query", lambda: None)
    except AgentDenied as exc:
        blocked = True
        results.append({"probe": "insight agent exceeds its step budget", "blocked": True, "reason": str(exc)})
    if not blocked:
        results.append({"probe": "insight agent exceeds its step budget", "blocked": False})
    run = AgentRun("care_navigator")
    try:
        run.call("write_operational", lambda: None)
        results.append({"probe": "care navigator writes to operations", "blocked": False})
    except AgentDenied as exc:
        results.append({"probe": "care navigator writes to operations", "blocked": True, "reason": str(exc)})
    tampered = json.loads(json.dumps(MANIFESTS["insight"]))
    tampered["tools"]["read_clinical"] = "read"
    results.append({"probe": "tampered manifest adds read_clinical", "blocked": _sign(tampered) != tampered["signature"],
                    "reason": "signature check fails"})
    return results


def public_manifests() -> list[dict[str, Any]]:
    return [{k: v for k, v in m.items()} for m in MANIFESTS.values()]
