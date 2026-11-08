"""Clinical continuity store (finalsystem.md §12, §19.1, §23, B.9).

Separate from the operational store, with its own key and its own access path.
Employer roles can never call into this module; they only receive the minimal
operational projection (for example "clinic visit 14:00-16:00"), never a value,
a diagnosis or a reason (§8.6, §23.1, invariant 5).

All records are SYNTHETIC: "SYNTHETIC: not a real result".
"""
from __future__ import annotations

import hashlib
import itertools
import os
import secrets
from datetime import datetime, timedelta
from typing import Any

CLINICAL_KEY = os.environ.get("BARDAN_CLINICAL_KEY") or secrets.token_hex(32)   # separate key (§23.7)
SYNTH = "SYNTHETIC: not a real result"

CLINIC_PLACE = "Partner clinic (fictional), Musaffah"


def _clinic_sessions() -> list[dict[str, Any]]:
    """Synthetic partner-clinic sessions with named slots. Urgent slots are on the hour and half hour, the others
    at quarter past and quarter to. Slots already taken by patients from other sites are marked 'outside'."""
    def build(sid: str, day: str, start: str, end: str, urgent: int, routine: int, taken: dict[str, int]):
        t0 = datetime.fromisoformat(f"{day}T{start}:00+04:00")
        slots = []
        for cls, n, offset in (("urgent", urgent, 0), ("routine", routine, 15)):
            for k in range(n):
                st = t0 + timedelta(minutes=offset + 30 * k)
                slots.append({"class": cls, "start": st.isoformat(), "end": (st + timedelta(minutes=15)).isoformat(),
                              "taken_by": "outside" if k < taken.get(cls, 0) else None})
        slots.sort(key=lambda x: x["start"])
        return {"id": sid, "date": day, "start": start, "end": end, "place": CLINIC_PLACE, "slots": slots}
    return [build("s_0819_pm", "2025-08-19", "14:00", "16:00", 4, 4, {"urgent": 1, "routine": 3}),
            build("s_0820_am", "2025-08-20", "08:00", "12:00", 2, 8, {"routine": 5})]


REFERRAL_ALLOWED = {
    "offered": {"accepted", "declined"},
    "accepted": {"scheduled"},
    "scheduled": {"attended", "missed"},
    "missed": {"scheduled", "escalated"},
    "escalated": {"scheduled"},
    "attended": {"results_reviewed"},
    "results_reviewed": {"next_step_agreed"},
    "next_step_agreed": {"closed", "transferred"},
    "declined": set(), "closed": set(), "transferred": set(),
}

# Nurse hydration check: demonstration encoding of the guideline's action levels (Appendix C.5; VERIFY).
USG_LEVELS = [
    (1.000, 1.015, "normal", ["maintain_fluids"]),
    (1.016, 1.020, "slight", ["extra_fluids", "rehydrate_before_work"]),
    (1.021, 1.029, "moderate", ["rehydrate_before_work", "fluids_every_15_20_min"]),
    (1.030, 1.080, "significant", ["investigate", "remove_from_hot_work", "recheck_in_4h"]),
]
USG_LIMITS = {"start_of_shift": 1.015, "other": 1.029}


class ClinicalError(Exception):
    def __init__(self, code: str, message: str, status: int = 422):
        super().__init__(message)
        self.code = code
        self.status = status


def pseudonym(worker_ref: str) -> str:
    """Clinical identity is separate from the operational reference (§23.7)."""
    return "pt_" + hashlib.sha256((CLINICAL_KEY + worker_ref).encode()).hexdigest()[:8]


