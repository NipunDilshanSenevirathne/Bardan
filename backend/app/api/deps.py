"""Shared request context, authorisation helpers and RFC 9457 problem details."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Header, HTTPException
from fastapi.responses import JSONResponse

from ..core import access
from ..core.sandbox import STORE, Sandbox


@dataclass
class Ctx:
    sb: Sandbox
    actor: str
    role: str
    persona: str
    lang: str
    reset: bool

    def require(self, capability: str, resource: str = "", subject: str | None = None) -> None:
        if not access.can(self.role, capability):
            category = "clinical" if capability.startswith("clinical.") else "security"
            self.sb.audit.append(at=self.sb.now(), actor=self.actor, role=self.role, action=f"access:{capability}",
                                 resource=resource or capability, decision="denied",
                                 reason=f"role '{self.role}' lacks '{capability}'", subject=subject,
                                 category=category)
            raise HTTPException(403, f"Your role ({self.role}) is not allowed to do this. The attempt was recorded "
                                     f"in the audit log.")


def context(principal: dict[str, Any] = Depends(access.principal),
            x_bardan_lang: str | None = Header(default=None)) -> Ctx:
    sb, reset = STORE.get(principal["sb"])
    lang = x_bardan_lang if x_bardan_lang in ("en", "ar") else "en"
    return Ctx(sb=sb, actor=principal["actor"], role=principal["role"], persona=principal["persona"], lang=lang,
               reset=reset)


def problem(status: int, title: str, detail: str, code: str | None = None, instance: str | None = None):
    return JSONResponse(status_code=status, media_type="application/problem+json",
                        content={"type": f"https://bardan.example/problems/{code or 'error'}", "title": title,
                                 "status": status, "detail": detail, "code": code, "instance": instance})


def idempotent(ctx: Ctx, key: str | None, compute):
    """Idempotency-Key support: the same key returns the same result, never a second action (T54)."""
    if not key:
        return compute()
    store = ctx.sb.sync_acks
    k = f"idem:{ctx.actor}:{key}"
    with ctx.sb.lock:      # re-entrant: the action takes the same lock; two copies of a request never both run
        if k in store:
            return {**store[k], "idempotent_replay": True}
        out = compute()
        store[k] = out
        return out
