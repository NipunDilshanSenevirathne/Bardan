"""Worker companion routes: action card, reports, private check-ins, disputes, Speak, Ask, consent, passport."""
from __future__ import annotations

import base64
import secrets
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..ai import chat as chat_mod
from ..ai import explain as explain_mod
from ..ai import gate as gate_mod
from ..ai import intake as intake_mod
from ..ai.gemini import CLIENT, AIUnavailable
from ..core import actions, content
from ..core.clinical import fhir_bundle, pseudonym
from ..core.consent import PURPOSES
from ..core.ledger import LedgerError
from ..core.live import worker_status
from .deps import Ctx, context, idempotent

router = APIRouter(prefix="/v1")


def _worker_only(ctx: Ctx) -> None:
    ctx.require("self.read")


@router.get("/worker/today")
def today(ctx: Ctx = Depends(context)) -> dict[str, Any]:
    _worker_only(ctx)
    sb = ctx.sb
    with sb.lock:
        st = worker_status(sb, ctx.actor, ctx.lang)
    # Zone-level protection near the worker, plus personal tasks that name this worker. Another worker's
    # personal task (e.g. a move to shade) is never shown to colleagues.
    tasks = [sb.ledger.public(t, "worker") for t in sb.ledger.tasks.values()
             if t["state"] != "cancelled" and actions.task_concerns_worker(sb, t, ctx.actor)]
    for t in tasks:
        t["label"] = content.label(content.TASK_LABELS, t["action_code"], ctx.lang)
    notes = [n for n in sb.ledger.notifications if n.get("to_actor") == ctx.actor]
    tomorrow = None
    for sc in sb.plans.values():
        if sc.get("approval", {}).get("state") == "approved":
            msg = next((m for m in sc.get("worker_messages", []) if m["worker"] == ctx.actor), None)
            if msg:
                slots = (msg.get("slots_by_lang") or {}).get(ctx.lang) or msg["slots"]
                tomorrow = {**msg, "text": content.render(msg["template_id"], ctx.lang, **slots),
                            "plan": sc["scenario_id"]}
    return {"status": st, "tasks": tasks, "notifications": [{**n, "text": content.render_notification(n, ctx.lang)} for n in notes][-6:],
            "tomorrow": tomorrow,
            "help": {"emergency_number": "998", "help_point": "غرفة الإسعافات الأولية عند بوابة الموقع (علامة الصليب)"
                     if ctx.lang == "ar" else "Site gate first-aid room (cross sign)",
                     "dialler": "mock", "first_aiders": sb.world["responders"]},
            "label": sb.world["label"]}


@router.post("/worker/explain")
def explain(ctx: Ctx = Depends(context)) -> dict[str, Any]:
    _worker_only(ctx)
    sb = ctx.sb
    st = worker_status(sb, ctx.actor, ctx.lang)
    out = explain_mod.worker_card(st, ctx.lang, ai_on=sb.ai_enabled("explain"))
    run = sb.record_trace({**out["run"], "actor": ctx.actor, "input_ref": "worker_status"})
    return {"explanation": out["explanation"], "trace_id": run["id"]}


class ReportIn(BaseModel):
    intent: str
    zone: str | None = None


@router.post("/worker/reports")
def report(body: ReportIn, ctx: Ctx = Depends(context), idempotency_key: str | None = Header(default=None)):
    ctx.require("self.report")
    if body.intent not in actions.RESOURCE_TASK and body.intent != "HELP_REQUEST":
        raise HTTPException(422, "Unknown report type")

    def do():
        with ctx.sb.lock:
            if body.intent == "HELP_REQUEST":
                return actions.confirm_intake(ctx.sb, ctx.actor, {}, [{"intent": "HELP_REQUEST",
                                                                       "polarity": "affirmed"}])
            r = actions.report_resource(ctx.sb, ctx.actor, body.intent, body.zone)
            return {"task": ctx.sb.ledger.public(r["task"], "worker"), "duplicate": r["duplicate"],
                    "message": r["message"]}
    return idempotent(ctx, idempotency_key, do)


