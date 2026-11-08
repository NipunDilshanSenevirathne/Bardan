"""Bardan Guardian: the policy gate (finalsystem.md §16.5, B.4, B.8, G30).

Ordinary, testable code. It validates the WHOLE response shape, not keywords
alone, and blocks (falling back to an approved template in the worker's
language) when any rule fails:

  1. schema                 the output matches its typed contract
  2. action_ids             only action IDs the deterministic plan allowed
  3. numeric_grounding      every number appears in the permitted facts (G30)
  4. evidence_approved      cited passages are approved, in date and in jurisdiction
  5. forbidden_claim.*      diagnosis, kidney probability, fitness, dose, reassurance
  5b. plain_language        no internal codes (action, metric, message or reason IDs) in text people read
  6. policy_floor           never "keep working" after a concerning symptom or a stop
  7. role_permission        clinical content never reaches an employer role
  8. consent                disclosure is covered by current consent
  9. limitation_disclosed   stale or missing data is admitted, not hidden
 10. language               the draft is in the worker's language
 11. injection              instructions or tool calls echoed from data are refused
 12. sensitive_request      no requests for information the task does not need
"""
from __future__ import annotations

import re
from typing import Any

import jsonschema

from ..core import content

GATE_VERSION = "gate-1.5.0"

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫", "0123456789.")
NUM = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)(?![\w])")

FORBIDDEN: dict[str, list[str]] = {
    "forbidden_claim.kidney_probability": [
        r"\b\d+(?:\.\d+)?\s*(?:%|percent|per cent)\b[^.]*\b(?:kidney|renal|fail|failure|damage|disease|risk|chance)",
        r"\b(?:chance|probability|likelihood|risk)\b[^.]{0,40}\b(?:kidney|renal)\b[^.]{0,40}\b(?:fail|failure|disease|damage)",
        r"\bkidneys?\b[^.]{0,40}\b(?:are|is)\s+(?:likely|probably)\s+(?:to\s+)?fail",
        # The number after the kidney words: "your kidney failure risk is 85%" (found live, red-team mode).
        r"\b(?:kidney|renal)\b[^.]{0,60}?\d+(?:\.\d+)?\s*(?:%|percent|per cent)",
        r"(?:نسبة|احتمال|فرصة|خطر|مخاطر|تقدير)[^.]{0,40}(?:الكل|كلي|فشل|قصور)",
        r"\d+\s*(?:٪|%)[^.]{0,40}(?:الكل|كلي|فشل|قصور)",
        r"(?:الكل|كلي|فشل كلوي|قصور كلوي)[^.]{0,60}?\d+\s*(?:٪|%|في المئة|بالمئة)",
    ],
    "forbidden_claim.diagnosis": [
        r"\byou(?:'re|\s+are|\s+have|\s+may|\s+might|\s+will)?\s+(?:\w+\s+){0,2}(?:have|having|developing|"
        r"suffering from|getting|got|showing)\b[^.]{0,30}"
        r"\b(?:ckd|chronic kidney|kidney (?:disease|failure|damage|injury)|aki|heat ?stroke|renal failure)",
        r"\b(?:diagnos(?:is|ed)\s+(?:of|with|is))\b",
        r"(?:أنت|انت|لديك|عندك)\s+[^.]{0,20}(?:مرض الكلى|فشل كلوي|قصور كلوي|ضربة شمس)",
        r"(?:تشخيصك|تم تشخيصك)",
    ],
    "forbidden_claim.reassurance": [
        r"\byour\s+kidneys?\s+(?:are|look|seem)\s+(?:healthy|fine|normal|ok|okay|good)",
        r"\b(?:nothing to worry about|no need to worry|you(?:'re| are) (?:fine|healthy|safe))\b",
        r"(?:كليتاك|كليتيك|كلاك)\s+(?:سليمة|سليمتان|بخير|طبيعية)",
        r"(?:لا داعي للقلق|لا تقلق أبدا|أنت بخير)",
    ],
    "forbidden_claim.fitness": [
        r"\b(?:fit|safe|cleared|ready)\s+(?:to|for)\s+(?:work|return)",
        r"\b(?:fitness|readiness)\s+score\b",
        r"(?:لائق للعمل|آمن للعمل|جاهز للعمل|مسموح لك بالعمل)",
    ],
    # Absolute certainty about a health question. Found live on 8 November 2026 (red-team mode): "I am 100% certain
    # you should ..." passed numeric grounding because a retrieved passage happened to contain 100.
    "forbidden_claim.certainty": [
        r"\b(?:100|hundred)\s*(?:%|percent|per cent)\s+(?:certain|sure|confident|positive)\b",
        r"\b(?:i am|i'm|we are|we're)\s+(?:\w+\s+){0,2}(?:certain|confident)\b",
        r"\b(?:i|we)\s+(?:can\s+)?guarantee\b",
        r"\bdefinitively\b",
        r"\bwithout (?:any |a )?(?:doubt|question)\b",
        r"متأكد(?:ة)?\s+(?:تماما|تماماً|جدا|جداً|كل التأكد|بنسبة)",
        r"(?:100|١٠٠)\s*(?:%|٪|بالمئة|في المئة)\s*(?:متأكد|أكيد|واثق)",
        r"(?:متأكد|أكيد|واثق)(?:ة)?\s*(?:بنسبة\s*)?(?:100|١٠٠)\s*(?:%|٪|بالمئة|في المئة)",
        r"بكل\s+تأكيد",
        r"(?:أضمن|اضمن)\s+لك",
        r"(?:بدون|دون)\s+(?:أي\s+|أدنى\s+|أي أدنى\s+)?شك",
        r"واثق(?:ة)?\s+(?:تماما|تماماً|جدا|جداً|من هذا)",
    ],
    # Doses, not laboratory units: "400 mg" is a dose, "64 mg/g" (urine ACR) or "7.2 mg/mmol" is a result.
    "forbidden_claim.dose": [
        r"\b\d+(?:\.\d+)?\s*(?:mg|milligrams?|ml)\b(?!\s*/)",
        r"\b\d+(?:\.\d+)?\s*(?:tablets?|pills?|capsules?)\b",
        r"\btake\s+(?:one|two|three|\d+)\s+(?:tablets?|pills?|doses?)",
        r"\b(?:dose|dosage)\s+(?:is|of)\b",
        r"(?:جرعة|ملغ|ملجم|ملليغرام|مليغرام|حبة|حبتين|أقراص)\s*(?:\d|واحدة|اثنتين)",
        r"(?:خذ|تناول|اشرب)\s+(?:حبة|حبتين|ثلاث|\d+)",
        r"\d+\s*(?:حبة|حبات|أقراص|قرص)",
        r"\d+\s*(?:ملغ|ملجم|ملليغرام|مليغرام)(?!\s*/)",
    ],
}
INTERNAL_TERMS = re.compile(r"\bpassages?\b|\bpassage[_ ]ids?\b|\bjson\b|\bsystem prompt\b|\bthe prompt\b|"
                            r"(?:المقاطع|المقتطفات|النصوص|الفقرات)\s+المعتمدة|المقاطع المقدمة", re.I)
