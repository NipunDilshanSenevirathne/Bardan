"""Plan and action explanations (finalsystem.md §13.5 P0 "plan explanations", §16.1, §15.7).

A model may only explain a decision that the deterministic engine already made,
using permitted facts and allowed action IDs. The gate checks action IDs,
numeric grounding, claims and language; on failure the reviewed template is used.
"""
from __future__ import annotations

import json
from typing import Any

from ..core import content
from . import gate as G
from .gemini import CLIENT, AIUnavailable

PROMPT_VERSION = "explain-prompt@1.4"
SCHEMA = {"type": "object", "properties": {"text": {"type": "string"},
                                           "action_ids": {"type": "array", "items": {"type": "string"}}},
          "required": ["text", "action_ids"]}
# The plan explanation takes no action, so its output has no action IDs. Found live on 8 November 2026: the model
# put the changed task IDs (P1, P2, P3) in action_ids and the gate rightly blocked every draft.
PLAN_SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}


def worker_card(status: dict[str, Any], lang: str, ai_on: bool) -> dict[str, Any]:
    d = status["decision"]
    allowed = set(d["actions"])
    obs = (status.get("inputs") or {}).get("observation") or {}
    w = status["worker"]
    template = status["message"]
    # Labelled facts in plain words: the model explains what the card already says, never internal codes.
    facts = {"card_says": template.get("text"), "status": status.get("state_label"),
             "why": [content.reason_text(r, lang, obs.get("value")) for r in d["reasons"]],
             "reading": obs.get("value"), "unit": obs.get("unit"),
             "observed_at": (obs.get("observed_at") or "")[11:16], "reading_age_min": obs.get("age_min"),
             "zone": (status["assignment"].get("zone") or {}).get("id"), "breaks": [b["time"] for b in status["breaks"]]}
    if w.get("acclimatization") == "new":
        facts.update(new_worker=True, acclimatization_day=w.get("day"), heat_exposure_limit_percent=w["exposure_percent"])
    run = {"capability": "explain_card", "prompt_version": PROMPT_VERSION, "lang": lang}
    # Emergencies and individual care plans never get a model-written card (an individual fluid plan must not
    # meet general drinking advice, T10).
    if not ai_on or d["state"] in ("emergency",) or template.get("template_id") == "msg.routine_plan_fluid":
        run["gate"] = {"decision": "not_needed", "reasons": [], "checks": []}
        return {"explanation": {**template, "source": "approved_template"}, "run": run}
    lang_name = "Arabic" if lang == "ar" else "English"
    system = (f"Explain to a construction worker, in {lang_name}, in two short sentences, WHY this protection "
              "decision applies now, using the reasons in 'why'. Stay consistent with what the card already says "
              "('card_says'). Use only the facts. In the text, describe actions in plain words (their labels); put "
              "the IDs of the actions you mention only in action_ids, never in the text. No advice beyond the "
              "actions, no diagnosis, no new numbers. Write natural, grammatical " + lang_name +
              (" (simple Modern Standard Arabic)" if lang == "ar" else "") + ". JSON only.")
    labels = {a: content.label(content.ACTION_LABELS, a, lang) for a in allowed}
    try:
        o = CLIENT.generate_json(tier="fast", system=system,
                                 user=f"Facts: {json.dumps(facts, ensure_ascii=False)}\n"
                                      f"Actions (ID: label): {json.dumps(labels, ensure_ascii=False)}",
                                 schema=SCHEMA, temperature=0.2, max_tokens=200, timeout_s=8.0)
        draft = o["data"]
        g = G.check(draft, schema=SCHEMA, facts=facts, allowed_actions=allowed, lang=lang, state=d["state"],
                    must_disclose=None, fallback_template=template["template_id"])
        shown = G.safe_text(g, draft.get("text", ""), lang)
        if g["decision"] != "allowed":
            shown = {**template, "source": "approved_template"}
        run.update(gate=g, draft=draft.get("text"), latency_ms=o["latency_ms"])
        return {"explanation": shown, "run": run}
    except AIUnavailable as exc:
        run.update(gate={"decision": "not_needed", "reasons": [], "checks": []}, fallback=str(exc))
        return {"explanation": {**template, "source": "approved_template"}, "run": run}