class CheckinIn(BaseModel):
    symptoms: list[str] = Field(default_factory=list, max_length=12)
    kind: str = "quick"
    preferences: dict[str, Any] | None = None
    about: str = "self"


@router.post("/worker/check-ins")
def checkin(body: CheckinIn, ctx: Ctx = Depends(context), idempotency_key: str | None = Header(default=None)):
    ctx.require("self.checkin")
    return idempotent(ctx, idempotency_key, lambda: actions.checkin(
        ctx.sb, ctx.actor, body.symptoms, kind=body.kind, preferences=body.preferences, about=body.about))


class DisputeIn(BaseModel):
    text: str = Field(default="This didn't happen", max_length=300)


@router.post("/worker/tasks/{task_id}/dispute")
def dispute(task_id: str, body: DisputeIn, ctx: Ctx = Depends(context),
            idempotency_key: str | None = Header(default=None, max_length=80)):
    ctx.require("self.dispute")
    return idempotent(ctx, f"dispute:{task_id}:{idempotency_key}" if idempotency_key else None,
                      lambda: _dispute(task_id, body, ctx))


def _dispute(task_id: str, body: DisputeIn, ctx: Ctx):
    sb = ctx.sb
    with sb.lock:
        try:
            _own_task(sb, task_id, ctx.actor)
            t = sb.ledger.dispute(task_id, actor=ctx.actor, role="worker", at=sb.now(), text=body.text)
        except LedgerError as e:
            raise HTTPException(e.status, str(e)) from e
        sb.audit.append(at=sb.now(), actor=ctx.actor, role="worker", action="task.dispute", resource=task_id)
    return {"task": sb.ledger.public(t, "worker"),
            "message": {"text": content.render("msg.dispute_received", ctx.lang,
                                               role="HSE" if ctx.lang == "en" else "مسؤول السلامة")}}


@router.post("/worker/tasks/{task_id}/confirm")
def confirm(task_id: str, ctx: Ctx = Depends(context), idempotency_key: str | None = Header(default=None, max_length=80)):
    ctx.require("task.confirm")
    return idempotent(ctx, f"confirm:{task_id}:{idempotency_key}" if idempotency_key else None,
                      lambda: _confirm(task_id, ctx))


def _confirm(task_id: str, ctx: Ctx):
    sb = ctx.sb
    with sb.lock:
        try:
            t = _own_task(sb, task_id, ctx.actor)
            if t["state"] not in ("reported_complete", "in_progress", "accepted", "escalated", "verified"):
                raise LedgerError("confirm_state", "Nothing to confirm yet.")
            # In an observed drill the real water point is outside the app, so the worker's word is taken; the
            # observer records whether the water was really back.
            if t["action_code"] == "WATER_RESTORE" and not t.get("drill") and \
                    not _water_physically_back(sb, t["zone_id"]):
                raise LedgerError("still_missing", "You can only confirm when the water is really back. If it is "
                                                   "still missing, press 'This didn't happen'.", 422)
            mine = [d for d in t["disputes"] if d.get("raised_by_ref") == ctx.actor and d["open"]]
            for d in mine:
                d["open"] = False
                d["resolved_at"] = sb.now()
                d["resolved_by"] = "worker_confirmation"
            t["open_disputes"] = sum(1 for d in t["disputes"] if d["open"])
            if t["action_code"] in ("WATER_RESTORE", "SHADE_EXTEND", "ENHANCED_SCHEDULE", "CHECK_WORKER",
                                    "MOVE_TO_SHADED_TASK", "BREAK_ACCESS"):
                sb.ledger.add_evidence(task_id, {"kind": "worker_confirmation", "scope": "Worker confirms the "
                                                 "protection is available"}, actor=ctx.actor, role="worker",
                                       at=sb.now())
            sb.audit.append(at=sb.now(), actor=ctx.actor, role="worker", action="task.confirm", resource=task_id)
        except LedgerError as e:
            raise HTTPException(e.status, str(e)) from e
    return {"task": sb.ledger.public(t, "worker")}


