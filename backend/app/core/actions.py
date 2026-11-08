"""Worker-side actions turned into protection events (finalsystem.md §8.3-§8.4, §11, §12.3, Appendix F).

Reports become operational tasks; symptoms stay private and leave only a
minimal operational projection ("check on a worker", never the symptom).
Urgent symptoms always open the emergency path first, with no model involved.
"""
from __future__ import annotations

from typing import Any

from . import content, policy
from .clinical import pseudonym

RESOURCE_TASK = {
    "RESOURCE_WATER_UNAVAILABLE": ("WATER_RESTORE", "Water point reported empty by a worker. Heat work in the zone "
                                                    "stops until water is restored and verified (AE-AD-HEAT).", False),
    "RESOURCE_SHADE_FULL": ("SHADE_EXTEND", "Shaded rest area reported full. Open capacity or stagger breaks.", False),
    "RESOURCE_COOLING_BROKEN": ("COOLING_FIX", "Cooling equipment reported not working.", False),
    "CANNOT_TAKE_BREAK": ("BREAK_ACCESS", "A worker reported they cannot take a required break (private report).",
                          True),
    "AC_BROKEN_HOUSING": ("AC_FIX", "Accommodation air conditioning reported broken. Labour accommodation must be "
                                    "air-conditioned. The reporter is not named.", True),
}
RESOURCE_TASK_AR = {
    "RESOURCE_WATER_UNAVAILABLE": "أبلغ عامل أن نقطة الماء فارغة. يتوقف العمل في الحر في المنطقة حتى يُعاد توفير الماء "
                                  "ويُتحقق منه (AE-AD-HEAT).",
    "RESOURCE_SHADE_FULL": "أُبلغ أن مكان الراحة المظلل ممتلئ. وفّر سعة إضافية أو وزّع الاستراحات.",
    "RESOURCE_COOLING_BROKEN": "أُبلغ أن معدات التبريد لا تعمل.",
    "CANNOT_TAKE_BREAK": "أبلغ عامل أنه لا يستطيع أخذ استراحة مطلوبة (بلاغ خاص).",
    "AC_BROKEN_HOUSING": "أُبلغ أن تكييف السكن معطل. يجب أن يكون سكن العمال مكيفاً. لا يُذكر اسم المُبلّغ.",
}
SYMPTOM_OF_INTENT = {k: v["symptom"] for k, v in content.INTENTS.items() if v.get("symptom")}


def worker_zone(sb, wid: str) -> str:
    w = sb.worker(wid)
    crew = next(c for c in sb.world["crews"] if c["id"] == w["crew"])
    return crew["zone"]


WORKER_TASK_CODES = ("WATER_RESTORE", "SHADE_EXTEND", "COOLING_FIX", "BREAK_ACCESS", "MOVE_TO_SHADED_TASK",
                     "ENHANCED_SCHEDULE")
PERSONAL_TASK_CODES = {"MOVE_TO_SHADED_TASK", "BREAK_ACCESS"}


def task_concerns_worker(sb, task: dict[str, Any], wid: str) -> bool:
    """The protections a worker is shown, and so the only ones they can confirm or dispute: tasks that name them,
    tasks they reported, and their own crew's or zone's shared protection. Another worker's personal task (a move
    to shade, say) is never shown to colleagues or open to their dispute."""
    if task["action_code"] not in WORKER_TASK_CODES:
        return False
    if wid in (task.get("affected_workers") or []) or task.get("reporter_ref") == wid:
        return True
    if task["action_code"] in PERSONAL_TASK_CODES:
        return False
    w = sb.worker(wid)
    if task.get("crew"):
        return task["crew"] == w["crew"]
    return bool(task.get("zone_id")) and task["zone_id"] == worker_zone(sb, wid)


