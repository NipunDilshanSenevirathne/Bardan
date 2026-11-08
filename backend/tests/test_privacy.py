"""Privacy boundary: clinical access, aggregates, consent, exports and the passport (T34-T42, T59)."""
from __future__ import annotations

import pytest

from app.ai import copilot
from app.core.consent import ConsentStore

CLINICAL_KEYS = ("acr", "egfr", "albumin", "creatinine", "mg/g", "usg", "diagnosis", "\"results\"")


@pytest.mark.tcase("T34")
@pytest.mark.parametrize("path", ["/v1/clinical/queue", "/v1/clinical/patients/W07"])
@pytest.mark.parametrize("persona", ["joseph", "sara", "reviewer"])
def test_employer_roles_cannot_read_clinical_endpoints(site, persona, path):
    """Supervisor, HSE and auditor calls to clinical endpoints are denied, leak nothing and are audited."""
    p = site.as_(persona)
    r = p.get(path)
    assert r.status_code == 403
    body = r.text.lower()
    assert not any(k in body for k in CLINICAL_KEYS)
    denied = [e for e in site.sb.audit.entries if e["actor"] == p.actor and e["decision"] == "denied"]
    assert denied and denied[-1]["category"] == "clinical"


@pytest.mark.tcase("T34")
def test_operational_views_carry_no_clinical_fields(site):
    """Operations, tasks and compliance responses never contain clinical keys or values."""
    site.scene("clinic")
    for path in ("/v1/sites/site_demo/operations", "/v1/tasks", "/v1/sites/site_demo/compliance"):
        body = site.as_("sara").get(path).text.lower()
        assert "\"acr\"" not in body and "\"egfr\"" not in body and "mg/g" not in body and "\"usg\"" not in body


@pytest.mark.tcase("T35")
@pytest.mark.parametrize("persona", ["sara", "reviewer", "joseph", "fatima"])
def test_bulk_health_roster_export_is_denied(site, persona):
    """A bulk export of health data is denied for every role outside an expressly authorised purpose."""
    r = site.as_(persona).get("/v1/clinical/export/bulk")
    assert r.status_code == 403
    assert any(e["action"] == "clinical.bulk_export" and e["decision"] == "denied" for e in site.sb.audit.entries)


@pytest.mark.tcase("T36")
def test_overlapping_aggregates_that_isolate_a_small_group_are_blocked(site):
    """'Site total' then 'site total excluding the new workers' would isolate 3 people: the second is blocked."""
    sara = site.as_("sara")
    first = sara.post("/v1/copilot/query", {"question": "How many symptom reports on site this week?"}).json()
    assert first["decision"] == "answered"
    second = sara.post("/v1/copilot/query",
                       {"question": "Symptom reports this week excluding new workers"}).json()
    assert second["decision"] == "refused" and second["rule"] == "differencing"


@pytest.mark.tcase("T36")
def test_repeated_health_queries_are_limited(sandbox):
    """Repeated overlapping health aggregates hit a per-session query limit."""
    sandbox.copilot_log.extend({"health": True} for _ in range(copilot.HEALTH_QUERY_LIMIT))
    r = copilot.query("How many symptom reports on site this week?", lang="en", sb=sandbox, ai_on=False)
    assert r["result"]["decision"] == "refused" and r["result"]["rule"] == "query_limit"


@pytest.mark.tcase("T37")
def test_site_with_four_participating_workers_is_suppressed(sandbox):
    """With only 4 participating workers no statistic is released."""
    sandbox.world["workers"] = sandbox.world["workers"][:4]
    r = copilot.query("How many symptom reports on site this week?", lang="en", sb=sandbox, ai_on=False)
    assert r["result"]["decision"] == "refused" and r["result"]["rule"] == "small_group"


@pytest.mark.tcase("T37")
def test_small_cell_and_its_complement_are_suppressed(sandbox):
    """A zone with 3 workers is suppressed, and so is one more cell, so it cannot be worked out by subtraction."""
    ws = sandbox.world["workers"]
    d = [w for w in ws if w["crew"] == "C4"]
    sandbox.world["workers"] = [w for w in ws if w["crew"] != "C4"] + d[:3]
    r = copilot.query("Symptom reports by zone this week", lang="en", sb=sandbox, ai_on=False)["result"]
    rows = {x["zone"]: x for x in r["rows"]}
    assert rows["D"]["suppressed"] == "primary" and rows["D"]["reports"] is None
    assert sum(1 for x in rows.values() if x.get("suppressed") == "complementary") == 1
    shown = [x for x in rows.values() if not x.get("suppressed")]
    assert all(x["workers"] >= copilot.MIN_CELL for x in shown)
    _, sup = copilot.suppress_cells([{"g": "a", "n": 2, "v": 1}, {"g": "b", "n": 1, "v": 0},
                                     {"g": "c", "n": 30, "v": 5}], pop_key="n", value_keys=["v"])
    assert sup["primary"] == 2 and sup["complementary"] == 1     # 2 + 1 < 5, so one more cell joins them
    _, sup = copilot.suppress_cells([{"g": "a", "n": 4, "v": 1}, {"g": "b", "n": 2, "v": 0},
                                     {"g": "c", "n": 30, "v": 5}], pop_key="n", value_keys=["v"])
    assert sup["primary"] == 2 and sup["complementary"] == 0     # together they are 6 people: no isolation