def _own_task(sb, task_id: str, wid: str) -> dict[str, Any]:
    """A worker can only confirm or dispute a protection they are shown; any other task is 'not found' to them, so
    a worker learns nothing about other people's tasks (and cannot block them)."""
    t = sb.ledger.tasks.get(task_id)
    if not t or not actions.task_concerns_worker(sb, t, wid):
        raise LedgerError("not_found", "Task not found", 404)
    return t


def _water_physically_back(sb, zone: str) -> bool:
    wp = next(w for w in sb.world["water_points"] if w["zone"] == zone)
    phys = sb.world["physical"]["water"].get(wp["id"])
    if not phys:
        return True
    return bool(phys.get("refilled_at"))


# ------------------------------------------------------------------ Speak
class IntakeIn(BaseModel):
    text: str | None = Field(default=None, max_length=600)
    audio_b64: str | None = Field(default=None, max_length=4_000_000)
    mime: str | None = Field(default=None, max_length=60)


AUDIO_MIME = {"audio/webm", "audio/ogg", "audio/wav", "audio/mp4", "audio/mpeg", "audio/aac", "audio/flac",
              "audio/x-wav", "audio/m4a"}


@router.post("/assist/intake")
def intake(body: IntakeIn, ctx: Ctx = Depends(context)):
    ctx.require("assist.intake")
    if not body.text and not body.audio_b64:
        raise HTTPException(422, "Say or type something, or use the icons.")
    audio = None
    if body.audio_b64:
        mime = (body.mime or "audio/webm").split(";")[0]
        if mime not in AUDIO_MIME:
            raise HTTPException(415, "Unsupported audio type")
        audio = (mime, base64.b64decode(body.audio_b64))
    sb = ctx.sb
    res = intake_mod.run(body.text, audio, ai_on=sb.ai_enabled("speak"))
    did = "intk_" + secrets.token_hex(4)
    sb.intake_drafts[did] = {"id": did, "worker": ctx.actor, "at": sb.now(), **res}
    run = sb.record_trace({"capability": "speak_intake", "actor": ctx.actor, "lang": res["language"],
                           "prompt_version": res["prompt_version"], "method": res["method"],
                           "input_ref": res["input_ref"], "latency_ms": res["latency_ms"],
                           "output": {"candidates": res["candidates"], "uncertain": res["uncertain"]},
                           "gate": {"decision": res["gate"]["decision"], "reasons": res["gate"]["notes"],
                                    "checks": []}, "ai_unavailable": res["ai_unavailable"]})
    labels = {k: {"en": v["en"], "ar": v["ar"], "icon": v["icon"], "urgent": v["urgent"]}
              for k, v in content.INTENTS.items()}
    return {"draft_id": did, **res, "labels": labels, "trace_id": run["id"],
            "prompt": content.render("msg.not_understood", ctx.lang) if res["uncertain"] else None}


class ConfirmIn(BaseModel):
    confirmed: list[dict[str, Any]] = Field(default_factory=list, max_length=12)


@router.post("/assist/intake/{draft_id}/confirm")
def intake_confirm(draft_id: str, body: ConfirmIn, ctx: Ctx = Depends(context)):
    ctx.require("assist.intake")
    sb = ctx.sb
    d = sb.intake_drafts.get(draft_id)
    if not d or d["worker"] != ctx.actor:
        raise HTTPException(404, "Draft not found")
    if d.get("confirmed_at"):
        return {"already_confirmed": True}
    for c in body.confirmed:
        if c.get("intent") not in content.INTENTS:
            raise HTTPException(422, "Unknown intent")
    with sb.lock:
        out = actions.confirm_intake(sb, ctx.actor, d, body.confirmed)
    return out


# -------------------------------------------------------------------- Ask
class ChatIn(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)


