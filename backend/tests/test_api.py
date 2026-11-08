"""API contracts and security: capability tokens, permissions, problem details, headers, AI model privacy."""
from __future__ import annotations

import base64
import json
import re
import time

import pytest

from app.core import access

MODEL_NAMES = re.compile(r"gemini|gemma|flash-lite|\bflash\b|tts-preview|text-embedding|generativelanguage", re.I)


def test_health_is_public_and_names_no_model(client):
    """Health works without a token and never names a model."""
    r = client.get("/v1/health")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert r.json()["languages"] == ["en", "ar"]
    assert not MODEL_NAMES.search(r.text)


def test_missing_tampered_or_expired_tokens_are_refused(client):
    """No token, a forged signature or an expired token: 401 with an RFC 9457 problem body."""
    assert client.get("/v1/worker/today").status_code == 401
    r = client.post("/v1/sandbox/session", json={"persona": "ravi"}).json()
    raw, sig = r["token"].rsplit(".", 1)
    payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    payload["role"] = "clinician"                                  # privilege escalation attempt
    forged = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    bad = client.get("/v1/clinical/queue", headers={"Authorization": f"Bearer {forged}.{sig}"})
    assert bad.status_code == 401
    assert bad.headers["content-type"].startswith("application/problem+json")
    body = bad.json()
    assert {"type", "title", "status", "detail"} <= set(body) and body["status"] == 401
    expired = access.sign({**payload, "role": "worker", "exp": int(time.time()) - 5})
    assert client.get("/v1/worker/today", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


PERMISSION_CASES = [
    ("ravi", "post", "/v1/plans/optimise", 403),
    ("ravi", "get", "/v1/tasks", 403),
    ("ravi", "get", "/v1/sites/site_demo/compliance", 403),
    ("anwar", "post", "/v1/copilot/query", 403),
    ("joseph", "post", "/v1/policy/drafts", 403),
    ("joseph", "post", "/v1/exemptions", 403),                     # T19: only HSE records exemptions
    ("joseph", "get", "/v1/audit", 403),
    ("joseph", "get", "/v1/insights/signals", 403),
    ("mariam", "post", "/v1/plans/optimise", 403),
    ("reviewer", "post", "/v1/tasks/task_001/events", 403),
    ("fatima", "get", "/v1/sites/site_demo/operations", 403),
    ("sara", "post", "/v1/plans/optimise", 403),
]


@pytest.mark.tcase("T19", "T34")
@pytest.mark.parametrize("persona,method,path,status", PERMISSION_CASES,
                         ids=[f"{p}-{m}-{u.split('/v1/')[1]}" for p, m, u, s in PERMISSION_CASES])
def test_permission_matrix_is_enforced_on_the_server(site, persona, method, path, status):
    """Every API call is authorised on the server from the token; hidden buttons are not access control."""
    p = site.as_(persona)
    body = {"task": "P1", "ref": "EX-1", "reason": "test reason"} if "exemptions" in path else \
        {"question": "water gaps"} if "copilot" in path else {"action": "accept"} if "events" in path else {}
    r = p.post(path, body) if method == "post" else p.get(path)
    assert r.status_code == status, r.text
    assert any(e["actor"] == p.actor and e["decision"] == "denied" for e in site.sb.audit.entries)


@pytest.mark.tcase("T19")
def test_only_an_authorised_exemption_record_lifts_the_midday_stop(site):
    """HSE records an exemption with a reference and reason; it is audited."""
    r = site.as_("sara").post("/v1/exemptions", {"task": "P1", "ref": "MOHRE-EX-2025-17",
                                                 "reason": "Continuous concrete pour (technical)"})
    assert r.status_code == 200 and r.json()["authorised"] is True
    assert any(e["action"] == "exemption.recorded" for e in site.sb.audit.entries)
    short = site.as_("sara").post("/v1/exemptions", {"task": "P1", "ref": "x", "reason": "no"})
    assert short.status_code == 422


@pytest.mark.tcase("T13", "T16")
def test_readings_with_wrong_kind_or_unit_are_quarantined(site):
    """Air temperature is never accepted as TWL or WBGT; a TWL in the wrong unit is quarantined, not converted."""
    sara = site.as_("sara")
    t = site.sb.now()
    r = sara.post("/v1/observations", {"zone": "A", "kind": "air_temp", "value": 44, "unit": "C", "observed_at": t})
    assert r.status_code == 422 and "T13" in r.json()["detail"]
    r = sara.post("/v1/observations", {"zone": "A", "kind": "twl", "value": 140, "unit": "C", "observed_at": t})
    assert r.status_code == 422 and "No silent conversion" in r.json()["detail"]
    assert any(e["action"] == "observation.quarantined" for e in site.sb.audit.entries)
    r = sara.post("/v1/observations", {"zone": "A", "kind": "twl", "value": 140, "unit": "W/m2",
                                       "observed_at": "2025-08-19T09:00:00"})
    assert r.status_code == 422                                       # no UTC offset


def test_validation_errors_are_problem_details(site):
    """Invalid input returns 422 problem+json naming the field."""
    r = site.sup.post("/v1/sandbox/advance", {"minutes": 9999})
    assert r.status_code == 422 and r.headers["content-type"].startswith("application/problem+json")
    assert "minutes" in r.json()["detail"]


def test_security_headers_are_set(client):
    """CSP without unsafe-inline scripts, no framing, no sniffing, no referrer."""
    r = client.get("/v1/health")
    csp = r.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    script = next(p for p in csp.split(";") if p.strip().startswith("script-src"))
    assert "unsafe-inline" not in script and "unsafe-eval" not in script
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["x-frame-options"] == "DENY" and "max-age" in r.headers["strict-transport-security"]


def test_rate_limit_returns_429(client, monkeypatch):
    """The shared sandbox is rate-limited per client address."""
    import app.main as m
    monkeypatch.setattr(m, "RATE", 3)
    monkeypatch.setattr(m, "_BUCKET", {})
    codes = [client.get("/v1/health", headers={"x-forwarded-for": "203.0.113.9"}).status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[-1] == 429


@pytest.mark.tcase("T50")
def test_no_model_identifier_ever_reaches_the_interface(site, fake_ai):
    """Model names and model switching stay in the documentation: traces, agents and reports never show them."""
    fake_ai(lambda system, user: {"answer": "Rest in the shade at your breaks.", "passage_ids": ["K-REST-1"]})
    site.as_("ravi").post("/v1/assist/chat", {"question": "Where should I rest?"})
    for path in ("/v1/trace", "/v1/agents", "/v1/health", "/v1/me", "/v1/reports/language"):
        r = site.as_("sara").get(path)
        assert r.status_code == 200 and not MODEL_NAMES.search(r.text), path
    ev = site.client.get("/v1/reports/evaluation")
    assert ev.status_code == 200 and not MODEL_NAMES.search(ev.text)


def test_trace_strips_model_fields_defensively():
    """Even if a run record carried model fields, the trace endpoint removes them."""
    from app.api.routes_trust import _strip_models
    run = {"id": "r1", "model": "x-model", "steps": [{"model_id": "y", "tier": "fast", "ok": True}]}
    out = _strip_models(run)
    assert "model" not in out and out["steps"] == [{"ok": True}]


def test_audit_chain_verifies_and_detects_tampering(site):
    """The audit log is hash-chained: it verifies, and any edit breaks the chain."""
    site.as_("ravi").post("/v1/worker/check-ins", {"symptoms": ["headache"]})
    v = site.as_("sara").get("/v1/audit/verify").json()
    assert v["valid"] is True and v["entries"] > 2
    site.sb.audit.entries[1]["actor"] = "someone-else"
    assert site.sb.audit.verify()["valid"] is False


def test_worker_audit_view_is_scoped_to_themselves(site):
    """A worker's audit view shows only entries about them."""
    site.as_("fatima").get("/v1/clinical/patients/W07")
    entries = site.as_("anwar").get("/v1/audit").json()["entries"]
    assert entries and all(e.get("subject") in (None, "W07") or e["actor"] == "W07" for e in entries)


def test_decision_replay_pack_matches_the_device_engine_format(client):
    """The replay pack serves every conformance case with the server's result; comparing identical results
    reports no difference, and a single changed action is reported as a mismatch."""
    pack = client.get("/v1/replay/conformance").json()
    rows = [{"id": c["id"], **{k: c["server"][k] for k in ("state", "band", "actions")}} for c in pack["cases"]]
    same = client.post("/v1/replay/compare", json={"device": "test", "results": rows}).json()
    assert same["identical"] == len(rows) and same["differences"] == []
    rows[0] = {**rows[0], "actions": rows[0]["actions"][:-1]}
    diff = client.post("/v1/replay/compare", json={"device": "test", "results": rows}).json()
    assert diff["verdict"].startswith("MISMATCH") and diff["differences"][0]["id"] == rows[0]["id"]


def test_sandbox_scene_jump_and_reset(site):
    """Scenes move the clock; reset gives a clean sandbox."""
    s = site.scene("midday")
    assert s["state"]["clock"].startswith("2025-08-19T12:40")
    r = site.sup.post("/v1/sandbox/reset").json()
    assert r["clock"].startswith("2025-08-18T18:00")
    assert site.sup.post("/v1/sandbox/scene", {"scene": "nope"}).status_code == 404