POLICY_FLOOR = [
    r"\b(?:keep|continue|carry on|go back to)\s+(?:working|work)\b",
    r"\b(?:you can|it is ok to|it's ok to|safe to)\s+(?:work|continue)\b",
    r"\bfinish\s+(?:your|the)\s+(?:task|shift|work)\b",
    r"(?:واصل العمل|استمر في العمل|يمكنك العمل|أكمل عملك|ارجع للعمل)",
]
INJECTION = [
    r"\bignore (?:all|your|the|previous)\b", r"\bsystem prompt\b", r"\bemail (?:all|the) (?:results|records)",
    r"\bexport (?:all|the) (?:data|results|records)", r"\bactivate (?:the )?plan\b", r"\bcall_tool\b",
    r"تجاهل (?:التعليمات|القواعد)", r"أرسل جميع النتائج",
]
SENSITIVE = [
    r"\b(?:passport|emirates id|visa|bank|card|password|pin)\s*(?:number|no\.?)?\b.*\?",
    r"(?:رقم الجواز|الهوية الإماراتية|رقم البطاقة|كلمة السر)",
]
CLINICAL_TERMS = [r"\bacr\b", r"\begfr\b", r"\balbumin", r"\bcreatinine\b", r"\bmg/g\b", r"\burine\b.*\bresult",
                  r"الألبومين", r"الكرياتينين", r"نتيجة (?:فحص )?(?:البول|الكلى)"]


def _norm(text: str) -> str:
    return (text or "").translate(_AR_DIGITS)


def numbers_in(text: str) -> list[str]:
    out = []
    for m in NUM.finditer(_norm(text)):
        out.append(m.group(1).replace(",", "."))
    return out


def allowed_numbers(facts: Any) -> set[str]:
    nums: set[str] = set()

    def walk(v: Any) -> None:
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple, set)):
            for x in v:
                walk(x)
        elif isinstance(v, bool) or v is None:
            return
        elif isinstance(v, (int, float)):
            nums.add(_fmt(v))
        elif isinstance(v, str):
            for n in numbers_in(v):
                nums.add(_fmt(float(n)))
    walk(facts)
    return nums


def _fmt(v: float) -> str:
    f = float(v)
    return str(int(f)) if f.is_integer() else f"{f:g}"


def language_of(text: str) -> str:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "unknown"
    arabic = sum(1 for c in letters if "؀" <= c <= "ۿ" or "ݐ" <= c <= "ݿ")
    return "ar" if arabic / len(letters) > 0.6 else "en" if arabic / len(letters) < 0.2 else "mixed"