@router.post("/assist/chat")
def ask(body: ChatIn, ctx: Ctx = Depends(context)):
    ctx.require("assist.chat")
    sb = ctx.sb
    st = worker_status(sb, ctx.actor, ctx.lang, apply_tightening=False)
    appt = None
    for ref in sb.clinical.referrals.values():
        if ref["worker_ref"] == ctx.actor and ref.get("appointment") and ref["state"] == "scheduled":
            a = ref["appointment"]
            appt = f"{_d(a['start'])} {a['start'][11:16]}-{a['end'][11:16]}"
    facts = {"state": st["decision"]["state"], "appointment": appt, "emergency_number": 998,
             "concerning_symptom": "triage:concerning_symptom" in st["decision"]["reasons"],
             "fluid_plan": sb.clinical.has_fluid_plan(ctx.actor)}
    # Answer in the language the question was written in; a mixed or unclear question follows the interface.
    # Found live on 8 November 2026: an Arabic question typed in the English interface got an English answer.
    asked = gate_mod.language_of(body.question)
    lang = asked if asked in ("en", "ar") else ctx.lang
    out = chat_mod.answer(body.question, lang=lang, facts=facts, ai_on=sb.ai_enabled("chat"),
                          redteam=bool(sb.world["settings"].get("redteam_mode")))
    run = sb.record_trace({**out["run"], "actor": ctx.actor, "question": body.question})
    return {"answer": out["answer"], "trace_id": run["id"], "gate": run["gate"]["decision"],
            "checked_by": "Bardan Guardian"}


def _d(iso: str) -> str:
    dt = datetime.fromisoformat(iso)
    return dt.strftime("%d %b")


class TtsIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)


@router.post("/assist/tts")
def tts(body: TtsIn, ctx: Ctx = Depends(context)):
    if not ctx.sb.ai_enabled("speech"):
        raise HTTPException(503, "Speech off: the app uses the phone's own voice instead.")
    try:
        wav = CLIENT.speak(body.text)
    except AIUnavailable as exc:
        raise HTTPException(503, "Speech unavailable: the app uses the phone's own voice instead.") from exc
    return Response(content=wav, media_type="audio/wav")


# -------------------------------------------------------------- emergency
class EmergencyIn(BaseModel):
    event_id: str | None = Field(default=None, max_length=64)
    kind: str
    subject: str | None = None
    symptoms: list[str] = Field(default_factory=list)
    device_time: str | None = None
    offline: bool = False


@router.post("/emergency/events")
def emergency(body: EmergencyIn, ctx: Ctx = Depends(context)):
    ctx.require("emergency.use")
    with ctx.sb.lock:
        try:
            return actions.emergency_event(ctx.sb, ctx.actor, body.model_dump())
        except ValueError as e:
            raise HTTPException(422, str(e)) from e


@router.get("/emergency/{emergency_id}")
def emergency_get(emergency_id: str, ctx: Ctx = Depends(context)):
    """What has really happened to an alert: received by the server, acknowledged by a responder, help received."""
    ctx.require("emergency.use")
    rec = next((e for e in ctx.sb.emergencies if e["id"] == emergency_id), None)
    if rec is None or (ctx.role == "worker" and ctx.actor not in (rec["reported_by"], rec["subject"])):
        raise HTTPException(404, "Alert not found")
    return actions.emergency_status(ctx.sb, rec)


@router.post("/emergency/{emergency_id}/acknowledge")
def emergency_ack(emergency_id: str, ctx: Ctx = Depends(context)):
    ctx.require("emergency.use")
    if ctx.role in ("worker", "auditor"):
        raise HTTPException(403, "Only a responder on the site or clinic team can acknowledge an alert.")
    with ctx.sb.lock:
        try:
            return actions.acknowledge_emergency(ctx.sb, emergency_id, actor=ctx.actor, role=ctx.role)
        except KeyError as e:
            raise HTTPException(404, "Alert not found") from e


class SyncIn(BaseModel):
    device_id: str = Field(..., max_length=64)
    events: list[dict[str, Any]] = Field(default_factory=list, max_length=200)