def report_resource(sb, wid: str, intent: str, zone: str | None = None, via: str = "icon") -> dict[str, Any]:
    code, rationale, hidden = RESOURCE_TASK[intent]
    w = sb.worker(wid)
    zone = zone or worker_zone(sb, wid)
    # In a drill sandbox, each Bardan drill gets its own task: an earlier drill's task never absorbs a new report.
    series = getattr(sb, "drills", None)
    running = series.running() if series is not None else None
    drill_id = running["id"] if running and running["arm"] == "bardan" and running["control"] == code else None
    # One open task per resource and zone: duplicates attach as confirmations, never a second task.
    for t in sb.ledger.tasks.values():
        if t["action_code"] == code and t["zone_id"] == zone and t["state"] not in ("verified", "cancelled") \
                and t.get("drill") == drill_id:
            t.setdefault("reports", []).append({"at": sb.now(), "via": via})
            sb.audit.append(at=sb.now(), actor=wid, role="worker", action="report.duplicate", resource=t["id"])
            return {"task": t, "duplicate": True, "message": _ack(intent, zone, w["lang"])}
    task = sb.ledger.create(action_code=code, zone=zone, now=sb.now(), rationale=rationale,
                            rationale_ar=RESOURCE_TASK_AR.get(intent),
                            source=f"worker_report:{via}", crew=w["crew"], reporter_hidden=hidden,
                            extra={"reporter_ref": wid if not hidden else None,
                                   "reports": [{"at": sb.now(), "via": via}], "drill": drill_id})
    if drill_id:
        series.link_task(task)
    sb.reports.append({"at": sb.now(), "intent": intent, "zone": zone, "task": task["id"], "via": via,
                       "reporter_hidden": hidden})
    sb.audit.append(at=sb.now(), actor=wid if not hidden else "anonymous", role="worker", action="report.created",
                    resource=task["id"], detail={"intent": intent, "zone": zone})
    return {"task": task, "duplicate": False, "message": _ack(intent, zone, w["lang"])}


def _ack(intent: str, zone: str, lang: str) -> dict[str, Any]:
    if intent == "RESOURCE_WATER_UNAVAILABLE":
        tid, slots = "msg.water_task_created", {"zone": zone}
    elif intent == "AC_BROKEN_HOUSING":
        tid, slots = "msg.ac_broken_ack", {}
    elif intent == "CANNOT_TAKE_BREAK":
        tid, slots = "msg.dispute_received", {"role": "HSE" if lang == "en" else "مسؤول السلامة"}
    else:
        tid, slots = "msg.report_received", {"zone": zone}
    return {"template_id": tid, "text": content.render(tid, lang, **slots)}


