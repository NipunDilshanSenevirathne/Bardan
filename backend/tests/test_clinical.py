"""Clinical continuity: lab import, referrals, nurse hydration checks, restrictions and summaries (T57-T63)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.ai import gate as G
from app.core.clinical import ClinicalError, ClinicalStore, acr_category, pseudonym


@pytest.fixture
def store(sandbox) -> ClinicalStore:
    return sandbox.clinical


@pytest.mark.tcase("T57")
def test_lab_result_for_another_identity_is_quarantined(site):
    """A result claiming a different identity is quarantined, never attached to any worker."""
    fatima = site.as_("fatima")
    r = fatima.post("/v1/clinical/results/import", {"lab_id": "lab_0102"}).json()
    assert r["status"] == "quarantined" and "identity_mismatch" in r["item"]["problems"]
    pid = pseudonym("W07")
    assert all(x["value"] != 410 for x in site.sb.clinical.results_for(pid))


@pytest.mark.tcase("T58")
def test_ambiguous_units_decimal_or_sample_time_stay_unverified(store):
    """mg/mmol, a decimal comma or a sample time without an offset: unverified, no automatic category."""
    r = store.import_result("lab_0103", actor="S03", at="2025-08-19T14:10:00+04:00")
    assert r["status"] == "quarantined" and "unexpected_unit" in r["item"]["problems"]
    assert "category" not in r["item"]
    store.incoming.append({"id": "lab_x", "claimed_name": "Anwar Hussain", "claimed_ref": pseudonym("W07"),
                           "analyte": "urine_acr", "value": "6,4", "unit": "mg/g", "specimen_at": "2025-08-10 07:40",
                           "method": "Immunoturbidimetric", "lab": "Fictional", "reference_range": "", "context": ""})
    r2 = store.import_result("lab_x", actor="S03", at="2025-08-19T14:10:00+04:00")
    assert r2["status"] == "quarantined"
    assert {"decimal_ambiguous", "sample_time_ambiguous"} <= set(r2["item"]["problems"])


def test_matching_result_is_verified_and_categorised_for_the_clinician_only(site):
    """A clean result is verified with its category for the clinician; the worker sees 'needs a clinician'."""
    r = site.as_("fatima").post("/v1/clinical/results/import", {"lab_id": "lab_0101"}).json()
    assert r["status"] == "verified" and r["result"]["category"] == acr_category(64) == "A2"
    me = site.as_("anwar").get("/v1/worker/health").json()
    assert any(x["value"] == 64 for x in me["results"]) and me["result_message"]
    assert "A2" not in str(me["results"])          # the category stays with the clinician


@pytest.mark.tcase("T60")
def test_urgent_referral_without_capacity_is_escalated_not_queued(store):
    """No urgent clinic capacity: the request is escalated to the clinical lead; nothing waits silently."""
    for slot in store.sessions[0]["slots"]:
        if slot["class"] == "urgent":
            slot["taken_by"] = "outside"
    with pytest.raises(ClinicalError) as e:
        store.create_referral(patient_ref=pseudonym("W07"), worker_ref="W07", urgency="urgent", actor="S03",
                              at="2025-08-19T14:00:00+04:00")
    assert e.value.status == 409 and "escalated to the clinical lead" in str(e.value)
    ref = store.referrals["ref_0001"]
    store.referral_event("ref_0001", "escalated", actor="S04", at="2025-08-19T14:10:00+04:00",
                         reason="transport_unavailable")
    assert ref["state"] == "escalated" and ref["history"][-1]["by"] == "S04"


@pytest.mark.tcase("T61")
@pytest.mark.parametrize("text,lang", [("You are cleared to return to work.", "en"),
                                       ("You are fit for work again.", "en"),
                                       ("أنت لائق للعمل الآن.", "ar")])
def test_no_algorithmic_clearance_after_illness(text, lang):
    """Return after illness needs an authorised return plan: any 'fit' or 'cleared' wording is blocked."""
    g = G.check({"text": text}, lang=lang)
    assert g["decision"] == "blocked" and any(r["rule"] == "forbidden_claim.fitness" for r in g["reasons"])


@pytest.mark.tcase("T62")
def test_nurse_check_1031_at_shift_start_holds_and_removes_from_hot_work(site):
    """USG 1.031 at the start of a shift: hold, remove from hot work, retest timer from the table, clinician."""
    mariam = site.as_("mariam")
    r = mariam.post("/v1/clinical/hydration-checks", {"worker_ref": "W01", "usg": 1.031,
                                                     "timing": "start_of_shift", "entry": "display_photo_confirmed"})
    assert r.status_code == 200, r.text
    rec = r.json()
    assert rec["action_level"] == "significant"
    for a in ("hold_work_station_assignment", "remove_from_hot_work", "recheck_in_4h", "clinician_review"):
        assert a in rec["actions"]
    assert rec["retest_due_at"] == (datetime.fromisoformat(site.sb.now()) + timedelta(hours=4)).isoformat()
    ops = site.sup.get("/v1/sites/site_demo/operations").json()
    label = next(x for x in ops["operational_labels"] if x["worker"] == "W01")
    assert "1.031" not in label["text"] and "usg" not in label["text"].lower()


def test_failed_check_below_significant_retests_after_one_hour(store):
    """1.022 at the start of a shift fails the 1.015 limit: hold, rehydrate, retest after 1 h, clinician sign-off."""
    rec = store.hydration_check(worker_ref="W01", usg=1.022, timing="start_of_shift", entry="typed", actor="S04",
                                at="2025-08-19T05:20:00+04:00")
    assert rec["action_level"] == "moderate" and rec["out_of_range"] is True
    assert {"hold_work_station_assignment", "retest_due", "clinician_review"} <= set(rec["actions"])
    assert rec["retest_due_at"] == "2025-08-19T06:20:00+04:00"
    ok = store.hydration_check(worker_ref="W01", usg=1.012, timing="start_of_shift", entry="typed", actor="S04",
                               at="2025-08-19T06:25:00+04:00")
    assert ok["action_level"] == "normal" and ok["actions"] == ["maintain_fluids"]


@pytest.mark.tcase("T63")
@pytest.mark.parametrize("usg", [10.24, 1024, 0.99, 1.2])
def test_implausible_refractometer_reading_is_rejected(site, usg):
    """A value like 10.24 is rejected as implausible and the nurse is asked to re-enter it."""
    r = site.as_("mariam").post("/v1/clinical/hydration-checks", {"worker_ref": "W01", "usg": usg,
                                                                 "timing": "start_of_shift", "entry": "typed"})
    assert r.status_code == 422 and "plausible" in r.json()["detail"]


def test_restriction_reaches_operations_as_a_label_without_the_reason(site):
    """A clinician's restriction becomes an operational label; the private reason never leaves the clinic."""
    site.as_("fatima").post("/v1/clinical/restrictions", {"worker_ref": "W07", "label": "shaded_light_duty",
                                                        "until": "2025-08-26T18:00:00+04:00",
                                                        "reason_private": "ACR follow-up SECRET-REASON"})
    body = site.sup.get("/v1/sites/site_demo/operations").text
    assert "SECRET-REASON" not in body
    st = site.as_("anwar").get("/v1/worker/today").json()["status"]
    assert st["inputs"]["restriction_label"] == "shaded_light_duty"


