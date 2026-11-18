"""Scenario Lab and shift simulator routes (programme feedback, November 2026).

Stateless: the reviewer's scenario is planned and returned, never stored. Only counts go to the audit log.
"""
from __future__ import annotations

import threading
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..planner import lab
from .deps import Ctx, context

router = APIRouter(prefix="/v1")
_SOLVES = threading.BoundedSemaphore(2)     # at most two lab plans at once per instance (CPU on a small host)

Id = Field(min_length=1, max_length=8, pattern=r"^[A-Za-z0-9_-]+$")
Hhmm = Field(pattern=r"^\d\d:\d\d$")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Weather(Strict):
    peak_c: float = Field(ge=25, le=50)
    humidity_pct: float = Field(ge=10, le=90)
    wind_ms: float = Field(ge=0.5, le=10)
    sky: Literal["clear", "haze", "cloud"]


class RestArea(Strict):
    id: str = Id
    name: str = Field(min_length=1, max_length=40)
    type: Literal["cooled", "shade"]
    seats: int = Field(ge=0, le=60)


class Task(Strict):
    id: str = Id
    name: str = Field(min_length=1, max_length=40)
    exposure: Literal["sun", "partial", "shade", "indoor"]
    workload: Literal["light", "moderate", "heavy"]
    clothing: Literal["work_clothes", "coveralls", "double_layer"] = "work_clothes"
    hours: float = Field(ge=0.5, le=10)
    start: str = Hhmm
    end: str = Hhmm
    crew_size: int = Field(ge=1, le=30)
    rest_area: str = Id
    walk_min: float = Field(default=3, ge=0, le=10)
    one_piece: bool = False
    can_wait: bool = True


class Worker(Strict):
    id: str = Id
    name: str = Field(min_length=1, max_length=30)
    lang: Literal["en", "ar"] = "en"
    task: str = Id
    status: Literal["new", "returning", "acclimatized"] = "acclimatized"
    day: int = Field(default=1, ge=1, le=9999)
    age: int | None = Field(default=None, ge=16, le=75)
    restriction: Literal["shaded_light_duty", "no_heat_work"] | None = None
    wearable: bool = False
    share_status: bool = False


class Scenario(Strict):
    id: str | None = Field(default=None, max_length=40)
    title: str | None = Field(default=None, max_length=80)
    title_ar: str | None = Field(default=None, max_length=80)
    season: Literal["summer", "autumn"]
    weather: Weather
    rest_areas: list[RestArea] = Field(min_length=1, max_length=lab.LIMITS["rest_areas"])
    shaded_places: int = Field(default=3, ge=0, le=20)
    tasks: list[Task] = Field(min_length=1, max_length=lab.LIMITS["tasks"])
    workers: list[Worker] = Field(default_factory=list, max_length=lab.LIMITS["workers"])


class Event(Strict):
    type: Literal["hotter", "humid", "calm", "cloud", "water_out", "ac_fails", "symptom", "wearable"]
    at: str = Hhmm
    target: str | None = Field(default=None, max_length=8)


class PrevTask(BaseModel):
    id: str = Id
    slots: list[int] = Field(default_factory=list, max_length=lab.SLOTS)


class PrevBreak(BaseModel):
    crew: str = Id
    start_q: int = Field(ge=0, lt=lab.SLOTS * 2)
    quarters: int = Field(ge=1, le=4)


class PrevAssignment(BaseModel):
    heat_slots: list[int] = Field(default_factory=list, max_length=lab.SLOTS)


class Previous(BaseModel):
    tasks: list[PrevTask] = Field(default_factory=list, max_length=lab.LIMITS["tasks"])
    breaks: list[PrevBreak] = Field(default_factory=list, max_length=lab.SLOTS * 2 * lab.LIMITS["tasks"])
    assignments: dict[str, PrevAssignment] = Field(default_factory=dict, max_length=lab.LIMITS["workers"])


class LabIn(Strict):
    scenario: Scenario
    now: str | None = Field(default=None, pattern=r"^\d\d:\d\d$")
    previous: Previous | None = None
    events: list[Event] = Field(default_factory=list, max_length=lab.LIMITS["events"])


@router.get("/lab/presets")
def presets(ctx: Ctx = Depends(context)) -> dict[str, Any]:
    ctx.require("lab.run")
    return {"presets": lab.presets(), "limits": lab.LIMITS, "label": "SIMULATION",
            "notice": "Sample data only: do not enter real people or health details. Nothing you enter is stored."}


@router.post("/lab/plan")
def plan(body: LabIn, ctx: Ctx = Depends(context)) -> dict[str, Any]:
    ctx.require("lab.run")
    if not _SOLVES.acquire(timeout=8):
        raise HTTPException(503, "The planner is busy with other reviewers. Try again in a few seconds.")
    try:
        out = lab.run(body.scenario.model_dump(), now=body.now,
                      previous=body.previous.model_dump() if body.previous else None,
                      events=[e.model_dump() for e in body.events])
    except lab.LabError as e:
        raise HTTPException(422, str(e)) from e
    finally:
        _SOLVES.release()
    ctx.sb.audit.append(at=ctx.sb.now(), actor=ctx.actor, role=ctx.role, action="lab.plan", resource="scenario_lab",
                        detail={"tasks": len(body.scenario.tasks), "named_workers": len(body.scenario.workers),
                                "events": len(body.events), "status": out["status"],
                                "revalidation": (out.get("revalidation") or {}).get("result")})
    return out