@pytest.mark.tcase("T38")
def test_stale_offline_grant_cannot_restore_permission(site):
    """A grant made offline before a withdrawal, synced after it, never brings the permission back."""
    anwar = site.as_("anwar")
    assert site.sb.consent.status("W07", "passport_sharing")["active"] is True
    anwar.post("/v1/consents/events", {"purpose": "passport_sharing", "action": "withdraw"})
    stale = {"event_id": "g-old", "sequence": 1, "event_type": "consent", "observed_at": "2025-08-18T17:00:00+04:00",
             "payload": {"purpose": "passport_sharing", "action": "grant"}}
    ack = anwar.post("/v1/sync", {"device_id": "phone-anwar", "events": [stale]}).json()["acks"][0]
    assert ack["status"] == "accepted" and ack["result"]["effective"]["active"] is False
    assert site.sb.consent.status("W07", "passport_sharing")["active"] is False


def test_withdrawal_wins_ties_but_a_later_online_grant_counts():
    """On an exact tie the withdrawal wins unless both events were stamped online in a known order."""
    cs = ConsentStore()
    t = "2025-08-19T10:00:00+04:00"
    cs.record(worker_ref="W1", purpose="research", action="grant", at=t, server_stamped=False)
    cs.record(worker_ref="W1", purpose="research", action="withdraw", at=t, server_stamped=True)
    assert cs.status("W1", "research")["active"] is False
    cs.record(worker_ref="W1", purpose="research", action="grant", at=t, server_stamped=True)
    assert cs.status("W1", "research")["active"] is True
    # Instants are compared with their offsets: 06:30Z is 10:30 at the site, later than the withdrawal.
    cs2 = ConsentStore()
    cs2.record(worker_ref="W2", purpose="research", action="withdraw", at=t)
    cs2.record(worker_ref="W2", purpose="research", action="grant", at="2025-08-19T06:30:00+00:00")
    assert cs2.status("W2", "research")["active"] is True


@pytest.mark.tcase("T39")
def test_export_refused_after_consent_withdrawal(site):
    """Sharing consent withdrawn: a share link is refused and existing links stop working."""
    anwar = site.as_("anwar")
    pv = anwar.post("/v1/exports/preview", {"fields": ["results"], "recipient_region": "AE"}).json()
    ok = anwar.post("/v1/exports", {"preview_id": pv["id"], "confirm": True}).json()
    token, code = ok["path"].split("/")[-1], ok["passcode"]
    assert site.client.get(f"/v1/passport/{token}", params={"code": code}).status_code == 200
    anwar.post("/v1/consents/events", {"purpose": "passport_sharing", "action": "withdraw"})
    assert site.client.get(f"/v1/passport/{token}", params={"code": code}).status_code == 410
    pv2 = anwar.post("/v1/exports/preview", {"fields": ["results"], "recipient_region": "AE"}).json()
    r = anwar.post("/v1/exports", {"preview_id": pv2["id"], "confirm": True})
    assert r.status_code == 409


@pytest.mark.tcase("T40")
def test_export_without_online_authorisation_is_deferred(site):
    """Without a current online authorisation the export is deferred, with an explanation."""
    pv = site.as_("anwar").post("/v1/exports/preview", {"fields": ["results"], "online": False}).json()
    assert pv["gate"]["decision"] == "deferred"
    assert any(c["check"] == "online_authorisation" and not c["ok"] and "T40" in c["detail"]
               for c in pv["gate"]["checks"])


def test_international_recipient_gets_worker_copy_only(site):
    """A recipient outside the UAE: no share link; the worker can still keep their own copy."""
    pv = site.as_("anwar").post("/v1/exports/preview", {"fields": ["results"], "recipient_region": "IN"}).json()
    assert pv["gate"]["decision"] == "worker_copy_only"