def checkin(sb, wid: str, symptoms: list[str], *, kind: str = "quick", preferences: dict | None = None,
            via: str = "icons", about: str = "self") -> dict[str, Any]:
    """Private check-in. Symptoms stay in the worker store; the supervisor only sees 'check on a worker'."""
    pack = policy.heat_pack()
    urgent = [s for s in symptoms if s in pack["urgent_symptoms"]]
    concerning = [s for s in symptoms if s in pack["concerning_symptoms"]]
    rec = {"id": f"chk_{len(sb.checkins) + 1:04d}", "worker_ref": wid, "at": sb.now(), "kind": kind,
           "symptoms": symptoms, "preferences": preferences or {}, "via": via, "about": about}
    sb.checkins.append(rec)
    out: dict[str, Any] = {"checkin": rec["id"], "urgent": bool(urgent), "concerning": bool(concerning)}
    w = sb.worker(wid)
    if urgent:
        ev = {"id": f"emg_{len(sb.emergencies) + 1:03d}", "subject": wid, "reported_by": wid if about == "self"
              else f"buddy_of:{wid}", "symptoms": urgent, "at": sb.now(),
              "states": [{"state": "card_opened", "device_time": None, "server_time": sb.now(), "offline": False}],
              "closed": False, "location": {"zone": worker_zone(sb, wid)}}
        sb.emergencies.append(ev)
        sb.ledger.create(action_code="CHECK_WORKER", zone=worker_zone(sb, wid), now=sb.now(),
                         rationale="Emergency card opened on site. Location and time only (incident response).",
                         rationale_ar="فُتحت بطاقة الطوارئ في الموقع. الموقع والوقت فقط (للاستجابة للحادث).",
                         source="emergency", crew=w["crew"], affected=[wid], extra={"emergency": ev["id"]})
        out["emergency"] = ev
        out["message"] = {"template_id": "msg.emergency", "text": content.render("msg.emergency", w["lang"])}
    elif concerning:
        sb.ledger.create(action_code="CHECK_WORKER", zone=worker_zone(sb, wid), now=sb.now(),
                         rationale="A worker asked for a check. Stop the activity, cool down, buddy or first aider "
                                   "assessment. The reason stays private.", source="private_checkin",
                         rationale_ar="طلب عامل أن يتم تفقده. أوقف النشاط، وبرّد الجسم، وليقيّمه الزميل أو المسعف. "
                                      "يبقى السبب خاصاً.",
                         crew=w["crew"], affected=[wid])
        mid = "msg.muscle_dark_urine" if "muscle_pain_dark_urine" in concerning else "msg.concerning_symptom"
        out["message"] = {"template_id": mid, "text": content.render(mid, w["lang"])}
        if "muscle_pain_dark_urine" in concerning:
            sb.clinical.projections[wid] = {"worker_ref": wid, "label_id": "msg.at_clinic", "status": "at_clinic",
                                            "since": sb.now()}
            out["urgent_clinical_assessment"] = True
    if (preferences or {}).get("ac_broken"):
        out["housing"] = report_resource(sb, wid, "AC_BROKEN_HOUSING", via="evening_checkin")
    if (preferences or {}).get("pain_tablets"):
        out["medicine_info"] = {"template_id": "msg.medicine_info",
                                "text": content.render("msg.medicine_info", w["lang"])}
    if (preferences or {}).get("fasting"):
        out["fasting_info"] = {"template_id": "msg.fasting_info", "text": content.render("msg.fasting_info",
                                                                                          w["lang"])}
    shared = sb.consent.status(wid, "share_checkins_with_clinic")["active"]
    out["shared_with_nurse"] = shared
    sb.audit.append(at=sb.now(), actor=wid, role="worker", action="checkin.private", resource=rec["id"],
                    subject=wid, category="clinical" if symptoms else "operational",
                    detail={"shared_with_nurse": shared, "count": len(symptoms)})
    return out