def test_care_relationship_and_consent_gate_the_record(site):
    """Without active care consent, even the clinician is refused, and the refusal is audited."""
    site.as_("anwar").post("/v1/consents/events", {"purpose": "clinical_care", "action": "withdraw"})
    r = site.as_("fatima").get("/v1/clinical/patients/W07")
    assert r.status_code == 403
    assert any(e["action"] == "clinical.read_patient" and e["decision"] == "denied" for e in site.sb.audit.entries)


def test_clinician_written_summary_can_be_approved_when_ai_is_off(site):
    """With AI off, the clinician writes the summary; it is approved and shown to the worker."""
    site.sup.post("/v1/sandbox/settings", {"ai_enabled": False})
    fatima = site.as_("fatima")
    d = fatima.post("/v1/clinical/summaries/draft", {"worker_ref": "W07", "lang": "ar",
                                                    "note": "ACR 64 mg/g. Repeat in 3 months."}).json()
    assert d["summary"] is None and d["status"] == "ai_off_manual_template"
    ok = fatima.post(f"/v1/clinical/summaries/{d['id']}/approve", {"text": "نتيجتك تحتاج إلى إعادة الفحص بعد 3 أشهر."})
    assert ok.status_code == 200 and ok.json()["source"] == "clinician_written"
    me = site.as_("anwar").get("/v1/worker/health").json()
    assert me["summaries"] and me["summaries"][0]["status"] == "approved"