@router.post("/sync")
def sync(body: SyncIn, ctx: Ctx = Depends(context)):
    """Idempotent outbox exchange (§20.3): duplicates create nothing new; withdrawal always wins."""
    sb = ctx.sb
    acks = []
    for ev in sorted(body.events, key=lambda e: e.get("sequence", 0)):
        eid = ev.get("event_id")
        key = f"sync:{body.device_id}:{eid}"
        if not eid:
            acks.append({"event_id": None, "status": "rejected", "reason": "missing event_id"})
            continue
        if key in sb.sync_acks:
            acks.append({**sb.sync_acks[key], "status": "duplicate"})
            continue
        typ = ev.get("event_type")
        clock_issue = _clock_quality(sb, body.device_id, ev.get("observed_at"))
        if clock_issue:
            if typ == "consent" and (ev.get("payload") or {}).get("action") == "grant":
                # A grant whose time cannot be trusted never overrides a withdrawal (T38, T55).
                ack = {"event_id": eid, "status": "rejected", "reason": f"time_uncertain:{clock_issue}",
                       "detail": "Device clock problem: the grant was not applied. Ask again online."}
                sb.sync_acks[key] = ack
                acks.append(ack)
                continue
            # Everything else is kept (safety first) on server time, marked time-uncertain.
            ev = {**ev, "observed_at": sb.now(), "device_reported_at": ev.get("observed_at")}
        try:
            with sb.lock:
                if typ == "emergency":
                    r = actions.emergency_event(sb, ctx.actor, {**ev.get("payload", {}), "event_id": eid,
                                                                "offline": True})
                elif typ == "checkin":
                    p = ev.get("payload", {})
                    r = actions.checkin(sb, ctx.actor, p.get("symptoms", []), kind=p.get("kind", "quick"),
                                        via="offline_outbox",
                                        about="other_person" if p.get("about") == "other_person" else "self")
                elif typ == "report":
                    intent = (ev.get("payload") or {}).get("intent")
                    if intent == "HELP_REQUEST":       # same path as the online "I need help" button
                        actions.confirm_intake(sb, ctx.actor, {}, [{"intent": "HELP_REQUEST", "polarity": "affirmed"}])
                        r = {"help_requested": True}
                    elif intent in actions.RESOURCE_TASK:
                        r = {"report": actions.report_resource(sb, ctx.actor, intent, via="offline_outbox")["task"]["id"]}
                    else:
                        raise ValueError("unknown report type")
                elif typ == "consent":
                    p = ev["payload"]
                    r = sb.consent.record(worker_ref=ctx.actor, purpose=p["purpose"], action=p["action"],
                                          at=ev.get("observed_at") or sb.now(), device=body.device_id,
                                          recorded_at=sb.now())
                    st = sb.consent.status(ctx.actor, p["purpose"])
                    r = {"consent": p, "effective": st}
                else:
                    raise ValueError("unknown event type")
            ack = {"event_id": eid, "status": "accepted", "server_received_at": sb.now(), "result": r,
                   **({"time_uncertain": clock_issue} if clock_issue else {})}
        except Exception as exc:  # report, never crash the batch
            ack = {"event_id": eid, "status": "rejected", "reason": str(exc)}
        sb.sync_acks[key] = ack
        acks.append(ack)
    return {"acks": acks, "server_time": sb.now()}


CLOCK_AHEAD_TOLERANCE_MIN = 5


def _clock_quality(sb, device_id: str, observed_at: str | None) -> str | None:
    """Detect device clocks that run ahead or were rolled back (T55). Returns a problem code, or None."""
    if not observed_at:
        return None
    try:
        t = datetime.fromisoformat(observed_at)
    except ValueError:
        return "unparseable_time"
    if t.tzinfo is None:
        return "no_utc_offset"
    now = datetime.fromisoformat(sb.now())
    if (t - now).total_seconds() > CLOCK_AHEAD_TOLERANCE_MIN * 60:
        return "device_clock_ahead"
    last = sb.device_clock.get(device_id)
    if last and t < datetime.fromisoformat(last):
        return "device_clock_rolled_back"
    sb.device_clock[device_id] = observed_at
    return None


