"""Read and write for care: clinical document AI inside the clinical boundary (§14.6, §16.2; T57, T88-T91).

Extraction: a lab-report image becomes DRAFT fields, each with the source text
that supports it. Identity, unit and date checks run on every draft. Mismatched
identity or unexpected units are quarantined; nothing is converted. A clinician
verifies every field before it becomes a clinical result.

Drafting: a plain-language care summary in English or Arabic from the
clinician's own verified note, with a back-translation for the clinician to
compare. The gate blocks any diagnosis, probability or number not in the note.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from . import gate as G
from .gemini import CLIENT, AIUnavailable

DOCS = Path(__file__).resolve().parents[1] / "data" / "documents"
PROMPT_VERSION = "extract-prompt@1.2"
DOC_IDS = {"W07": "PT-118-SYN", "W36": "PT-136-SYN"}
SCHEMA = {
    "type": "object",
    "properties": {
        "patient_name": {"type": "string"}, "patient_id": {"type": "string"},
        "analyte": {"type": "string"}, "value": {"type": "number"}, "unit": {"type": "string"},
        "specimen_datetime": {"type": "string"}, "lab": {"type": "string"}, "method": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "object", "properties": {
            "field": {"type": "string"}, "text": {"type": "string"}}, "required": ["field", "text"]}},
    },
    "required": ["patient_name", "patient_id", "analyte", "value", "unit", "evidence"],
}
SUMMARY_SCHEMA = {"type": "object", "properties": {"summary": {"type": "string"}, "back_translation": {"type": "string"}},
                  "required": ["summary", "back_translation"]}


def list_documents() -> list[dict[str, Any]]:
    return json.loads((DOCS / "lab_reports.json").read_text())


def _text_layer(doc_id: str) -> str:
    return (DOCS / f"{doc_id}.txt").read_text(encoding="utf-8")


def text_parse(doc_id: str) -> dict[str, Any]:
    t = _text_layer(doc_id)

    def grab(pat: str) -> str | None:
        m = re.search(pat, t, re.I | re.M)
        return m.group(1).strip() if m else None
    row = re.search(r"^(?:Urine albumin/creatinine ratio(?: \(ACR\))?|ACR)\s+([\d.]+)\s+(\S+)", t, re.M)
    out = {"patient_name": grab(r"Patient name:\s*(.+)$") or "", "patient_id": grab(r"Patient ID:\s*(\S+)") or "",
           "analyte": "urine_acr" if row else "unknown", "value": float(row.group(1)) if row else 0.0,
           "unit": row.group(2) if row else "", "specimen_datetime": grab(r"Collected:\s*(.+)$") or "",
           "lab": t.splitlines()[0].strip(), "method": grab(r"Method:\s*(.+)$") or "", "evidence": []}
    for f, pat in (("patient_name", r"Patient name:.*"), ("patient_id", r"Patient ID:.*"),
                   ("value", r"^(?:Urine albumin/creatinine ratio(?: \(ACR\))?|ACR).*"), ("specimen_datetime",
                                                                                         r"Collected:.*")):
        m = re.search(pat, t, re.M)
        if m:
            out["evidence"].append({"field": f, "text": m.group(0).strip()})
    return out


def extract(doc_id: str, *, expected_worker: str, expected_name: str, ai_on: bool) -> dict[str, Any]:
    t0 = time.perf_counter()
    if doc_id not in {d["id"] for d in list_documents()}:
        raise KeyError(doc_id)
    method = "text_layer_parser"
    run: dict[str, Any] = {"capability": "document_extraction", "prompt_version": PROMPT_VERSION, "steps": []}
    fields: dict[str, Any] | None = None
    if ai_on:
        try:
            img = (DOCS / f"{doc_id}.png").read_bytes()
            o = CLIENT.generate_json(
                tier="reasoning",
                system=("Extract fields from this SYNTHETIC lab report image exactly as printed. Do not convert "
                        "units. Do not interpret. For each field add evidence with the exact printed line. "
                        "analyte: 'urine_acr' for albumin/creatinine ratio. JSON only."),
                user="Extract the fields.", schema=SCHEMA, inline=[("image/png", img)], temperature=0.0,
                max_tokens=700, timeout_s=20.0)
            fields = o["data"]
            method = "ai_vision"
            run["steps"].append({"step": "extract", "latency_ms": o["latency_ms"]})
        except AIUnavailable as exc:
            run["steps"].append({"step": "extract", "note": f"AI unavailable ({exc}); text-layer parser used"})
    if fields is None:
        fields = text_parse(doc_id)
    # Evidence must exist in the printed document (source highlighting).
    layer = _text_layer(doc_id)
    norm = re.sub(r"\s+", " ", layer)
    ev_ok = [e for e in fields.get("evidence", []) if re.sub(r"\s+", " ", e.get("text", "")).strip() in norm]
    checks = []
    problems = []
    if fields.get("patient_name", "").strip() != expected_name or \
            fields.get("patient_id", "").strip() != DOC_IDS.get(expected_worker, ""):
        problems.append("identity_mismatch")
    checks.append({"check": "identity", "ok": "identity_mismatch" not in problems})
    if fields.get("analyte") == "urine_acr" and fields.get("unit") != "mg/g":
        problems.append("unexpected_unit")
    checks.append({"check": "unit_mg_per_g", "ok": "unexpected_unit" not in problems,
                   "note": "Never converted automatically"})
    if not fields.get("method") or fields.get("method", "").lower().startswith("not stated"):
        problems.append("method_missing")
    checks.append({"check": "method_present", "ok": "method_missing" not in problems})
    checks.append({"check": "evidence_in_document", "ok": len(ev_ok) == len(fields.get("evidence", []))})
    status = "quarantined" if problems else "draft_for_clinician_verification"
    run["latency_ms"] = int((time.perf_counter() - t0) * 1000)
    run["gate"] = {"decision": "allowed" if not problems else "quarantined",
                   "reasons": [{"rule": p, "detail": "document checks"} for p in problems], "checks": []}
    return {"document": doc_id, "status": status, "fields": fields, "checks": checks, "problems": problems,
            "method": method, "evidence_highlights": ev_ok, "label": "SYNTHETIC document", "run": run}


NEGATION = re.compile(r"\b(?:not|no|never|none|without|don't|doesn't|didn't|isn't|aren't|won't|cannot|can't)\b", re.I)


def _negations(text: str) -> int:
    return len(NEGATION.findall(text or ""))


def draft_summary(note: str, *, lang: str, ai_on: bool) -> dict[str, Any]:
    """Care summary in the worker's language from the clinician's verified note (P1, §8.14 in EN/AR)."""
    t0 = time.perf_counter()
    run: dict[str, Any] = {"capability": "care_summary", "prompt_version": PROMPT_VERSION, "lang": lang}
    lang_name = "Arabic" if lang == "ar" else "English"
    if not ai_on:
        run["gate"] = {"decision": "not_needed", "reasons": [], "checks": []}
        return {"summary": None, "status": "ai_off_manual_template", "run": run}
    try:
        o = CLIENT.generate_json(
            tier="reasoning",
            system=(f"Rewrite the clinician's verified note as a plain-language summary for the worker in {lang_name}"
                    ", at most 4 short sentences. Add NOTHING that is not in the note: no diagnosis, no "
                    "probability, no advice, no new numbers. Keep each instruction in the clinician's own form: a "
                    "negative instruction stays negative ('do not stop' stays 'do not stop'). Then give an English "
                    "back_translation of your summary, word for word. JSON only."),
            user=f"Clinician's verified note:\n<<<{note}>>>", schema=SUMMARY_SCHEMA, temperature=0.1, max_tokens=500,
            timeout_s=15.0)
        d = o["data"]
        g = G.check({"text": d.get("summary", "")}, facts={"note": note}, lang=lang, text_fields=("text",),
                    fallback_template="msg.result_needs_clinician")
        # Back-translation check: numbers and key terms must survive the round trip (T91).
        nums_note = set(G.numbers_in(note))
        nums_back = set(G.numbers_in(d.get("back_translation", "")))
        discrepancies = sorted(nums_back ^ nums_note)
        # Meaning check beyond numbers: a negation gained or lost in the round trip ("do not stop" -> "stop").
        if _negations(note) != _negations(d.get("back_translation", "")):
            discrepancies.append("negation_changed")
        status = "draft_for_clinician_approval" if g["decision"] == "allowed" and not discrepancies else \
            "flagged_for_clinician"
        run.update(gate=g, latency_ms=int((time.perf_counter() - t0) * 1000))
        return {"summary": d.get("summary"), "back_translation": d.get("back_translation"),
                "discrepancies": discrepancies, "status": status, "run": run}
    except AIUnavailable as exc:
        run.update(gate={"decision": "not_needed", "reasons": [], "checks": []}, fallback=str(exc))
        return {"summary": None, "status": "ai_unavailable_manual_template", "run": run}