def confirm_intake(sb, wid: str, draft: dict[str, Any], confirmed: list[dict[str, Any]]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    symptoms, about = [], "self"
    for c in confirmed:
        intent, pol = c["intent"], c.get("polarity", "affirmed")
        if pol != "affirmed":
            continue
        meta = content.INTENTS[intent]
        if c.get("about") == "other_person":
            about = "other_person"
        if meta.get("symptom"):
            symptoms.append(meta["symptom"])
        elif intent in RESOURCE_TASK:
            results.append({"intent": intent, **report_resource(sb, wid, intent, via="voice_or_text")})
        elif intent == "HELP_REQUEST":
            sb.ledger.create(action_code="CHECK_WORKER", zone=worker_zone(sb, wid), now=sb.now(),
                             rationale="A worker pressed 'I need help'.", source="help_button",
                             rationale_ar="ضغط عامل على «أحتاج مساعدة».",
                             crew=sb.worker(wid)["crew"], affected=[wid])
            results.append({"intent": intent, "message": "help_requested"})
    chk = checkin(sb, wid, symptoms, via="voice_or_text", about=about) if symptoms else None
    draft["confirmed"] = confirmed
    draft["confirmed_at"] = sb.now()
    return {"resources": results, "checkin": chk}


def emergency_event(sb, wid: str, ev: dict[str, Any]) -> dict[str, Any]:
    """Honest communication states (invariant 8): dialler opened != help received."""
    allowed = {"card_opened", "dialler_opened", "message_queued", "message_delivered", "help_received", "closed"}
    if ev.get("kind") not in allowed:
        raise ValueError("unknown emergency state")
    key = f"emg:{ev.get('event_id')}"
    if ev.get("event_id") and key in sb.sync_acks:
        return {**sb.sync_acks[key], "duplicate": True}
    subject = ev.get("subject") or wid
    rec = next((e for e in sb.emergencies if e["subject"] == subject and not e["closed"]), None)
    if rec is None:
        rec = {"id": f"emg_{len(sb.emergencies) + 1:03d}", "subject": subject, "reported_by": wid,
               "symptoms": ev.get("symptoms", []), "at": ev.get("device_time") or sb.now(), "states": [],
               "closed": False, "location": {"zone": worker_zone(sb, subject) if subject.startswith("W") else None},
               "offline_origin": bool(ev.get("offline")), "received_at": sb.now(), "acknowledged": None}
        sb.emergencies.append(rec)
        t = sb.ledger.create(action_code="CHECK_WORKER", zone=rec["location"]["zone"], now=sb.now(),
                             rationale="Emergency card used. Location and time are shared for the response.",
                             rationale_ar="استُخدمت بطاقة الطوارئ. يُشارك الموقع والوقت لأجل الاستجابة.",
                             source="emergency", affected=[subject], extra={"emergency": rec["id"]})
        rec["task"] = t["id"]
    rec["states"].append({"state": ev["kind"], "device_time": ev.get("device_time"), "server_time": sb.now(),
                          "offline": bool(ev.get("offline"))})
    if ev["kind"] == "closed":
        rec["closed"] = True
    sb.audit.append(at=sb.now(), actor=wid, role="worker", action=f"emergency.{ev['kind']}", resource=rec["id"],
                    subject=subject, category="operational")
    # "received" means the Bardan server has the event, nothing more; "acknowledged" needs a person (below).
    ack = {"ack": True, "emergency": rec["id"], "state": ev["kind"], "received_by_server_at": sb.now()}
    if ev.get("event_id"):
        sb.sync_acks[key] = ack
    return ack


def acknowledge_emergency(sb, emergency_id: str, *, actor: str, role: str) -> dict[str, Any]:
    """A responder on the site team says they have seen the alert and are acting. Only this counts as the site team
    having the alert; the phone shows it as 'seen by the site team' with the role and time (invariant 8)."""
    rec = next((e for e in sb.emergencies if e["id"] == emergency_id), None)
    if rec is None:
        raise KeyError(emergency_id)
    if not rec.get("acknowledged"):
        rec["acknowledged"] = {"at": sb.now(), "role": role, "actor": actor}
        rec["states"].append({"state": "acknowledged", "device_time": None, "server_time": sb.now(), "role": role})
        sb.audit.append(at=sb.now(), actor=actor, role=role, action="emergency.acknowledged", resource=rec["id"],
                        subject=rec["subject"], category="operational")
        task = sb.ledger.tasks.get(rec.get("task", ""))
        if task and task["state"] in ("assigned", "escalated") and role in ("supervisor", "hse"):
            sb.ledger.transition(task["id"], "accepted", actor=actor, role=role, at=sb.now(),
                                 reason="responder acknowledged the emergency alert")
    return emergency_status(sb, rec)


def emergency_status(sb, rec: dict[str, Any]) -> dict[str, Any]:
    ack = rec.get("acknowledged")
    help_at = next((s["server_time"] for s in rec["states"] if s["state"] == "help_received"), None)
    return {"id": rec["id"], "received_by_server_at": rec.get("received_at"),
            "acknowledged": {"at": ack["at"], "role": ack["role"]} if ack else None,
            "help_received_at": help_at, "closed": rec["closed"], "zone": rec["location"].get("zone")}


def patient_ref(wid: str) -> str:
    return pseudonym(wid)