# ----------------------------------------------------------- my health
@router.get("/worker/health")
def my_health(ctx: Ctx = Depends(context)):
    _worker_only(ctx)
    sb = ctx.sb
    pid = pseudonym(ctx.actor)
    enrolled = sb.consent.status(ctx.actor, "clinical_care")["active"]
    patient = sb.clinical.patients.get(pid)
    results = sb.clinical.results_for(pid) if patient else []
    refs = [r for r in sb.clinical.referrals.values() if r["worker_ref"] == ctx.actor]
    hyd = [h for h in sb.clinical.hydration if h["worker_ref"] == ctx.actor]
    summaries = [s for s in sb.clinical.summaries if s["worker_ref"] == ctx.actor and s["status"] == "approved"]
    sb.audit.append(at=sb.now(), actor=ctx.actor, role="worker", action="clinical.read_own", resource=pid,
                    subject=ctx.actor, category="clinical")
    who = [e for e in sb.audit.scoped(role="worker", actor=ctx.actor) if e.get("subject") == ctx.actor
           and e["actor"] != ctx.actor]
    return {"enrolled": enrolled, "results": [{k: r[k] for k in ("id", "label", "value", "unit", "specimen_at",
                                                                 "method", "lab", "verification", "note")}
                                              for r in results],
            "result_message": content.render("msg.result_needs_clinician", ctx.lang,
                                             date=_appt(refs) or "-") if results else None,
            "referrals": refs, "hydration": hyd, "summaries": summaries,
            "consents": sb.consent.summary(ctx.actor), "consent_message": content.render("msg.consent_summary",
                                                                                          ctx.lang),
            "who_saw_my_data": who[-20:], "label": "SYNTHETIC: not a real result"}


def _appt(refs) -> str | None:
    for r in refs:
        if r.get("appointment") and r["state"] in ("scheduled", "attended"):
            return f"{_d(r['appointment']['start'])} {r['appointment']['start'][11:16]}"
    return None


@router.get("/consents")
def consents(ctx: Ctx = Depends(context)):
    ctx.require("self.consent")
    return {"consents": ctx.sb.consent.summary(ctx.actor), "history": ctx.sb.consent.history(ctx.actor)}


class ConsentIn(BaseModel):
    purpose: str
    action: str
    observed_at: str | None = None   # device time for offline events (T38)


@router.post("/consents/events")
def consent_event(body: ConsentIn, ctx: Ctx = Depends(context)):
    ctx.require("self.consent")
    sb = ctx.sb
    if body.purpose not in PURPOSES:
        raise HTTPException(422, "Unknown purpose")
    try:
        ev = sb.consent.record(worker_ref=ctx.actor, purpose=body.purpose, action=body.action,
                               at=body.observed_at or sb.now(), recorded_at=sb.now(),
                               device="online" if not body.observed_at else "phone",
                               server_stamped=not body.observed_at)
    except PermissionError as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    if body.action == "withdraw" and body.purpose == "passport_sharing":
        for link in sb.clinical.share_links.values():
            if link["worker_ref"] == ctx.actor:
                link["revoked"] = True
    sb.audit.append(at=sb.now(), actor=ctx.actor, role="worker", action=f"consent.{body.action}",
                    resource=body.purpose, subject=ctx.actor, category="consent")
    msg = content.render("msg.sharing_withdrawn", ctx.lang) if body.action == "withdraw" else None
    return {"event": ev, "effective": sb.consent.status(ctx.actor, body.purpose), "message": msg}


# ---------------------------------------------------------- Optional wearable (worker-controlled)
class WearableIn(BaseModel):
    """Only a status crosses from the phone. Heart rate, temperature estimates or any other number are refused
    (extra fields are rejected), and there is no status that clears a worker or relaxes a rule."""
    model_config = {"extra": "forbid"}
    status: str = Field(..., pattern=r"^(needs_break|check_on_me)$")
    observed_at: str | None = Field(default=None, max_length=40)