# ------------------------------------------------ booking capacity (external review, Nov 2026)
def _urgent_referral(fat, wid):
    r = fat.post("/v1/clinical/referrals", {"worker_ref": wid, "urgency": "urgent"})
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    assert fat.post(f"/v1/clinical/referrals/{rid}/events", {"state": "accepted"}).status_code == 200
    return rid


APPT = {"start": "2025-08-19T14:00:00+04:00", "end": "2025-08-19T16:00:00+04:00", "place": "clinic",
        "transport": "booked"}


@pytest.mark.tcase("T60")
def test_two_urgent_bookings_can_never_share_the_last_slot(site):
    """With one urgent slot left, the first booking takes it and the second is escalated, never double-booked."""
    site.scene("clinic")
    store = site.sb.clinical
    free = [x for x in store.sessions[0]["slots"] if x["class"] == "urgent" and not x["taken_by"]]
    for x in free[1:]:
        x["taken_by"] = "outside"                       # leave exactly one urgent slot
    fat = site.as_("fatima")
    a, b = _urgent_referral(fat, "W01"), _urgent_referral(fat, "W02")
    ra = fat.post(f"/v1/clinical/referrals/{a}/events", {"state": "scheduled", "appointment": APPT})
    rb = fat.post(f"/v1/clinical/referrals/{b}/events", {"state": "scheduled", "appointment": APPT})
    assert ra.status_code == 200 and rb.status_code == 409
    assert "escalated to the clinical lead" in rb.json()["detail"]
    taken = [x for x in store.sessions[0]["slots"] if x["taken_by"] == a]
    assert len(taken) == 1 and not [x for x in store.sessions[0]["slots"] if x["taken_by"] == b]
    assert store.referrals[b]["state"] == "accepted"     # still open, never silently dropped
    cap = fat.get("/v1/clinical/queue").json()["capacity"]
    assert cap["urgent_used"] == cap["urgent_slots"]
    assert any(e["action"] == "clinical.capacity_escalated" for e in site.sb.audit.entries)


def test_each_booking_gets_its_own_future_slot_and_the_employer_sees_only_the_window(site):
    """Bookings get distinct slots after the current time; the employer projection shows the session window only."""
    site.scene("clinic")                                    # 14:05: the 14:00 urgent slot has started
    fat = site.as_("fatima")
    a, b = _urgent_referral(fat, "W01"), _urgent_referral(fat, "W02")
    sa = fat.post(f"/v1/clinical/referrals/{a}/events", {"state": "scheduled", "appointment": APPT}).json()
    sb_ = fat.post(f"/v1/clinical/referrals/{b}/events", {"state": "scheduled", "appointment": APPT}).json()
    assert sa["appointment"]["start"] != sb_["appointment"]["start"]
    assert sa["appointment"]["start"] >= "2025-08-19T14:05:00+04:00"
    labels = site.sup.get("/v1/sites/site_demo/operations").json()["operational_labels"]
    shown = [x for x in labels if x.get("worker") in ("W01", "W02")]
    assert len(shown) == 2 and all("clinic visit 14:00-16:00" in x["text"] for x in shown)
    assert "urgent" not in str(shown).lower() and "15:" not in str(shown)