def plan_explanation(sc: dict[str, Any], lang: str, ai_on: bool) -> dict[str, Any]:
    """The planning agent's plain-word explanation, grounded in the certificate's numbers."""
    m, dm = sc["metrics"], sc["draft_metrics"]
    ar = lang == "ar"
    changes = [{"task": (c.get("name_ar") if ar else None) or c["name"], "from": c["from"], "to": c["to"],
                "reason": c["reason_ar"] if ar else c["reason"]} for c in sc["changes"]]
    facts = {"changes": changes, "heavy_harsh_draft": dm["heavy_harsh_worker_hours"],
             "heavy_harsh_plan": m["heavy_harsh_worker_hours"], "withdrawal_draft": dm["withdrawal_work_hours"],
             "midday_draft": dm["midday_violation_hours"], "rest_conflicts_draft": dm["rest_conflicts"],
             "seats_r1": 20, "workers": 40, "zero": 0}
    det_en = ("The pour moves to the early morning because Zone B is forecast to reach the withdrawal band from "
              f"10:00 and outdoor work in the sun must stop from 12:30. Heavy work in harsh bands falls from "
              f"{dm['heavy_harsh_worker_hours']:g} to {m['heavy_harsh_worker_hours']:g} worker-hours, and breaks "
              "are staggered so no shelter holds more people than its seats.")
    det_ar = ("ينتقل الصب إلى الصباح الباكر لأن التوقعات تشير إلى بلوغ المنطقة B نطاق الانسحاب من الساعة 10:00، "
              "ويجب إيقاف العمل في الشمس من 12:30. ينخفض العمل الشاق في النطاقات القاسية من "
              f"{dm['heavy_harsh_worker_hours']:g} إلى {m['heavy_harsh_worker_hours']:g} ساعة عمل، "
              "وتُوزّع الاستراحات بحيث لا يتجاوز عدد الأشخاص في أي مظلة عدد مقاعدها.")
    det = det_ar if lang == "ar" else det_en
    run = {"capability": "plan_explanation", "prompt_version": PROMPT_VERSION, "lang": lang}
    if not ai_on:
        run["gate"] = {"decision": "not_needed", "reasons": [], "checks": []}
        return {"text": det, "source": "reviewed_template", "run": run}
    lang_name = "Arabic" if lang == "ar" else "English"
    try:
        o = CLIENT.generate_json(
            tier="fast", system=(f"You are Bardan's planning agent. In {lang_name}, explain to a site supervisor in "
                                 "at most 3 sentences why the proposed plan differs from the draft. Use only the "
                                 "facts and their numbers. No new numbers. Call each task by its name. "
                                 "JSON with text."),
            user=f"Facts: {facts}", schema=PLAN_SCHEMA, temperature=0.2, max_tokens=260, timeout_s=10.0)
        draft = o["data"]
        g = G.check(draft, schema=PLAN_SCHEMA, facts={**facts, "times": ["05:30", "09:30", "10:00", "12:30", "15:00"]},
                    allowed_actions=set(), lang=lang, role="supervisor")
        run.update(gate=g, draft=draft.get("text"), latency_ms=o["latency_ms"])
        if g["decision"] == "allowed":
            return {"text": draft["text"], "source": "ai_assisted", "run": run}
        return {"text": det, "source": "reviewed_template", "run": run}
    except AIUnavailable as exc:
        run.update(gate={"decision": "not_needed", "reasons": [], "checks": []}, fallback=str(exc))
        return {"text": det, "source": "reviewed_template", "run": run}