class ClinicalStore:
    def __init__(self) -> None:
        self.patients: dict[str, dict[str, Any]] = {}
        self.results: list[dict[str, Any]] = []
        self.incoming: list[dict[str, Any]] = []     # lab feed waiting for clinician import
        self.quarantine: list[dict[str, Any]] = []
        self.referrals: dict[str, dict[str, Any]] = {}
        self.hydration: list[dict[str, Any]] = []
        self.restrictions: dict[str, dict[str, Any]] = {}
        self.care_plans: dict[str, dict[str, Any]] = {}
        self.summaries: list[dict[str, Any]] = []
        self.projections: dict[str, dict[str, Any]] = {}   # operational projection per worker
        self.share_links: dict[str, dict[str, Any]] = {}
        self.sessions = _clinic_sessions()
        self._rid = itertools.count(1)
        self._hid = itertools.count(1)

    # ------------------------------------------------------------- fixtures
    def seed(self, workers: list[dict[str, Any]]) -> None:
        by_id = {w["id"]: w for w in workers}
        for wid, enrolled in (("W07", True), ("W01", False), ("W36", True)):
            w = by_id.get(wid)
            if not w:
                continue
            pid = pseudonym(wid)
            self.patients[pid] = {"patient_ref": pid, "worker_ref": wid, "name": w["name"], "lang": w["lang"],
                                  "year_of_birth": 2025 - int(w.get("age", 35)), "care_relationship": "S03",
                                  "kidney_pathway": "enrolled" if enrolled else "not_enrolled",
                                  "synthetic": True}
        anwar = pseudonym("W07")
        self.results.append({
            "id": "res_0001", "patient_ref": anwar, "analyte": "urine_acr", "label": "Urine albumin-to-creatinine ratio",
            "value": 22, "unit": "mg/g", "category": "A1", "specimen_at": "2025-02-10T07:40:00+04:00",
            "method": "Immunoturbidimetric (partner lab)", "lab": "Partner lab (fictional)",
            "verification": "verified", "verified_by": "S03", "reference_range": "< 30 mg/g",
            "context": "Annual screening, start of shift", "loinc": "9318-7", "note": SYNTH})
        self.results.append({
            "id": "res_0002", "patient_ref": anwar, "analyte": "egfr", "label": "eGFR (lab-reported)",
            "value": 88, "unit": "mL/min/1.73m2", "category": None, "specimen_at": "2025-07-28T07:35:00+04:00",
            "method": "Creatinine-based; equation as reported by the lab (CKD-EPI 2021)", "lab": "Partner lab (fictional)",
            "verification": "verified", "verified_by": "S03", "reference_range": "lab-specific",
            "context": "Repeat panel", "loinc": "98979-8", "note": SYNTH})
        # Lab feed: Anwar's new ACR waits for import (demo step), plus two traps.
        self.incoming = [
            {"id": "lab_0101", "claimed_name": "Anwar Hussain", "claimed_ref": anwar, "analyte": "urine_acr",
             "value": 64, "unit": "mg/g", "specimen_at": "2025-07-28T07:35:00+04:00",
             "method": "Immunoturbidimetric (partner lab)", "lab": "Partner lab (fictional)",
             "reference_range": "< 30 mg/g", "context": "Repeat screening, start of shift", "note": SYNTH},
            {"id": "lab_0102", "claimed_name": "Anwar Hossain", "claimed_ref": "pt_00000000", "analyte": "urine_acr",
             "value": 410, "unit": "mg/g", "specimen_at": "2025-08-02T08:10:00+04:00",
             "method": "Unknown", "lab": "External lab (fictional)", "reference_range": "", "context": "",
             "note": SYNTH},
            {"id": "lab_0103", "claimed_name": by_id["W36"]["name"], "claimed_ref": pseudonym("W36"), "analyte": "urine_acr",
             "value": 7.2, "unit": "mg/mmol", "specimen_at": "2025-08-05T07:50:00+04:00",
             "method": "Point-of-care device", "lab": "Mobile screening van (fictional)", "reference_range": "",
             "context": "Outreach screening", "note": SYNTH},
        ]
        # Failure demonstration: a referral missed because transport was unavailable (§32.3).
        bilal = pseudonym("W36")
        self.referrals["ref_0001"] = {
            "id": "ref_0001", "patient_ref": bilal, "worker_ref": "W36", "owner": "S03", "coordinator": "S04",
            "urgency": "routine", "reason_code": "repeat_screening", "state": "missed",
            "appointment": {"start": "2025-08-12T14:00:00+04:00", "end": "2025-08-12T16:00:00+04:00",
                            "place": "Partner clinic (fictional), Musaffah", "transport": "requested"},
            "history": [
                {"state": "offered", "at": "2025-08-05T10:00:00+04:00"},
                {"state": "accepted", "at": "2025-08-05T10:20:00+04:00"},
                {"state": "scheduled", "at": "2025-08-06T09:00:00+04:00"},
                {"state": "missed", "at": "2025-08-12T16:05:00+04:00", "reason": "transport_unavailable"},
            ],
            "note": SYNTH}
        self.projections["W36"] = {"worker_ref": "W36", "label_id": "msg.clinic_absence",
                                   "time_range": "14:00-16:00 (12 Aug, missed)", "status": "missed"}
        # Ravi: a past nurse hydration check, already resolved (history only).
        ravi = pseudonym("W01")
        self.hydration.append({"id": "hyd_0001", "patient_ref": ravi, "worker_ref": "W01", "operator": "S04",
                               "instrument": {"type": "digital_refractometer", "device_id": "REF-02",
                                              "calibration_checked": "2025-08-17"},
                               "reading": {"usg": 1.024, "entry": "display_photo_confirmed",
                                           "provenance": "measured"},
                               "timing": "start_of_shift", "at": "2025-08-18T05:20:00+04:00",
                               "action_level": "moderate",
                               "actions": ["hold_work_station_assignment", "rehydrate_before_work", "retest_due"],
                               "retest_due_at": "2025-08-18T06:20:00+04:00", "retest": {"usg": 1.012,
                               "at": "2025-08-18T06:25:00+04:00", "action_level": "normal"}, "note": SYNTH})

    # ------------------------------------------------------------- results
    def import_result(self, lab_id: str, *, actor: str, at: str) -> dict[str, Any]:
        item = next((x for x in self.incoming if x["id"] == lab_id), None)
        if not item:
            raise ClinicalError("not_found", "No such incoming result", 404)
        patient = self.patients.get(item["claimed_ref"])
        problems = []
        if not patient or patient["name"] != item["claimed_name"]:
            problems.append("identity_mismatch")
        if item["analyte"] == "urine_acr" and item["unit"] != "mg/g":
            problems.append("unexpected_unit")
        if not item.get("method") or item["method"] == "Unknown":
            problems.append("method_missing")
        if not isinstance(item.get("value"), (int, float)):
            problems.append("decimal_ambiguous")      # e.g. "6,4": never guessed (T58)
        try:
            if datetime.fromisoformat(str(item.get("specimen_at"))).tzinfo is None:
                problems.append("sample_time_ambiguous")
        except ValueError:
            problems.append("sample_time_ambiguous")
        self.incoming = [x for x in self.incoming if x["id"] != lab_id]
        if problems:
            q = {**item, "quarantined_at": at, "problems": problems, "state": "quarantined",
                 "explain": ("Quarantined, not attached to any worker. A clinician must reconcile identity, units "
                             "and method. Nothing is converted or classified automatically.")}
            self.quarantine.append(q)
            return {"status": "quarantined", "item": q}
        cat = acr_category(item["value"])
        res = {"id": f"res_{len(self.results) + 1:04d}", "patient_ref": item["claimed_ref"],
               "analyte": item["analyte"], "label": "Urine albumin-to-creatinine ratio", "value": item["value"],
               "unit": item["unit"], "category": cat, "specimen_at": item["specimen_at"], "method": item["method"],
               "lab": item["lab"], "verification": "verified", "verified_by": actor, "verified_at": at,
               "reference_range": item["reference_range"], "context": item["context"], "loinc": "9318-7",
               "note": SYNTH,
               "interpretation_note": ("Category shown for the clinician only. One result is not a diagnosis; "
                                       "confirmation and chronicity are needed (KDIGO).")}
        self.results.append(res)
        return {"status": "verified", "result": res}

    def results_for(self, patient_ref: str) -> list[dict[str, Any]]:
        return sorted([r for r in self.results if r["patient_ref"] == patient_ref], key=lambda r: r["specimen_at"])

    # ------------------------------------------------------------ referrals
    # -------------------------------------------------------------- capacity
    @property
    def capacity(self) -> dict[str, Any]:
        """Today's clinic session as counts (shown in the clinic queue)."""
        s = self.sessions[0]
        used = {c: sum(1 for x in s["slots"] if x["class"] == c and x["taken_by"]) for c in ("urgent", "routine")}
        total = {c: sum(1 for x in s["slots"] if x["class"] == c) for c in ("urgent", "routine")}
        return {"date": s["date"], "session": f"{s['start']}-{s['end']}", "urgent_slots": total["urgent"],
                "urgent_used": used["urgent"], "routine_slots": total["routine"], "routine_used": used["routine"]}

    def sessions_view(self) -> list[dict[str, Any]]:
        return [{"id": s["id"], "date": s["date"], "window": f"{s['start']}-{s['end']}", "place": s["place"],
                 "free": {c: sum(1 for x in s["slots"] if x["class"] == c and not x["taken_by"])
                          for c in ("urgent", "routine")}} for s in self.sessions]

    def _free_slot(self, urgency: str, at: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """The earliest free slot that fits the clinician's urgency: urgent = today only; soon = today or the next
        day; routine = any session. A slot that has already started is never offered."""
        cls = "urgent" if urgency == "urgent" else "routine"
        now = datetime.fromisoformat(at)
        for s in self.sessions:
            days = (datetime.fromisoformat(s["date"]).date() - now.date()).days
            if (urgency == "urgent" and days != 0) or (urgency == "soon" and days > 1) or days < 0:
                continue
            for slot in s["slots"]:
                if slot["class"] == cls and not slot["taken_by"] and datetime.fromisoformat(slot["start"]) >= now:
                    return s, slot
        return None

    def create_referral(self, *, patient_ref: str, worker_ref: str, urgency: str, actor: str, at: str,
                        reason_code: str = "repeat_and_review") -> dict[str, Any]:
        if urgency not in ("routine", "soon", "urgent"):
            raise ClinicalError("urgency", "Urgency must be routine, soon or urgent (set by the clinician).")
        if urgency == "urgent" and self._free_slot("urgent", at) is None:
            raise ClinicalError("capacity", "No urgent clinic capacity left today: the backlog is escalated to the "
                                            "clinical lead. No new referral is created quietly.", 409)
        rid = f"ref_{len(self.referrals) + 1:04d}"
        ref = {"id": rid, "patient_ref": patient_ref, "worker_ref": worker_ref, "owner": actor, "coordinator": "S04",
               "urgency": urgency, "reason_code": reason_code, "state": "offered", "appointment": None,
               "history": [{"state": "offered", "at": at, "by": actor}], "note": SYNTH}
        self.referrals[rid] = ref
        return ref

    def referral_event(self, rid: str, new_state: str, *, actor: str, at: str, appointment: dict | None = None,
                       reason: str | None = None) -> dict[str, Any]:
        ref = self.referrals.get(rid)
        if not ref:
            raise ClinicalError("not_found", "Referral not found", 404)
        if new_state not in REFERRAL_ALLOWED[ref["state"]]:
            raise ClinicalError("transition", f"A referral cannot move from {ref['state']} to {new_state}.")
        if new_state == "scheduled":
            if not appointment:
                raise ClinicalError("appointment", "Scheduling needs an appointment time and place.")
            # Capacity is enforced when the slot is taken, under the sandbox lock: two bookings can never share
            # one slot, and a full clinic is escalated, never overbooked (T60).
            found = self._free_slot(ref["urgency"], at)
            if found is None:
                raise ClinicalError("capacity", f"No {'urgent' if ref['urgency'] == 'urgent' else 'suitable'} "
                                                "clinic slot is free for this referral: it is escalated to the "
                                                "clinical lead. Nothing is booked twice.", 409)
            session, slot = found
            slot["taken_by"] = rid
            ref["appointment"] = {"start": slot["start"], "end": slot["end"], "session": session["id"],
                                  "place": session["place"], "transport": appointment.get("transport", "booked")}
            # The employer sees only the session window, never the slot, the reason or the urgency (§8.6).
            self.projections[ref["worker_ref"]] = {
                "worker_ref": ref["worker_ref"], "label_id": "msg.clinic_absence",
                "time_range": f"{session['start']}-{session['end']}", "date": session["date"],
                "status": "scheduled"}
        if new_state == "missed":
            self.projections[ref["worker_ref"]] = {**self.projections.get(ref["worker_ref"], {}), "status": "missed"}
        if new_state == "attended":
            self.projections[ref["worker_ref"]] = {**self.projections.get(ref["worker_ref"], {}), "status": "attended"}
        ref["state"] = new_state
        ref["history"].append({"state": new_state, "at": at, "by": actor, **({"reason": reason} if reason else {})})
        return ref

    # ------------------------------------------------------------ hydration
    def hydration_check(self, *, worker_ref: str, usg: float, timing: str, entry: str, actor: str, at: str,
                        device_id: str = "REF-02", symptoms: bool = False) -> dict[str, Any]:
        if not (1.000 <= usg <= 1.060):
            raise ClinicalError("implausible", f"A reading of {usg} is not a plausible urine specific gravity. "
                                               "Re-enter the value shown on the refractometer (for example 1.024).")
        level = next(lv for lv in USG_LEVELS if lv[0] <= round(usg, 3) <= lv[1])
        limit = USG_LIMITS["start_of_shift" if timing == "start_of_shift" else "other"]
        out_of_range = usg > limit
        actions = list(level[3])
        retest = None
        if out_of_range:
            # Failed test (C.5): hold the work-station assignment and retest until within the limit.
            actions = ["hold_work_station_assignment", *actions]
        if level[2] == "significant":
            retest = (datetime.fromisoformat(at) + timedelta(hours=4)).isoformat()   # table: recheck in 4 h
        elif out_of_range:
            actions.append("retest_due")
            retest = (datetime.fromisoformat(at) + timedelta(hours=1)).isoformat()   # failed test: after 1 h
        if out_of_range or level[2] == "significant":
            actions.append("clinician_review")   # clinical sign-off required (C.5); never an automatic clearance
        if symptoms:
            actions.append("refer_to_medical_centre")
        rec = {"id": f"hyd_{len(self.hydration) + 1:04d}", "patient_ref": pseudonym(worker_ref),
               "worker_ref": worker_ref, "operator": actor, "operator_role": "nurse",
               "instrument": {"type": "digital_refractometer", "device_id": device_id,
                              "calibration_checked": "2025-08-17"},
               "reading": {"usg": round(usg, 3), "entry": entry, "provenance": "measured"}, "timing": timing,
               "at": at, "policy_version": "AE-AD-HEAT@0.1.1-demo (C.5 demonstration encoding, VERIFY)",
               "action_level": level[2], "out_of_range": out_of_range, "actions": actions,
               "retest_due_at": retest, "note": SYNTH}
        self.hydration.append(rec)
        if out_of_range or level[2] == "significant":
            self.projections[worker_ref] = {"worker_ref": worker_ref, "label_id": "msg.at_clinic",
                                            "status": "at_clinic", "since": at}
        elif self.projections.get(worker_ref, {}).get("label_id") == "msg.at_clinic":
            self.projections.pop(worker_ref, None)
        return rec

    # ---------------------------------------------------------- restrictions
    def set_restriction(self, worker_ref: str, *, label: str, until: str, actor: str, at: str,
                        reason_private: str) -> dict[str, Any]:
        if label not in ("shaded_light_duty", "no_heat_work", "none"):
            raise ClinicalError("label", "Unknown restriction label")
        r = {"worker_ref": worker_ref, "label": label, "until": until, "set_by": actor, "at": at,
             "reason_private": reason_private}
        self.restrictions[worker_ref] = r
        return r

    def set_care_plan(self, worker_ref: str, *, fluid_restriction: bool, text: str, actor: str,
                      at: str) -> dict[str, Any]:
        pid = pseudonym(worker_ref)
        if pid not in self.patients:
            raise ClinicalError("not_found", "No clinical record for this worker", 404)
        cp = {"patient_ref": pid, "fluid_restriction": bool(fluid_restriction), "text": text[:400], "set_by": actor,
              "at": at, "note": SYNTH}
        self.care_plans[pid] = cp
        return cp

    def has_fluid_plan(self, worker_ref: str) -> bool:
        """True when the worker's own care plan sets individual fluid limits (T10). Never shown to employers."""
        cp = self.care_plans.get(pseudonym(worker_ref))
        return bool(cp and cp.get("fluid_restriction"))

    def operational_projection(self) -> list[dict[str, Any]]:
        """The ONLY clinical-derived data the employer side can read (§23.1)."""
        out = []
        for wref, p in self.projections.items():
            # Only what operations need now: an upcoming absence or "at clinic". A missed visit, its reason
            # and any outcome stay inside the clinical boundary (T59).
            if p.get("status") not in ("scheduled", "at_clinic"):
                continue
            out.append({k: v for k, v in p.items() if k in ("worker_ref", "label_id", "time_range", "date", "status",
                                                             "since")})
        for wref, r in self.restrictions.items():
            if r["label"] != "none":
                out.append({"worker_ref": wref, "label_id": "msg.restriction_label", "restriction": r["label"],
                            "until": r["until"]})
        return out


def acr_category(value: float) -> str:
    if value < 30:
        return "A1"
    if value <= 300:
        return "A2"
    return "A3"


def fhir_bundle(store: ClinicalStore, patient_ref: str, fields: list[str], lang: str, at: str) -> dict[str, Any]:
    """Minimal FHIR R4 document Bundle for the Kidney Passport (§12.8, §21.7). Not an IPS claim."""
    p = store.patients[patient_ref]
    entries: list[dict[str, Any]] = []
    pat = {"resourceType": "Patient", "id": patient_ref, "name": [{"text": p["name"]}],
           "communication": [{"language": {"coding": [{"system": "urn:ietf:bcp:47", "code": p["lang"]}]}}],
           "meta": {"tag": [{"code": "SYNTHETIC", "display": SYNTH}]}}
    entries.append(pat)
    obs_refs = []
    if "results" in fields:
        for r in store.results_for(patient_ref):
            oid = f"obs-{r['id']}"
            obs_refs.append({"reference": f"Observation/{oid}"})
            entries.append({
                "resourceType": "Observation", "id": oid, "status": "final",
                "code": {"coding": [{"system": "http://loinc.org", "code": r["loinc"], "display": r["label"]}],
                         "text": r["label"]},
                "subject": {"reference": f"Patient/{patient_ref}"}, "effectiveDateTime": r["specimen_at"],
                "valueQuantity": {"value": r["value"], "unit": r["unit"]}, "method": {"text": r["method"]},
                "performer": [{"display": r["lab"]}], "note": [{"text": SYNTH}],
                "meta": {"tag": [{"code": "LOINC-VERIFY", "display": "Code to be re-verified before real use"}]}})
    if "care_plan" in fields and patient_ref in store.care_plans:
        cp = store.care_plans[patient_ref]
        entries.append({"resourceType": "CarePlan", "id": f"cp-{patient_ref}", "status": "active", "intent": "plan",
                        "subject": {"reference": f"Patient/{patient_ref}"}, "description": cp.get("text", "")})
    if "referrals" in fields:
        for ref in store.referrals.values():
            if ref["patient_ref"] == patient_ref:
                entries.append({"resourceType": "ServiceRequest", "id": f"sr-{ref['id']}", "status": "active",
                                "intent": "order", "priority": ref["urgency"],
                                "subject": {"reference": f"Patient/{patient_ref}"},
                                "note": [{"text": f"State: {ref['state']}"}]})
    comp = {"resourceType": "Composition", "id": f"comp-{patient_ref}", "status": "final",
            "type": {"text": "Worker-held care summary (Kidney Passport)"}, "date": at,
            "subject": {"reference": f"Patient/{patient_ref}"}, "title": "Kidney Passport (SYNTHETIC)",
            "section": [{"title": "Results", "entry": obs_refs}]}
    bundle = {"resourceType": "Bundle", "type": "document", "timestamp": at,
              "identifier": {"value": f"passport-{patient_ref}-{at[:10]}"},
              "entry": [{"fullUrl": f"urn:uuid:{e['resourceType'].lower()}-{e['id']}", "resource": e}
                        for e in [comp, *entries]],
              "meta": {"tag": [{"code": "SYNTHETIC"}, {"code": "NOT-IPS", "display": "Plain factual summary, not an "
                                                                                    "International Patient Summary"}]}}
    return bundle
