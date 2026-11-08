"""Sandbox, identity and settings routes (judge sandbox §32.11)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..ai.gemini import CLIENT
from ..core import access
from ..core.content import LANGUAGE_STATUS
from ..core.sandbox import STORE
from ..core.scenario import SCENES
from .deps import Ctx, context

router = APIRouter(prefix="/v1")
VERSION = "1.0.0"


@router.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "version": VERSION, "ai_configured": CLIENT.configured,
            "languages": list(LANGUAGE_STATUS), "sandboxes": STORE.stats}


@router.get("/personas")
def personas() -> list[dict[str, Any]]:
    out = []
    for key, p in access.PERSONA_INDEX.items():
        out.append({"key": key, **{k: p[k] for k in ("actor", "role", "name", "lang", "title")}})
    return out


class SessionIn(BaseModel):
    persona: str = Field(..., max_length=20)
    sandbox_id: str | None = Field(default=None, max_length=40)


@router.post("/sandbox/session")
def session(body: SessionIn) -> dict[str, Any]:
    if body.sandbox_id:
        sb, reset = STORE.get(body.sandbox_id)
    else:
        sb, reset = STORE.create(), False
    tok = access.issue(sb.id, body.persona)
    sb.audit.append(at=sb.now(), actor=tok["persona"]["actor"], role=tok["persona"]["role"],
                    action="sandbox.persona_selected", resource=sb.id, category="security")
    return {"sandbox_id": sb.id, "reset": reset, **tok, "state": _state(sb)}


def _state(sb) -> dict[str, Any]:
    return {"clock": sb.now(), "scene": sb.world["scene"], "scenes": SCENES, "settings": sb.world["settings"],
            "site": sb.world["site"], "label": sb.world["label"], "active_plan": sb.active_plan_id,
            "created_epoch": int(sb.created), "reset_after_s": 3600, "ai_configured": CLIENT.configured,
            # Participants learn only whether a drill runs and which way of working it uses (never the plan).
            "drill": sb.drills.public_state() if sb.drills is not None else None,
            "live_clock": sb.live_clock is not None}


@router.get("/sandbox/state")
def state(ctx: Ctx = Depends(context)) -> dict[str, Any]:
    return {**_state(ctx.sb), "reset": ctx.reset, "me": {"actor": ctx.actor, "role": ctx.role,
                                                          "persona": ctx.persona}}


class SceneIn(BaseModel):
    scene: str


@router.post("/sandbox/scene")
def scene(body: SceneIn, ctx: Ctx = Depends(context)) -> dict[str, Any]:
    try:
        with ctx.sb.lock:
            r = ctx.sb.set_scene(body.scene, actor=ctx.actor)
    except KeyError as exc:
        raise HTTPException(404, "Unknown scene") from exc
    return {**r, "state": _state(ctx.sb)}


class AdvanceIn(BaseModel):
    minutes: int = Field(..., ge=1, le=240)


@router.post("/sandbox/advance")
def advance(body: AdvanceIn, ctx: Ctx = Depends(context)) -> dict[str, Any]:
    with ctx.sb.lock:
        ctx.sb.advance(body.minutes)
    return _state(ctx.sb)


@router.post("/sandbox/reset")
def reset(ctx: Ctx = Depends(context)) -> dict[str, Any]:
    sb = STORE.reset(ctx.sb.id)
    return _state(sb)


class SettingsIn(BaseModel):
    ai_enabled: bool | None = None
    ai_capabilities: dict[str, bool] | None = None
    forecast_enabled: bool | None = None
    redteam_mode: bool | None = None
    offline_roles: list[str] | None = Field(default=None, max_length=6)   # simulate unreachable owners (T56)


@router.post("/sandbox/settings")
def settings(body: SettingsIn, ctx: Ctx = Depends(context)) -> dict[str, Any]:
    s = ctx.sb.world["settings"]
    for k, v in body.model_dump(exclude_none=True).items():
        if k == "ai_capabilities":
            s.setdefault("ai_capabilities", {}).update(v)
        elif k == "offline_roles":
            roles = {r for r in v if r in access.PERMISSIONS}
            ctx.sb.ledger.offline_roles = roles
            s[k] = sorted(roles)
        else:
            s[k] = v
    ctx.sb.audit.append(at=ctx.sb.now(), actor=ctx.actor, role=ctx.role, action="settings.changed",
                        resource="sandbox", category="ai", detail=body.model_dump(exclude_none=True))
    return s


class TourIn(BaseModel):
    step: str = Field(..., max_length=40)


@router.post("/sandbox/tour")
def tour(body: TourIn, ctx: Ctx = Depends(context)) -> dict[str, Any]:
    # Counts only: no tracking of who did what (§32.11 measurement rule).
    if body.step not in ctx.sb.tour_steps:
        ctx.sb.tour_steps.add(body.step)
        STORE.stats["tour_steps"] += 1
    return {"completed": sorted(ctx.sb.tour_steps)}


@router.get("/me")
def me(ctx: Ctx = Depends(context)) -> dict[str, Any]:
    p = access.PERSONA_INDEX[ctx.persona]
    return {"persona": p, "role": ctx.role, "permissions": sorted(access.PERMISSIONS[ctx.role])}
