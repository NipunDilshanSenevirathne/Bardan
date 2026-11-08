"""Clinical continuity workspace routes. Clinical roles only; every denial is audited (T34, T35)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..ai import extraction as extraction_mod
from ..core.clinical import ClinicalError, pseudonym
from .deps import Ctx, context

router = APIRouter(prefix="/v1/clinical")


def _clinical(ctx: Ctx, cap: str = "clinical.read", resource: str = "clinical", subject: str | None = None) -> None:
    ctx.require(cap, resource=resource, subject=subject)


@router.get("/queue")
def queue(ctx: Ctx = Depends(context)) -> dict[str, Any]:
    _clinical(ctx, resource="clinical/queue")
    sb = ctx.sb
    cs = sb.clinical
    names = {w["id"]: w["name"] for w in sb.world["workers"]}
    triage = []
    for c in sb.checkins:
        if not c["symptoms"]:
            continue
        shared = sb.consent.status(c["worker_ref"], "share_checkins_with_clinic")["active"]
        urgent_path = any(s in ("muscle_pain_dark_urine",) for s in c["symptoms"])
        if shared or urgent_path:
            triage.append({"worker_ref": c["worker_ref"], "name": names.get(c["worker_ref"]), "at": c["at"],
                           "symptoms": c["symptoms"], "basis": "shared check-in" if shared else "urgent assessment"})
        else:
            triage.append({"worker_ref": c["worker_ref"], "name": names.get(c["worker_ref"]), "at": c["at"],
                           "symptoms": None, "basis": "not shared by the worker (withdrawn or not granted)"})
    sb.audit.append(at=sb.now(), actor=ctx.actor, role=ctx.role, action="clinical.queue_read",
                    resource="clinical/queue", category="clinical")
    return {"incoming": cs.incoming, "quarantine": cs.quarantine, "triage": triage,
            "referrals": [{**r, "name": names.get(r["worker_ref"])} for r in cs.referrals.values()],
            "hydration": [{**h, "name": names.get(h["worker_ref"])} for h in cs.hydration],
            "capacity": cs.capacity, "sessions": cs.sessions_view(), "documents": extraction_mod.list_documents(),
            "patients": [{"worker_ref": p["worker_ref"], "name": p["name"], "pathway": p["kidney_pathway"]}
                         for p in cs.patients.values()], "label": "SYNTHETIC clinical records"}


@router.get("/patients/{worker_ref}")
def patient(worker_ref: str, ctx: Ctx = Depends(context)) -> dict[str, Any]:
    _clinical(ctx, resource=f"clinical/patients/{worker_ref}", subject=worker_ref)
    sb = ctx.sb
    pid = pseudonym(worker_ref)
    p = sb.clinical.patients.get(pid)
    if not p:
        raise HTTPException(404, "No clinical record")
    care = sb.consent.status(worker_ref, "clinical_care")
    if not care["active"]:
        sb.audit.append(at=sb.now(), actor=ctx.actor, role=ctx.role, action="clinical.read_patient",
                        resource=pid, subject=worker_ref, decision="denied", category="clinical",
                        reason="no active care consent")
        raise HTTPException(403, "No active care authorisation for this worker.")
    sb.audit.append(at=sb.now(), actor=ctx.actor, role=ctx.role, action="clinical.read_patient", resource=pid,
                    subject=worker_ref, category="clinical")
    return {"patient": p, "results": sb.clinical.results_for(pid),
            "referrals": [r for r in sb.clinical.referrals.values() if r["worker_ref"] == worker_ref],
            "hydration": [h for h in sb.clinical.hydration if h["worker_ref"] == worker_ref],
            "restriction": sb.clinical.restrictions.get(worker_ref),
            "care_plan": sb.clinical.care_plans.get(pid),
            "summaries": [s for s in sb.clinical.summaries if s["worker_ref"] == worker_ref],
            "checkins_shared": sb.consent.status(worker_ref, "share_checkins_with_clinic")["active"],
            "consents": sb.consent.summary(worker_ref)}


class ImportIn(BaseModel):
    lab_id: str


@router.post("/results/import")
def import_result(body: ImportIn, ctx: Ctx = Depends(context)):
    _clinical(ctx, "clinical.verify", resource="clinical/results")
    sb = ctx.sb
    try:
        r = sb.clinical.import_result(body.lab_id, actor=ctx.actor, at=sb.now())
    except ClinicalError as e:
        raise HTTPException(e.status, str(e)) from e
    sb.audit.append(at=sb.now(), actor=ctx.actor, role=ctx.role, action=f"clinical.result_{r['status']}",
                    resource=body.lab_id, category="clinical")
    return r


class ReferralIn(BaseModel):
    worker_ref: str
    urgency: str
    reason_code: str = "repeat_and_review"


@router.post("/referrals")
def referral(body: ReferralIn, ctx: Ctx = Depends(context)):
    _clinical(ctx, "clinical.referral", resource="clinical/referrals", subject=body.worker_ref)
    sb = ctx.sb
    try:
        with sb.lock:
            r = sb.clinical.create_referral(patient_ref=pseudonym(body.worker_ref), worker_ref=body.worker_ref,
                                            urgency=body.urgency, actor=ctx.actor, at=sb.now(),
                                            reason_code=body.reason_code)
    except ClinicalError as e:
        if e.code == "capacity":
            sb.audit.append(at=sb.now(), actor=ctx.actor, role=ctx.role, action="clinical.capacity_escalated",
                            resource="clinical/referrals", subject=body.worker_ref, category="clinical",
                            decision="denied", reason="no urgent capacity today: escalated to the clinical lead")
        raise HTTPException(e.status, str(e)) from e
    sb.audit.append(at=sb.now(), actor=ctx.actor, role=ctx.role, action="clinical.referral_created",
                    resource=r["id"], subject=body.worker_ref, category="clinical")
    return r


class ReferralEventIn(BaseModel):
    state: str
    appointment: dict[str, Any] | None = None
    reason: str | None = Field(default=None, max_length=200)


@router.post("/referrals/{rid}/events")
def referral_event(rid: str, body: ReferralEventIn, ctx: Ctx = Depends(context)):
    cap = "clinical.referral_coordinate" if ctx.role == "nurse" else "clinical.referral"
    _clinical(ctx, cap, resource=f"clinical/referrals/{rid}")
    sb = ctx.sb
    try:
        with sb.lock:     # check-and-book is one step: two requests can never take the same slot
            r = sb.clinical.referral_event(rid, body.state, actor=ctx.actor, at=sb.now(),
                                           appointment=body.appointment, reason=body.reason)
    except ClinicalError as e:
        if e.code == "capacity":
            sb.audit.append(at=sb.now(), actor=ctx.actor, role=ctx.role, action="clinical.capacity_escalated",
                            resource=f"clinical/referrals/{rid}", category="clinical", decision="denied",
                            reason="no free slot: escalated to the clinical lead, nothing double-booked")
        raise HTTPException(e.status, str(e)) from e
    if body.state == "missed":
        # Coordinator follow-up; the employer is never told the reason (T59).
        sb.ledger.create(action_code="CLINIC_TRANSPORT", zone=None, now=sb.now(),
                         rationale="Arrange transport for a rescheduled clinic visit (no clinical detail).",
                         rationale_ar="ترتيب النقل لزيارة عيادة أُعيدت جدولتها (دون أي تفاصيل طبية).",
                         source="clinical_coordination", affected=[r["worker_ref"]])
    sb.audit.append(at=sb.now(), actor=ctx.actor, role=ctx.role, action=f"clinical.referral_{body.state}",
                    resource=rid, subject=r["worker_ref"], category="clinical")
    return r


class HydrationIn(BaseModel):
    worker_ref: str
    usg: float
    timing: str = "start_of_shift"
    entry: str = "typed"
    symptoms: bool = False


@router.post("/hydration-checks")
def hydration(body: HydrationIn, ctx: Ctx = Depends(context)):
    _clinical(ctx, "clinical.hydration", resource="clinical/hydration", subject=body.worker_ref)
    sb = ctx.sb
    try:
        r = sb.clinical.hydration_check(worker_ref=body.worker_ref, usg=body.usg, timing=body.timing,
                                        entry=body.entry, actor=ctx.actor, at=sb.now(), symptoms=body.symptoms)
    except ClinicalError as e:
        raise HTTPException(e.status, str(e)) from e
    sb.audit.append(at=sb.now(), actor=ctx.actor, role=ctx.role, action="clinical.hydration_check",
                    resource=r["id"], subject=body.worker_ref, category="clinical")
    return r


class RestrictionIn(BaseModel):
    worker_ref: str
    label: str
    until: str
    reason_private: str = Field(..., max_length=200)


@router.post("/restrictions")
def restriction(body: RestrictionIn, ctx: Ctx = Depends(context)):
    _clinical(ctx, "clinical.restriction", resource="clinical/restrictions", subject=body.worker_ref)
    sb = ctx.sb
    try:
        r = sb.clinical.set_restriction(body.worker_ref, label=body.label, until=body.until, actor=ctx.actor,
                                        at=sb.now(), reason_private=body.reason_private)
    except ClinicalError as e:
        raise HTTPException(e.status, str(e)) from e
    sb.audit.append(at=sb.now(), actor=ctx.actor, role=ctx.role, action="clinical.restriction_set",
                    resource=body.worker_ref, subject=body.worker_ref, category="clinical")
    return {k: v for k, v in r.items()}


class CarePlanIn(BaseModel):
    worker_ref: str
    fluid_restriction: bool = False
    text: str = Field(default="", max_length=400)


@router.post("/care-plans")
def care_plan(body: CarePlanIn, ctx: Ctx = Depends(context)):
    """Individual care plan (clinician only). A fluid plan replaces general drinking advice everywhere (T10)."""
    _clinical(ctx, "clinical.write", resource="clinical/care_plans", subject=body.worker_ref)
    sb = ctx.sb
    try:
        cp = sb.clinical.set_care_plan(body.worker_ref, fluid_restriction=body.fluid_restriction, text=body.text,
                                       actor=ctx.actor, at=sb.now())
    except ClinicalError as e:
        raise HTTPException(e.status, str(e)) from e
    sb.audit.append(at=sb.now(), actor=ctx.actor, role=ctx.role, action="clinical.care_plan_set",
                    resource=body.worker_ref, subject=body.worker_ref, category="clinical")
    return cp


class ExtractIn(BaseModel):
    doc_id: str
    worker_ref: str


@router.post("/documents/extract")
def extract(body: ExtractIn, ctx: Ctx = Depends(context)):
    _clinical(ctx, "clinical.document_ai", resource="clinical/documents", subject=body.worker_ref)
    sb = ctx.sb
    name = next((w["name"] for w in sb.world["workers"] if w["id"] == body.worker_ref), "")
    try:
        r = extraction_mod.extract(body.doc_id, expected_worker=body.worker_ref, expected_name=name,
                                   ai_on=sb.ai_enabled("document"))
    except KeyError as e:
        raise HTTPException(404, "Unknown document") from e
    run = sb.record_trace({**r.pop("run"), "actor": ctx.actor, "input_ref": body.doc_id})
    if r["status"] == "quarantined":
        sb.clinical.quarantine.append({"id": body.doc_id, "claimed_name": r["fields"].get("patient_name"),
                                       "problems": r["problems"], "state": "quarantined", "quarantined_at": sb.now(),
                                       "explain": "Quarantined by document checks; a clinician must reconcile."})
    return {**r, "trace_id": run["id"]}


@router.get("/documents/{doc_id}/image")
def document_image(doc_id: str, ctx: Ctx = Depends(context)):
    """The scanned synthetic lab report, served only inside the clinical boundary (no public URL)."""
    _clinical(ctx, resource=f"clinical/documents/{doc_id}")
    if doc_id not in {d["id"] for d in extraction_mod.list_documents()}:
        raise HTTPException(404, "Unknown document")
    path = extraction_mod.DOCS / f"{doc_id}.png"
    if not path.exists():
        raise HTTPException(404, "No image for this document")
    ctx.sb.audit.append(at=ctx.sb.now(), actor=ctx.actor, role=ctx.role, action="clinical.document_viewed",
                        resource=doc_id, category="clinical")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, no-store"})


class SummaryIn(BaseModel):
    worker_ref: str
    note: str = Field(..., min_length=10, max_length=1200)
    lang: str = "ar"


@router.post("/summaries/draft")
def draft_summary(body: SummaryIn, ctx: Ctx = Depends(context)):
    _clinical(ctx, "clinical.summary_approve", resource="clinical/summaries", subject=body.worker_ref)
    sb = ctx.sb
    r = extraction_mod.draft_summary(body.note, lang=body.lang if body.lang in ("en", "ar") else "en",
                                     ai_on=sb.ai_enabled("document"))
    run = sb.record_trace({**r.pop("run"), "actor": ctx.actor, "input_ref": "clinician_note"})
    sid = f"sum_{len(sb.clinical.summaries) + 1:03d}"
    rec = {"id": sid, "worker_ref": body.worker_ref, "note": body.note, "lang": body.lang, **r,
           "status": r["status"], "trace_id": run["id"]}
    sb.clinical.summaries.append(rec)
    return rec


class SummaryApproveIn(BaseModel):
    text: str | None = Field(default=None, min_length=10, max_length=1200)


@router.post("/summaries/{sid}/approve")
def approve_summary(sid: str, body: SummaryApproveIn | None = None, ctx: Ctx = Depends(context)):
    """Approve the drafted summary, or (when AI is off or unavailable) the clinician's own written text."""
    _clinical(ctx, "clinical.summary_approve", resource=f"clinical/summaries/{sid}")
    s = next((x for x in ctx.sb.clinical.summaries if x["id"] == sid), None)
    if s and not s.get("summary") and body and body.text:
        s["summary"] = body.text.strip()
        s["source"] = "clinician_written"
        s["back_translation"] = None
        s["discrepancies"] = []
    if not s or not s.get("summary"):
        raise HTTPException(404, "Nothing to approve")
    if s["status"] == "flagged_for_clinician" and not s.get("reviewed"):
        s["reviewed"] = True
    s["status"] = "approved"
    s["approved_by"] = ctx.actor
    ctx.sb.audit.append(at=ctx.sb.now(), actor=ctx.actor, role=ctx.role, action="clinical.summary_approved",
                        resource=sid, subject=s["worker_ref"], category="clinical")
    return s


@router.get("/export/bulk")
def bulk_export(ctx: Ctx = Depends(context)):
    """Always denied outside an expressly authorised clinical purpose (T35)."""
    ctx.sb.audit.append(at=ctx.sb.now(), actor=ctx.actor, role=ctx.role, action="clinical.bulk_export",
                        resource="clinical/*", decision="denied", category="clinical",
                        reason="bulk health roster export is never available")
    raise HTTPException(403, "Bulk health roster export is not available to any role. The attempt was audited.")