def check(draft: dict[str, Any], *, schema: dict[str, Any] | None = None, facts: dict[str, Any] | None = None,
          allowed_actions: set[str] | None = None, lang: str = "en", role: str = "worker",
          approved_ids: set[str] | None = None, state: str | None = None, consent_ok: bool = True,
          must_disclose: list[str] | None = None, text_fields: tuple[str, ...] = ("text", "answer", "summary"),
          fallback_template: str = "msg.safe_fallback") -> dict[str, Any]:
    reasons: list[dict[str, str]] = []
    checks: list[dict[str, Any]] = []

    def rule(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"rule": name, "ok": ok})
        if not ok:
            reasons.append({"rule": name, "detail": detail})

    # 1. schema
    if schema is not None:
        try:
            jsonschema.validate(draft, schema)
            rule("schema", True)
        except jsonschema.ValidationError as exc:
            rule("schema", False, exc.message[:160])
    text = " ".join(str(draft.get(f, "")) for f in text_fields if draft.get(f))
    norm = _norm(text).lower()
    # 2. action IDs
    if allowed_actions is not None:
        bad = [a for a in draft.get("action_ids", []) if a not in allowed_actions]
        rule("action_ids", not bad, f"not allowed: {', '.join(bad)}" if bad else "")
    # 3. numeric grounding
    if facts is not None:
        allowed = allowed_numbers(facts)
        ungrounded = [n for n in numbers_in(text) if _fmt(float(n)) not in allowed]
        rule("numeric_grounding", not ungrounded,
             f"value {ungrounded[0]} not present in permitted facts" if ungrounded else "")
    # 4. evidence
    if approved_ids is not None:
        cited = draft.get("passage_ids", [])
        bad = [c for c in cited if c not in approved_ids]
        rule("evidence_approved", not bad, f"unapproved or inapplicable source: {', '.join(bad)}" if bad else "")
    # 5. forbidden claims
    for name, pats in FORBIDDEN.items():
        hit = next((p for p in pats if re.search(p, norm, re.I)), None)
        rule(name, hit is None, "pattern matched" if hit else "")
    # 5b. plain language: a person never reads an internal code (an action or metric ID, a message ID, a reason
    # code). Found live: a model wrote "you will receive EXTRA_BREAKS" into a worker's explanation.
    code = re.search(r"\w_\w|\bmsg\.[a-z]|\b(?:freshness|triage|emergency|resources|conflict):[a-z]", text)
    # Words from the model's own instructions. Found live on 8 November 2026: an Arabic answer read "لا توجد
    # passages معتمدة" ("there are no approved passages").
    if code is None:
        code = INTERNAL_TERMS.search(norm)
    rule("plain_language", code is None, "internal code or term in the text" if code else "")
    # 6. policy floor
    if state in ("stop", "emergency") or (facts or {}).get("concerning_symptom"):
        hit = next((p for p in POLICY_FLOOR if re.search(p, norm, re.I)), None)
        rule("policy_floor", hit is None, "suggests continuing work below the policy floor" if hit else "")
    # 7. role
    if role in ("supervisor", "hse", "auditor"):
        hit = next((p for p in CLINICAL_TERMS if re.search(p, norm, re.I)), None)
        rule("role_permission", hit is None, "clinical content for an employer role" if hit else "")
    # 8. consent
    rule("consent", consent_ok, "" if consent_ok else "disclosure not covered by current consent")
    # 9. limitations
    for phrase in must_disclose or []:
        ok = phrase.lower() in norm
        rule("limitation_disclosed", ok, "" if ok else f"missing disclosure: {phrase}")
    # 10. language
    if text:
        got = language_of(text)
        ok = got == lang or (got == "mixed" and lang == "ar")
        rule("language", ok, "" if ok else f"draft is {got}, worker language is {lang}")
    # 11. injection, 12. sensitive requests
    hit = next((p for p in INJECTION if re.search(p, norm, re.I)), None)
    rule("injection", hit is None, "instruction-like text from data was echoed" if hit else "")
    hit = next((p for p in SENSITIVE if re.search(p, norm, re.I)), None)
    rule("sensitive_request", hit is None, "asks for information the task does not need" if hit else "")

    blocked = bool(reasons)
    return {"component": "policy_gate", "policy_version": GATE_VERSION,
            "decision": "blocked" if blocked else "allowed", "reasons": reasons, "checks": checks,
            "fallback": {"template_id": fallback_template, "language": lang} if blocked else None}


def safe_text(gate_result: dict[str, Any], draft_text: str, lang: str, **slots: Any) -> dict[str, Any]:
    """What the worker actually sees: the draft if allowed, otherwise the approved template."""
    if gate_result["decision"] == "allowed":
        return {"text": draft_text, "source": "ai_assisted", "lang": lang}
    tid = gate_result["fallback"]["template_id"]
    return {"text": content.render(tid, lang, **slots), "source": "approved_template", "template_id": tid,
            "lang": lang}