WEARABLE_PURPOSE = {"needs_break": "wearable_status_share", "check_on_me": "wearable_buddy_alert"}


@router.post("/worker/wearable/status")
def wearable_status(body: WearableIn, ctx: Ctx = Depends(context), idempotency_key: str | None = Header(default=None)):
    ctx.require("self.report")
    sb = ctx.sb
    purpose = WEARABLE_PURPOSE[body.status]
    if not sb.consent.status(ctx.actor, purpose)["active"]:
        raise HTTPException(403, "You have not chosen to share this, so nothing was sent. Your alert stays on your "
                                 "phone.")

    def act() -> dict[str, Any]:
        w = sb.worker(ctx.actor)
        first = w["name"].split()[0]
        if body.status == "needs_break":
            task = sb.ledger.create(
                action_code="CHECK_WORKER", zone=actions.worker_zone(sb, ctx.actor), now=sb.now(),
                rationale=f"{first}'s own wearable suggests a break and {first} chose to share this. Make sure "
                          f"{first} can rest in the shade now. No heart rate or other health value is shared.",
                rationale_ar=f"تقترح ساعة {first} الخاصة استراحة واختار {first} مشاركة ذلك. تأكد أن {first} "
                             "يستطيع الاستراحة في الظل الآن. لا يُشارك أي نبض أو قيمة صحية أخرى.",
                source="wearable_status", crew=w["crew"], affected=[ctx.actor])
            sb.ledger.notify(to_role="worker", to_actor=ctx.actor, at=sb.now(), template="msg.wearable_shared",
                             slots={}, task=task["id"])
            out = {"shared": "needs_break", "task": task["id"],
                   "message": content.render("msg.wearable_shared", ctx.lang)}
        else:
            buddy = w.get("buddy")
            if not buddy:
                raise HTTPException(409, "No buddy is set for you, so nothing was sent. Press Emergency if you need "
                                         "help.")
            n = sb.ledger.notify(to_role="worker", to_actor=buddy, at=sb.now(), template="msg.wearable_buddy",
                                 slots={"name": first})
            out = {"shared": "check_on_me", "notified": "buddy", "notification": n["id"]}
        sb.audit.append(at=sb.now(), actor=ctx.actor, role="worker", action=f"wearable.{body.status}",
                        resource=purpose, subject=ctx.actor, category="consent",
                        detail={"values_shared": "none"})
        return out

    return idempotent(ctx, idempotency_key, act)


# ---------------------------------------------------------- Kidney Passport
class PreviewIn(BaseModel):
    fields: list[str] = Field(default_factory=lambda: ["results", "referrals", "care_plan"])
    recipient_name: str = Field(default="My doctor", max_length=80)
    recipient_region: str = Field(default="AE", max_length=8)
    online: bool = True


EXPORTABLE = {"results", "referrals", "care_plan", "hydration", "exposure_context"}


@router.post("/exports/preview")
def export_preview(body: PreviewIn, ctx: Ctx = Depends(context)):
    ctx.require("self.export")
    sb = ctx.sb
    pid = pseudonym(ctx.actor)
    if pid not in sb.clinical.patients:
        raise HTTPException(404, "You have no care record to export.")
    fields = [f for f in body.fields if f in EXPORTABLE]
    gate = transfer_gate(sb, ctx.actor, body.recipient_region, body.online)
    bundle = fhir_bundle(sb.clinical, pid, fields, ctx.lang, sb.now())
    pv = {"id": "pv_" + secrets.token_hex(4), "worker_ref": ctx.actor, "fields": fields,
          "recipient": {"name": body.recipient_name, "region": body.recipient_region}, "gate": gate,
          "created_at": sb.now(), "bundle": bundle}
    sb.exports.append(pv)
    return {**pv, "notice": "Downloaded copies cannot be recalled." if ctx.lang == "en"
            else "لا يمكن استرجاع النسخ التي تم تنزيلها."}


