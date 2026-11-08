"""Identity for the judge sandbox, capability tokens and the permission matrix (§15.3, §21.5, §23.1).

There is no sign-up and no personal data: a judge picks a synthetic persona and
receives a signed, short-lived capability token for one sandbox. Every API call
is authorised on the server from that token. "A field hidden in the frontend
is not access control" (§21.5).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any

from fastapi import Header, HTTPException

from .scenario import PERSONAS, STAFF

SECRET = os.environ.get("BARDAN_TOKEN_SECRET") or secrets.token_hex(32)
TOKEN_TTL_S = 4 * 3600

PERSONA_INDEX: dict[str, dict[str, Any]] = {}
for key, p in PERSONAS.items():
    PERSONA_INDEX[key] = {"key": key, "actor": p["id"], "role": "worker", "name": p["name"], "lang": p["lang"],
                          "title": p["role_title"]}
for key, s in STAFF.items():
    PERSONA_INDEX[key] = {"key": key, "actor": s["id"], "role": s["role"], "name": s["name"], "lang": s["lang"],
                          "title": s["title"]}

# Capability matrix. Clinical capabilities never belong to employer roles.
PERMISSIONS: dict[str, set[str]] = {
    "worker": {"self.read", "self.report", "self.dispute", "self.checkin", "self.consent", "self.export",
               "assist.intake", "assist.chat", "emergency.use", "task.read_own", "task.confirm"},
    "supervisor": {"ops.read", "task.act", "task.read", "plan.evaluate", "plan.simulate", "plan.optimise",
                   "plan.approve", "plan.activate", "observation.write", "forecast.read", "emergency.use",
                   "copilot.query"},
    "hse": {"ops.read", "task.read", "task.act", "task.verify_independent", "task.escalation_owner",
            "compliance.read", "copilot.query", "policy.compile", "policy.approve", "insights.read",
            "insights.approve", "forecast.read", "plan.simulate", "plan.evaluate", "audit.read",
            "observation.write", "emergency.use", "exemption.record"},
    "clinician": {"clinical.read", "clinical.write", "clinical.verify", "clinical.referral",
                  "clinical.restriction", "clinical.document_ai", "clinical.summary_approve", "policy.approve",
                  "audit.read", "emergency.use"},
    "nurse": {"clinical.read", "clinical.hydration", "clinical.referral_coordinate", "emergency.use",
              "audit.read"},
    "auditor": {"reports.read", "audit.read", "replay.run", "ops.read", "task.read", "compliance.read",
                "forecast.read", "insights.read", "drill.run"},
}
CLINICAL_PREFIX = "clinical."
EMPLOYER_ROLES = {"supervisor", "hse", "auditor"}


def sign(payload: dict[str, Any]) -> str:
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = hmac.new(SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()[:40]
    return f"{raw}.{sig}"


def verify(token: str) -> dict[str, Any]:
    try:
        raw, sig = token.rsplit(".", 1)
    except ValueError as exc:
        raise HTTPException(401, "Malformed capability token") from exc
    good = hmac.new(SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()[:40]
    if not hmac.compare_digest(good, sig):
        raise HTTPException(401, "Capability token signature is not valid")
    payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    if payload.get("exp", 0) < time.time():
        raise HTTPException(401, "Capability token expired; choose a persona again")
    return payload


def issue(sandbox_id: str, persona_key: str) -> dict[str, Any]:
    p = PERSONA_INDEX.get(persona_key)
    if not p:
        raise HTTPException(404, "Unknown persona")
    now = int(time.time())
    payload = {"sb": sandbox_id, "persona": persona_key, "actor": p["actor"], "role": p["role"],
               "iat": now, "exp": now + TOKEN_TTL_S}
    return {"token": sign(payload), "persona": p, "permissions": sorted(PERMISSIONS[p["role"]])}


def principal(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Choose a persona to get a sandbox capability token")
    return verify(authorization[7:])


def can(role: str, capability: str) -> bool:
    return capability in PERMISSIONS.get(role, set())
