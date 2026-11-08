"""Compile: draft policy-pack rules from a heat code, for two people to approve (§14.5, B.13, C.7; T84-T87).

Pipeline: parse clauses -> draft rules (model, or the deterministic template
parser) -> every rule must carry a quote found VERBATIM in the source ->
schema validation -> garbled tables flagged "needs human" -> generated boundary
tests -> diff against the current pack -> two-person approval -> signed demo
release. Nothing activates automatically, and jurisdictions are never merged.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

import jsonschema

from .gemini import CLIENT, AIUnavailable

DOC = Path(__file__).resolve().parents[1] / "data" / "documents" / "sharjah_demo_excerpt.txt"
PROMPT_VERSION = "compiler-prompt@1.1"
RULE_SCHEMA = {
    "type": "object",
    "properties": {"rules": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "clause": {"type": "string"},
            "when": {"type": "object", "properties": {
                "twl_wm2": {"type": "object", "properties": {"lt": {"type": "number"}, "gte": {"type": "number"},
                                                             "lte": {"type": "number"}, "gt": {"type": "number"}}}},
                "required": ["twl_wm2"]},
            "require": {"type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string"}, "value": {"type": ["number", "boolean", "string"]},
                "unit": {"type": "string"}}, "required": ["name", "value"]}},
            "quote": {"type": "string"},
        },
        "required": ["id", "clause", "when", "require", "quote"]}}},
    "required": ["rules"],
}
APPROVER_ROLES = {"hse", "clinician"}


def source_text() -> str:
    return DOC.read_text(encoding="utf-8")


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def clauses(text: str) -> list[dict[str, str]]:
    out = []
    for m in re.finditer(r"Clause (\d+\.\d+)\.\s*(.+?)(?=\n\s*\n|\Z)", text, re.S):
        out.append({"clause": m.group(1), "text": _norm_ws(m.group(2))})
    return out


def garbled_lines(text: str) -> list[dict[str, Any]]:
    """Table rows with broken words (many short fragments) are flagged, never compiled (T84)."""
    flags = []
    for i, line in enumerate(text.splitlines(), 1):
        if "|" not in line:
            continue
        words = re.findall(r"[A-Za-z]+", line)
        frags = [w for w in words if len(w) <= 3 and w.lower() not in {"twl", "and", "the", "of", "per", "kg", "ok"}]
        if words and len(frags) / len(words) > 0.3:
            flags.append({"line": i, "text": line.strip(), "flag": "table_extraction_garbled",
                          "action": "needs_human: read the official PDF; no rule drafted from these cells"})
    return flags


def template_parse(cls: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Deterministic fallback parser for the clause patterns used in the demonstration excerpt."""
    rules = []
    for c in cls:
        t = c["text"]
        when = None
        m = re.search(r"below (\d+) W/m2", t)
        if m:
            when = {"lt": float(m.group(1))}
        m = re.search(r"from (\d+) to (\d+) W/m2", t)
        if m:
            when = {"gte": float(m.group(1)), "lt": float(m.group(2))}
        m = re.search(r"above (\d+) W/m2", t)
        if m:
            when = {"gt": float(m.group(1))}
        if not when:
            continue
        req = []
        m = re.search(r"rehydrate at ([\d.]+) litres? per hour", t)
        if m:
            req.append({"name": "rehydration_per_hour_l", "value": float(m.group(1)), "unit": "L/h"})
        if "no employee shall work alone" in t or "shall not work alone" in t:
            req.append({"name": "no_lone_work", "value": True})
        if "shade and ventilation" in t:
            req.append({"name": "shade_and_ventilation", "value": True})
        if "ordinary work shall not continue" in t:
            req.append({"name": "essential_work_only", "value": True})
        if "no thermal stress limits" in t:
            req.append({"name": "no_thermal_stress_limits", "value": True})
        rules.append({"id": f"shj_twl_{c['clause'].replace('.', '_')}", "clause": c["clause"],
                      "when": {"twl_wm2": when}, "require": req, "quote": t})
    return rules


