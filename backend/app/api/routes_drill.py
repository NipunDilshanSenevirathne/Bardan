"""Drill console routes: observed drills in a dedicated sandbox (core/drill.py, docs/DRILL-PROTOCOL.md).

Only the facilitator (the independent reviewer persona) sets up and runs drills and sees the recorded moments.
Participants' screens learn only whether a drill is running and which way of working it uses.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..core import access, policy
from ..core.drill import DrillError, DrillSeries
from ..core.sandbox import STORE
from .deps import Ctx, context

router = APIRouter(prefix="/v1")
APP_VERSION = "1.0.0"


def _err(e: DrillError) -> HTTPException:
    return HTTPException(e.status, str(e))


def _series(ctx: Ctx) -> DrillSeries:
    ctx.require("drill.run")
    s = ctx.sb.drills
    if s is None:
        raise HTTPException(404, "This sandbox has no drill series. Set one up on the drill console.")
    return s


def _view(ctx: Ctx, s: DrillSeries) -> dict[str, Any]:
    sb = ctx.sb
    return {**s.view(sb, facilitator=True), "sandbox_id": sb.id, "clock": sb.now(), "live": sb.live_clock is not None}


class SeriesIn(BaseModel):
    label: str = Field(default="", max_length=80)
    scenario: str = Field(default="water_out", max_length=20)
    per_arm: int = Field(default=2, ge=1, le=6)
    probes: bool = True
    deadline_min: int | None = Field(default=None, ge=5, le=60)
    people: int | None = Field(default=None, ge=2, le=40)
    setting: str = Field(default="role_play", max_length=20)
    languages: list[str] = Field(default_factory=lambda: ["en"], max_length=2)


@router.post("/drills/series")
def create_series(body: SeriesIn, ctx: Ctx = Depends(context)) -> dict[str, Any]:
    """A new drill sandbox: a clean shift (plan activated, no failures yet) and the drill plan."""
    ctx.require("drill.run")
    sb = STORE.create()
    with sb.lock:
        sb.set_scene("start", actor=ctx.actor)
        try:
            sb.drills = DrillSeries(label=body.label, scenario=body.scenario, per_arm=body.per_arm,
                                    probes=body.probes, deadline_min=body.deadline_min, people=body.people,
                                    setting=body.setting, languages=body.languages, created_by=ctx.actor)
        except DrillError as e:
            raise _err(e) from e
        sb.audit.append(at=sb.now(), actor=ctx.actor, role=ctx.role, action="drill.series_created",
                        resource=sb.drills.id, category="security",
                        detail={"scenario": body.scenario, "per_arm": body.per_arm, "probes": body.probes})
    tok = access.issue(sb.id, ctx.persona)
    return {"sandbox_id": sb.id, "token": tok["token"], "persona": tok["persona"], "permissions": tok["permissions"]}


@router.get("/drills/series")
def get_series(ctx: Ctx = Depends(context)) -> dict[str, Any]:
    s = _series(ctx)
    sb = ctx.sb
    with sb.lock:
        s.auto_end(sb)
        if sb.live_clock is not None:
            sb.ledger.tick(sb.now())       # escalations fire in real time during a drill
        return _view(ctx, s)


class StartIn(BaseModel):
    drill_id: str | None = Field(default=None, max_length=10)


@router.post("/drills/start")
def start(body: StartIn, ctx: Ctx = Depends(context)) -> dict[str, Any]:
    s = _series(ctx)
    with ctx.sb.lock:
        try:
            s.start(ctx.sb, body.drill_id)
        except DrillError as e:
            raise _err(e) from e
        return _view(ctx, s)


class MarkIn(BaseModel):
    mark: str = Field(..., max_length=30)
    undo: bool = False


@router.post("/drills/{drill_id}/mark")
def mark(drill_id: str, body: MarkIn, ctx: Ctx = Depends(context)) -> dict[str, Any]:
    s = _series(ctx)
    with ctx.sb.lock:
        try:
            s.mark(ctx.sb, drill_id, body.mark, undo=body.undo)
        except DrillError as e:
            raise _err(e) from e
        return _view(ctx, s)


class EndIn(BaseModel):
    notes: str = Field(default="", max_length=300)


@router.post("/drills/{drill_id}/end")
def end(drill_id: str, body: EndIn, ctx: Ctx = Depends(context)) -> dict[str, Any]:
    s = _series(ctx)
    with ctx.sb.lock:
        try:
            s.end(ctx.sb, drill_id, notes=body.notes)
        except DrillError as e:
            raise _err(e) from e
        return _view(ctx, s)


class AbandonIn(BaseModel):
    reason: str = Field(..., max_length=200)


@router.post("/drills/{drill_id}/abandon")
def abandon(drill_id: str, body: AbandonIn, ctx: Ctx = Depends(context)) -> dict[str, Any]:
    s = _series(ctx)
    with ctx.sb.lock:
        try:
            s.abandon(ctx.sb, drill_id, body.reason)
        except DrillError as e:
            raise _err(e) from e
        return _view(ctx, s)


@router.get("/drills/export")
def export(ctx: Ctx = Depends(context)) -> Response:
    s = _series(ctx)
    with ctx.sb.lock:
        body = s.export(ctx.sb, app_version=APP_VERSION,
                        policy_version=f"{policy.heat_pack()['policy_id']}@{policy.heat_pack()['version']}")
    return Response(json.dumps(body, ensure_ascii=False, indent=1), media_type="application/json",
                    headers={"content-disposition": f'attachment; filename="bardan-drills-{s.id}.json"'})