def transfer_gate(sb, wid: str, region: str, online: bool) -> dict[str, Any]:
    """Export guard (B.6): current authority, consent, recipient region, online authorisation."""
    checks = []
    consent_ok = sb.consent.status(wid, "passport_sharing")["active"]
    checks.append({"check": "consent_passport_sharing", "ok": consent_ok})
    checks.append({"check": "online_authorisation", "ok": online,
                   "detail": None if online else "Export needs a current online authorisation (T40)."})
    domestic = region.upper() in ("AE", "UAE")
    checks.append({"check": "recipient_region", "ok": domestic,
                   "detail": None if domestic else "International transfer of health data needs a legal basis "
                                                   "review under UAE health-data rules; consent alone may not be "
                                                   "enough (GATE, §25.4). Worker-held copy only."})
    link_ok = consent_ok and online and domestic
    return {"checks": checks, "share_link_permitted": link_ok,
            "worker_held_copy_permitted": online,
            "decision": "permitted" if link_ok else ("worker_copy_only" if online else "deferred")}


class ExportIn(BaseModel):
    preview_id: str
    confirm: bool = False
    kind: str = "share_link"     # share_link | worker_copy


@router.post("/exports")
def export(body: ExportIn, ctx: Ctx = Depends(context)):
    ctx.require("self.export")
    sb = ctx.sb
    pv = next((p for p in sb.exports if p["id"] == body.preview_id and p["worker_ref"] == ctx.actor), None)
    if not pv or not body.confirm:
        raise HTTPException(422, "Preview and explicit confirmation are required.")
    gate = transfer_gate(sb, ctx.actor, pv["recipient"]["region"], True)
    if body.kind == "share_link":
        if not gate["share_link_permitted"]:
            sb.audit.append(at=sb.now(), actor=ctx.actor, role="worker", action="export.share_link",
                            resource=pv["id"], decision="denied", subject=ctx.actor, category="export",
                            reason=gate["decision"])
            raise HTTPException(409, "A share link is not permitted: " + "; ".join(
                c.get("detail") or c["check"] for c in gate["checks"] if not c["ok"]))
        token = secrets.token_urlsafe(12)
        code = f"{secrets.randbelow(10**6):06d}"
        expires = (datetime.fromisoformat(sb.now()) + timedelta(hours=72)).isoformat()
        sb.clinical.share_links[token] = {"token": token, "code": code, "worker_ref": ctx.actor,
                                          "expires_at": expires, "revoked": False, "bundle": pv["bundle"],
                                          "recipient": pv["recipient"], "sandbox": sb.id}
        _LINKS[token] = sb.clinical.share_links[token]
        sb.audit.append(at=sb.now(), actor=ctx.actor, role="worker", action="export.share_link",
                        resource=pv["id"], subject=ctx.actor, category="export")
        return {"kind": "share_link", "path": f"/passport/{token}", "passcode": code, "expires_at": expires,
                "notice": "Downloaded copies cannot be recalled."}
    sb.audit.append(at=sb.now(), actor=ctx.actor, role="worker", action="export.worker_copy", resource=pv["id"],
                    subject=ctx.actor, category="export")
    return {"kind": "worker_copy", "bundle": pv["bundle"], "notice": "Downloaded copies cannot be recalled."}


_LINKS: dict[str, dict[str, Any]] = {}


@router.get("/passport/{token}")
def passport_view(token: str, code: str):
    link = _LINKS.get(token)
    if not link or link["code"] != code:
        raise HTTPException(404, "Link or passcode not valid")
    if link["revoked"]:
        raise HTTPException(410, "The worker withdrew sharing; this link no longer works.")
    from ..core.sandbox import STORE
    sb = STORE.peek(link.get("sandbox", ""))
    if sb is None or token not in sb.clinical.share_links or sb.now() > link["expires_at"]:
        # The sandbox clock is the reference; a reset sandbox also ends its links.
        raise HTTPException(410, "This share link has expired.")
    return {"bundle": link["bundle"], "recipient": link["recipient"], "expires_at": link["expires_at"],
            "label": "SYNTHETIC care summary"}
