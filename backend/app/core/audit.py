"""Append-only, hash-chained audit log (finalsystem.md §19, §23, §27.2 invariant 5).

Every access decision, task transition, consent event, export and AI gate
decision is appended here. Each entry carries the hash of the previous entry,
so any edit or deletion breaks the chain and ``verify`` reports where.
Entries never contain clinical values: only references and categories.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

GENESIS = "0" * 64


class AuditLog:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def append(self, *, at: str, actor: str, role: str, action: str, resource: str,
               decision: str = "allowed", reason: str | None = None, subject: str | None = None,
               category: str = "operational", detail: dict[str, Any] | None = None) -> dict[str, Any]:
        prev = self.entries[-1]["hash"] if self.entries else GENESIS
        entry = {
            "seq": len(self.entries) + 1,
            "at": at,
            "actor": actor,
            "role": role,
            "action": action,
            "resource": resource,
            "decision": decision,
            "reason": reason,
            "subject": subject,            # whose data (worker ref), for "who saw my data"
            "category": category,          # operational | clinical | consent | export | ai | security
            "detail": detail or {},
            "prev_hash": prev,
        }
        entry["hash"] = _hash(entry)
        self.entries.append(entry)
        return entry

    def verify(self) -> dict[str, Any]:
        prev = GENESIS
        for e in self.entries:
            if e["prev_hash"] != prev:
                return {"valid": False, "broken_at": e["seq"], "reason": "previous-hash mismatch"}
            if _hash({k: v for k, v in e.items() if k != "hash"}) != e["hash"]:
                return {"valid": False, "broken_at": e["seq"], "reason": "entry content changed"}
            prev = e["hash"]
        return {"valid": True, "entries": len(self.entries), "head": prev}

    def scoped(self, *, role: str, actor: str, subject: str | None = None) -> list[dict[str, Any]]:
        """Audit visibility per §23.1: workers see who accessed their data; supervisors their own
        operational actions; HSE and auditors the operational scope; clinicians clinical access."""
        if role == "worker":
            return [e for e in self.entries if e.get("subject") == actor or e["actor"] == actor]
        if role == "supervisor":
            return [e for e in self.entries if e["actor"] == actor]
        if role in ("hse", "auditor"):
            return [_redact(e) if e["category"] == "clinical" else e for e in self.entries]
        if role in ("clinician", "nurse"):
            return [e for e in self.entries if e["category"] in ("clinical", "consent", "export")
                    or e["actor"] == actor]
        return []


def _hash(entry: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(entry, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _redact(e: dict[str, Any]) -> dict[str, Any]:
    r = dict(e)
    r["detail"] = {"redacted": "clinical detail is not visible outside the clinical boundary"}
    return r