def boundary_tests(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tests = []
    for r in rules:
        w = r["when"]["twl_wm2"]
        edges = sorted({v for v in w.values()})
        for e in edges:
            for v in (e - 1, e, e + 1):
                tests.append({"rule": r["id"], "twl_wm2": v, "expect_applies": _applies(w, v)})
    return tests


def _applies(w: dict[str, float], v: float) -> bool:
    if "lt" in w and not v < w["lt"]:
        return False
    if "lte" in w and not v <= w["lte"]:
        return False
    if "gt" in w and not v > w["gt"]:
        return False
    if "gte" in w and not v >= w["gte"]:
        return False
    return True


def compile_document(ai_on: bool) -> dict[str, Any]:
    t0 = time.perf_counter()
    text = source_text()
    cls = clauses(text)
    flags = garbled_lines(text)
    method = "template_parser"
    rules: list[dict[str, Any]] = []
    run: dict[str, Any] = {"capability": "policy_compiler", "prompt_version": PROMPT_VERSION, "steps": []}
    if ai_on:
        try:
            o = CLIENT.generate_json(
                tier="reasoning",
                system=("Draft machine-readable heat-policy rules from official clause text. One rule per TWL zone "
                        "clause. 'when' uses twl_wm2 with lt/lte/gt/gte exactly as worded ('below 115' is lt 115, "
                        "'from 115 to 140' is gte 115 and lt 140, 'above 220' is gt 220). 'require' lists "
                        "obligations with values from the text only. 'quote' MUST be copied verbatim from the "
                        "clause. Do not use table rows. Do not invent values. JSON only."),
                user="Clauses:\n" + "\n".join(f"Clause {c['clause']}. {c['text']}" for c in cls),
                schema=RULE_SCHEMA, temperature=0.0, max_tokens=1400, timeout_s=20.0)
            rules = o["data"].get("rules", [])
            method = "ai_draft"
            run["steps"].append({"step": "draft", "latency_ms": o["latency_ms"], "rules": len(rules)})
        except AIUnavailable as exc:
            run["steps"].append({"step": "draft", "note": f"AI unavailable ({exc}); template parser used"})
    if not rules:
        rules = template_parse(cls)
    # Verbatim quote check (T85) and schema validation.
    norm_src = _norm_ws(text)
    checked = []
    for r in rules:
        q = _norm_ws(r.get("quote", ""))
        quote_ok = bool(q) and q in norm_src
        try:
            jsonschema.validate({"rules": [r]}, RULE_SCHEMA)
            schema_ok = True
        except jsonschema.ValidationError:
            schema_ok = False
        status = "draft" if (quote_ok and schema_ok) else "rejected"
        reason = None if status == "draft" else ("no verbatim quote in the source" if not quote_ok
                                                 else "schema validation failed")
        checked.append({**r, "quote_match": quote_ok, "schema_ok": schema_ok, "status": status, "reason": reason,
                        "boundary_semantics": "verify_inclusive_exclusive_against_official_table"})
    good = [r for r in checked if r["status"] == "draft"]
    tests = boundary_tests(good)
    draft = {
        "pack": "AE-SHJ-HEAT", "version": "0.0.1-draft", "jurisdiction": "AE-SH",
        "status": "draft_needs_two_approvals", "source": {"document": "OSHJ-CoP-33 Safety in Heat (demonstration "
                                                                      "excerpt)", "edition": "Version 2, July 2024",
                                                         "sha256": hashlib.sha256(text.encode()).hexdigest()[:16],
                                                         "official": False},
        "rules": checked, "flags": flags, "generated_tests": tests,
        "diff_vs_current": {"added": [r["id"] for r in good], "changed": [], "removed": []},
        "approvals": [], "activation": {"state": "blocked", "reason": "needs two qualified approvals"},
        "method": method, "quote_match_rate": round(sum(1 for r in checked if r["quote_match"]) / max(1, len(checked)), 3),
        "never_merged_with": ["AE-AD-HEAT"], "label": "Demonstration: paraphrased source, not official wording",
    }
    run["latency_ms"] = int((time.perf_counter() - t0) * 1000)
    run["gate"] = {"decision": "allowed" if good else "blocked",
                   "reasons": [{"rule": "verbatim_quote", "detail": r["id"]} for r in checked if not r["quote_match"]],
                   "checks": [{"rule": "verbatim_quote", "ok": r["quote_match"]} for r in checked]}
    return {"draft": draft, "run": run}


def approve(draft: dict[str, Any], *, actor: str, role: str, at: str, note: str = "") -> dict[str, Any]:
    if role not in APPROVER_ROLES:
        raise PermissionError("Only a qualified HSE lead or clinical lead can approve a policy pack.")
    if any(a["actor"] == actor for a in draft["approvals"]):
        raise PermissionError("The same person cannot approve twice; two different qualified people are needed.")
    if draft["flags"] and not note:
        raise ValueError("Flagged items must be resolved with a written note before approval.")
    draft["approvals"].append({"actor": actor, "role": role, "at": at, "note": note})
    if len({a["role"] for a in draft["approvals"]}) >= 2 and len(draft["approvals"]) >= 2:
        draft["status"] = "approved_pending_signature"
    return draft


def activate(draft: dict[str, Any], *, actor: str, at: str) -> dict[str, Any]:
    if len(draft["approvals"]) < 2:
        raise PermissionError("Blocked: a policy pack cannot activate without two qualified approvals (T86).")
    failing = [t for t in draft["generated_tests"] if _applies(
        next(r for r in draft["rules"] if r["id"] == t["rule"])["when"]["twl_wm2"], t["twl_wm2"]) != t["expect_applies"]]
    if failing:
        raise ValueError("Blocked: the pack's own tests fail.")
    sig = hashlib.sha256(json.dumps(draft["rules"], sort_keys=True).encode()).hexdigest()
    draft["status"] = "active_demo_sandbox"
    draft["signature"] = f"demo-signature:{sig[:24]}"
    draft["activation"] = {"state": "active_in_sandbox_only", "at": at, "by": actor,
                           "note": "Demonstration only. Applies to AE-SH sites; never merged with AE-AD-HEAT."}
    return draft