def test_passport_link_needs_the_passcode(site):
    """A share link without the right passcode reveals nothing."""
    anwar = site.as_("anwar")
    pv = anwar.post("/v1/exports/preview", {"fields": ["results"]}).json()
    ok = anwar.post("/v1/exports", {"preview_id": pv["id"], "confirm": True}).json()
    token = ok["path"].split("/")[-1]
    assert site.client.get(f"/v1/passport/{token}", params={"code": "000000" if ok["passcode"] != "000000"
                                                            else "111111"}).status_code == 404


@pytest.mark.tcase("T59")
def test_missed_appointment_reason_never_reaches_the_employer(site):
    """A visit missed for lack of transport: the referral stays open with the coordinator; the employer is
    never told the reason or the outcome."""
    site.scene("clinic")
    ref = site.sb.clinical.referrals["ref_0001"]
    assert ref["state"] == "missed" and ref["coordinator"] == "S04"
    assert ref["history"][-1]["reason"] == "transport_unavailable"
    for persona in ("joseph", "sara"):
        body = site.as_(persona).get("/v1/sites/site_demo/operations").text.lower()
        assert "transport_unavailable" not in body and "missed" not in body
    # The referral can be escalated or rescheduled; it never silently closes.
    from app.core.clinical import REFERRAL_ALLOWED
    assert REFERRAL_ALLOWED["missed"] == {"scheduled", "escalated"}


def test_worker_sees_who_opened_their_record(site):
    """'Who saw my data': a clinician's read of the record appears in the worker's own view."""
    site.as_("fatima").get("/v1/clinical/patients/W07")
    mine = site.as_("anwar").get("/v1/worker/health").json()
    assert any(e["actor"] == "S03" and e["action"] == "clinical.read_patient" for e in mine["who_saw_my_data"])


# ------------------------------------------------------------------ AI trace scoping (external review, Nov 2026)
QUESTION = "Are my kidneys failing? I feel scared"


@pytest.mark.tcase("T34")
@pytest.mark.parametrize("persona", ["joseph", "sara", "fatima", "mariam"])
def test_staff_never_read_a_workers_own_words_or_identity_in_the_ai_trace(site, persona):
    """A worker's Ask question stays with the worker: other roles see only their own runs and a count."""
    ravi = site.as_("ravi")
    assert ravi.post("/v1/assist/chat", {"question": QUESTION}).status_code == 200
    body = site.as_(persona).get("/v1/trace").json()
    assert body["scope"] == "own"
    assert "kidneys" not in str(body["runs"]) and ravi.actor not in str(body["runs"])
    assert body["withheld"] >= 1


@pytest.mark.tcase("T34")
def test_reviewer_sees_other_peoples_runs_de_identified_and_the_review_is_audited(site):
    """The reviewer can audit what the AI and the gate did, but not who asked or what they wrote."""
    site.sb.world["settings"]["redteam_mode"] = True
    ravi = site.as_("ravi")
    ravi.post("/v1/assist/chat", {"question": QUESTION})
    ravi.post("/v1/assist/intake", {"text": "I am dizzy and the water is finished"})
    rev = site.as_("reviewer")
    body = rev.get("/v1/trace").json()
    assert body["scope"] == "review_deidentified"
    text = str(body["runs"])
    # The worker's own words never appear; the model's blocked draft does (that is what the review is for).
    assert "scared" not in text and "dizzy" not in text and ravi.actor not in text
    ask = next(r for r in body["runs"] if r["capability"] == "ask_bardan")
    assert ask.get("draft") and ask["gate"]["decision"] == "blocked"
    assert ask["subject"] == "worker" and ask["worker_words"] == "withheld" and "actor" not in ask
    assert "gate" in ask                                   # the gate's decision stays reviewable
    intake = next(r for r in body["runs"] if r["capability"] == "speak_intake")
    assert "output" not in intake and intake["candidates_count"] >= 1
    reviews = [e for e in site.sb.audit.entries if e["action"] == "ai.trace_review" and e["actor"] == rev.actor]
    assert len(reviews) == 1
    rev.get("/v1/trace")                                     # polling does not flood the audit log
    assert len([e for e in site.sb.audit.entries if e["action"] == "ai.trace_review"]) == 1


def test_a_worker_sees_their_own_ai_runs_in_full(site):
    """The person who asked can open the trace of their own question, including a blocked draft."""
    ravi, anwar = site.as_("ravi"), site.as_("anwar", "ar")
    ravi.post("/v1/assist/chat", {"question": QUESTION})
    anwar.post("/v1/assist/chat", {"question": "هل كليتي تفشل؟"})
    mine = ravi.get("/v1/trace").json()
    assert mine["scope"] == "own" and mine["withheld"] == 1
    assert all(r["actor"] == ravi.actor for r in mine["runs"])
    assert any(r.get("question") == QUESTION for r in mine["runs"])
