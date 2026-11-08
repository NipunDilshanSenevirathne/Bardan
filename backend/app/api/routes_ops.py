"""Site protection console routes (supervisor and HSE). Operational schemas carry no clinical fields."""
from __future__ import annotations

import copy
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from ..ai import compiler as compiler_mod
from ..ai import copilot as copilot_mod
from ..ai import explain as explain_mod
from ..ai import gate as gate_mod
from ..ai.orchestrator import AgentDenied, AgentRun
from ..core import actions, content, policy, reporting
from ..core.history import history
from ..core.ledger import LedgerError
from ..core.live import worker_status
from ..core.scenario import REPLAY_DAY, simulated_reading
from ..insights.cusum import signals as watch_signals
from ..planner import certificate as cert
from ..planner.twin import draft_to_plan, grid, hhmm_to_slot, simulate
from .deps import Ctx, context, idempotent

router = APIRouter(prefix="/v1")
SITE = "site_demo"
FORBIDDEN_OPERATIONAL_KEYS = {"acr", "egfr", "usg", "value_clinical", "symptoms", "diagnosis", "results"}


def _site(site_id: str) -> None:
    if site_id != SITE:
        raise HTTPException(404, "Unknown site")


@router.get("/sites/{site_id}/operations")
def operations(site_id: str, ctx: Ctx = Depends(context)) -> dict[str, Any]:
    _site(site_id)
    ctx.require("ops.read")
    sb = ctx.sb
    w = sb.world
    with sb.lock:
        zones = []
        for z in w["zones"]:
            r = simulated_reading(w, z["id"], sb.now())
            age = None
            if r.get("observed_at"):
                age = int((datetime.fromisoformat(sb.now()) - datetime.fromisoformat(r["observed_at"])).total_seconds()
                          // 60)
            band = None
            fresh = policy.is_fresh({k: r.get(k) for k in ("kind", "value", "observed_at", "provenance")},
                                    datetime.fromisoformat(sb.now()))
            if fresh and r.get("value") is not None:
                band = policy.band_from_twl(float(r["value"])) if r["kind"] == "twl" else policy.band_from_wbgt(
                    float(r["value"]))
            zones.append({**{k: z[k] for k in ("id", "name", "name_ar", "outdoor", "direct_sun", "rest_area",
                                                "water_point", "map", "shade_fraction")},
                          "reading": {k: r.get(k) for k in ("kind", "value", "unit", "observed_at", "provenance",
                                                            "instrument")} | {"age_min": age, "simulated": True},
                          "band": band if fresh else "unavailable", "water": sb.water_status(z["id"])})
        workers = []
        for wk in w["workers"]:
            st = worker_status(sb, wk["id"], ctx.lang)
            workers.append({"id": wk["id"], "name": wk["name"], "crew": wk["crew"],
                            "acclimatization": wk["acclimatization"], "day": wk["day"],
                            "exposure_percent": st["worker"]["exposure_percent"], "state": st["decision"]["state"],
                            "assignment": st["assignment"], "tightened": st["tightened"],
                            "subcontractor": wk["subcontractor"]})
        projections = sb.clinical.operational_projection()
        labels = []
        for p in projections:
            wk = next((x for x in w["workers"] if x["id"] == p["worker_ref"]), None)
            if not wk:
                continue
            if p["label_id"] == "msg.restriction_label":
                text = content.render(p["label_id"], ctx.lang, name=wk["name"], time=p["until"][11:16])
            elif p["label_id"] == "msg.clinic_absence":
                text = content.render(p["label_id"], ctx.lang, name=wk["name"], time_range=p.get("time_range", ""))
            else:
                text = content.render(p["label_id"], ctx.lang, name=wk["name"])
            labels.append({"worker": wk["id"], "text": text, "status": p.get("status")})
        rest = []
        for r in w["rest_areas"]:
            rest.append({**r})
    plan = sb.active_plan()
    out = {"site": w["site"], "clock": sb.now(), "zones": zones, "workers": workers,
           "operational_labels": labels, "rest_areas": rest, "water_points": [
               {**wp, "status": sb.water_status(wp["zone"])} for wp in w["water_points"]],
           "responders": w["responders"], "toilets": w["toilets"],
           "active_plan": {"id": plan["scenario_id"], "activated_at": plan["activation"]["at"],
                           "certificate": (plan.get("certificate") or {}).get("certificate_id")} if plan else None,
           "emergencies": [{"id": e["id"], "zone": e["location"].get("zone"), "at": e["at"],
                            "states": [s["state"] for s in e["states"]], "closed": e["closed"],
                            "acknowledged": ({"at": e["acknowledged"]["at"], "role": e["acknowledged"]["role"]}
                                             if e.get("acknowledged") else None)}
                           for e in sb.emergencies],
           "notifications": [{**n, "text": content.render_notification(n, ctx.lang)}
                             for n in sb.ledger.notifications if n["to_role"] in (ctx.role, "supervisor")][-10:],
           "label": w["label"]}
    _assert_no_clinical(out)
    return out


def _assert_no_clinical(obj: Any) -> None:
    """Defence in depth: the operational schema must never carry clinical keys (invariant 5)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in FORBIDDEN_OPERATIONAL_KEYS:
                raise HTTPException(500, "Operational response blocked: clinical field detected")
            _assert_no_clinical(v)
    elif isinstance(obj, list):
        for v in obj:
            _assert_no_clinical(v)


@router.get("/tasks")
def tasks(ctx: Ctx = Depends(context)) -> dict[str, Any]:
    ctx.require("task.read")
    sb = ctx.sb
    with sb.lock:
        sb.ledger.tick(sb.now())
        items = [sb.ledger.public(t, ctx.role) for t in sb.ledger.tasks.values()]
    for t in items:
        t["label"] = content.label(content.TASK_LABELS, t["action_code"], ctx.lang)
    return {"tasks": sorted(items, key=lambda t: t["created_at"], reverse=True), "clock": sb.now()}


class TaskEventIn(BaseModel):
    action: str
    evidence: dict[str, Any] | None = None
    reason: str | None = Field(default=None, max_length=300)
    expected_version: int | None = None


ACTION_STATE = {"accept": "accepted", "start": "in_progress", "report_complete": "reported_complete",
                "verify": "verified", "escalate": "escalated", "cancel": "cancelled", "reopen": "reopened"}


@router.post("/tasks/{task_id}/events")
def task_event(task_id: str, body: TaskEventIn, ctx: Ctx = Depends(context),
               idempotency_key: str | None = Header(default=None, max_length=80)) -> dict[str, Any]:
    ctx.require("task.act")
    # A retried request (a dropped connection on a site network) returns the first result, never a second action.
    return idempotent(ctx, f"task:{task_id}:{idempotency_key}" if idempotency_key else None,
                      lambda: _task_event(task_id, body, ctx))


def _task_event(task_id: str, body: TaskEventIn, ctx: Ctx) -> dict[str, Any]:
    sb = ctx.sb
    with sb.lock:
        try:
            if body.action == "add_evidence":
                if not body.evidence:
                    raise LedgerError("evidence_required", "Evidence is required", 422)
                t = sb.ledger.add_evidence(task_id, body.evidence, actor=ctx.actor, role=ctx.role, at=sb.now())
                _side_effects(sb, t, body, ctx)
            elif body.action == "resolve_dispute":
                ctx.require("task.verify_independent", resource=f"tasks/{task_id}")
                t = sb.ledger.resolve_dispute(task_id, actor=ctx.actor, role=ctx.role, at=sb.now(),
                                              reason=body.reason or "")
            else:
                if body.action not in ACTION_STATE:
                    raise LedgerError("unknown_action", "Unknown action", 422)
                t = sb.ledger.get(task_id)
                if body.action == "accept" and t["state"] == "escalated" and ctx.role != "hse":
                    raise LedgerError("forbidden", "An escalated task is owned by the HSE lead now.", 403)
                t = sb.ledger.transition(task_id, ACTION_STATE[body.action], actor=ctx.actor, role=ctx.role,
                                         at=sb.now(), evidence=body.evidence, reason=body.reason,
                                         expected_version=body.expected_version)
                _side_effects(sb, t, body, ctx)
        except LedgerError as e:
            sb.audit.append(at=sb.now(), actor=ctx.actor, role=ctx.role, action=f"task.{body.action}",
                            resource=task_id, decision="denied", reason=e.code)
            raise HTTPException(e.status, str(e)) from e
        sb.audit.append(at=sb.now(), actor=ctx.actor, role=ctx.role, action=f"task.{body.action}", resource=task_id)
    return {"task": sb.ledger.public(t, ctx.role)}


def _side_effects(sb, t: dict[str, Any], body: TaskEventIn, ctx: Ctx) -> None:
    """Physical-world effects in the scenario: an independent check by HSE refills the water point. Accepting an
    emergency check task is the responder's acknowledgement of the alert."""
    if t.get("emergency") and body.action == "accept":
        rec = next((e for e in sb.emergencies if e["id"] == t["emergency"]), None)
        if rec and not rec.get("acknowledged"):
            actions.acknowledge_emergency(sb, rec["id"], actor=ctx.actor, role=ctx.role)
    if t["action_code"] == "WATER_RESTORE" and body.evidence:
        kind = body.evidence.get("kind")
        wp = next(w for w in sb.world["water_points"] if w["zone"] == t["zone_id"])
        phys = sb.world["physical"]["water"].setdefault(wp["id"], {})
        if kind in ("independent_spot_check", "water_point_check") and ctx.role == "hse":
            phys["refilled_at"] = sb.now()
        if kind == "water_point_check" and ctx.role == "supervisor" and body.evidence.get("water_actually_delivered"):
            phys["refilled_at"] = sb.now()
    if t["state"] == "verified" and t["action_code"] == "WATER_RESTORE":
        wp = next(w for w in sb.world["water_points"] if w["zone"] == t["zone_id"])
        wp["status"] = "available"
        wp["last_check"] = sb.now()
        wp["last_check_tier"] = t["achieved_tier"]


class ObservationIn(BaseModel):
    zone: str
    kind: str
    value: float
    unit: str
    observed_at: str
    provenance: str = "measured"
    instrument: str | None = None


@router.post("/observations")
def observation(body: ObservationIn, ctx: Ctx = Depends(context)):
    ctx.require("observation.write")
    expected = {"twl": "W/m2", "wbgt": "C"}
    if body.kind not in expected:
        raise HTTPException(422, "Only TWL and WBGT observations are accepted; air temperature is never "
                                 "labelled as either (T13).")
    if body.unit != expected[body.kind]:
        ctx.sb.audit.append(at=ctx.sb.now(), actor=ctx.actor, role=ctx.role, action="observation.quarantined",
                            resource=body.zone, decision="denied", reason="unit mismatch")
        raise HTTPException(422, f"Quarantined: {body.kind.upper()} must be in {expected[body.kind]}, got "
                                 f"'{body.unit}'. No silent conversion (T16).")
    try:
        policy.parse_time(body.observed_at)
    except ValueError as e:
        raise HTTPException(422, "Timestamps must include a UTC offset") from e
    ctx.sb.world["reading_overrides"][body.zone] = {**body.model_dump(), "entered_by": ctx.actor}
    ctx.sb.audit.append(at=ctx.sb.now(), actor=ctx.actor, role=ctx.role, action="observation.added",
                        resource=body.zone, detail=body.model_dump())
    return {"accepted": True, "observation": body.model_dump()}


@router.delete("/observations/{zone}")
def clear_observation(zone: str, ctx: Ctx = Depends(context)):
    ctx.require("observation.write")
    ctx.sb.world["reading_overrides"].pop(zone, None)
    return {"cleared": zone}


@router.get("/sites/{site_id}/forecast")
def forecast(site_id: str, mode: str = "scenario", ctx: Ctx = Depends(context)):
    _site(site_id)
    ctx.require("forecast.read")
    fc = ctx.sb.forecast("live" if mode == "live" else "scenario")
    if mode != "live" and fc.get("available"):
        fc = {**fc, "observed": _observed_so_far(ctx.sb), "observed_label": (
            "Derived WBGT from the simulated zone instruments (replayed weather), up to the sandbox clock. "
            "Live values govern; forecasts can only add protection.")}
    return fc


def _observed_so_far(sb) -> dict[str, list[dict[str, Any]]]:
    """Half-hourly derived WBGT per zone on the scenario day, up to the sandbox clock (for the chart overlay)."""
    from ..core.scenario import TZ, zone_wbgt_at
    clock = sb.now()
    if clock[:10] < REPLAY_DAY:
        return {}
    end = clock[11:16] if clock[:10] == REPLAY_DAY else "19:00"
    out: dict[str, list[dict[str, Any]]] = {}
    for z in sb.world["zones"]:
        rows = []
        for m in range(5 * 60, 19 * 60 + 1, 30):
            hhmm = f"{m // 60:02d}:{m % 60:02d}"
            if hhmm > end:
                break
            v = zone_wbgt_at(REPLAY_DAY, hhmm, z["id"])
            if v is not None:
                rows.append({"time": f"{REPLAY_DAY}T{hhmm}:00{TZ}", "wbgt_c": round(float(v), 2)})
        out[z["id"]] = rows
    return out


# ------------------------------------------------------------------ plans
def _summary(sc: dict[str, Any]) -> dict[str, Any]:
    keys = ("scenario_id", "kind", "status", "for_date", "created_at", "created_by", "metrics", "draft_metrics",
            "approval", "activation", "label", "changes", "solver", "stages", "certificate", "revalidation", "message",
            "diagnosis", "fallback", "forecast_issued_at", "forecast_label", "explanation", "inputs",
            "forecast_available")
    out = {k: sc.get(k) for k in keys if k in sc}
    if "revalidation" in out and out["revalidation"]:
        out["revalidation"] = {k: out["revalidation"][k] for k in ("engine", "result", "checks")} | {
            "violations": out["revalidation"]["violations"][:30], "violation_count": len(out["revalidation"]["violations"])}
    return out


@router.get("/plans")
def plans(ctx: Ctx = Depends(context)):
    ctx.require("plan.simulate")
    return {"plans": [_summary(s) for s in ctx.sb.plans.values()], "active": ctx.sb.active_plan_id}


@router.get("/plans/{plan_id}")
def plan_get(plan_id: str, ctx: Ctx = Depends(context)):
    ctx.require("plan.simulate")
    sc = ctx.sb.plans.get(plan_id)
    if not sc:
        raise HTTPException(404, "Plan not found")
    return {**_summary(sc), "plan": sc.get("plan"), "grid": sc.get("grid"), "twin": sc.get("twin"),
            "draft_twin": sc.get("draft_twin"), "worker_messages": sc.get("worker_messages"),
            "agent_run": sc.get("agent_run")}


@router.post("/plans/evaluate")
def plan_evaluate(ctx: Ctx = Depends(context)):
    ctx.require("plan.evaluate")
    with ctx.sb.lock:
        sc = ctx.sb.evaluate_draft(ctx.actor)
    return {**_summary(sc), "plan": sc["plan"], "grid": sc["grid"], "twin": sc["twin"]}


class OptimiseIn(BaseModel):
    extra_seats: dict[str, int] | None = None
    task_overrides: dict[str, dict[str, Any]] | None = None


@router.post("/plans/optimise")
def plan_optimise(body: OptimiseIn, ctx: Ctx = Depends(context)):
    ctx.require("plan.optimise")
    sb = ctx.sb
    run = AgentRun("planning", sb, kill_switch=sb.ai_enabled("plan") or True)
    with sb.lock:
        try:
            fc = run.call("get_zone_forecast", lambda: sb.forecast(), ref="site_demo/72h")
            run.call("run_site_twin", lambda: None, ref="draft_plan")
            sc = run.call("solve_schedule", lambda: sb.optimise(ctx.actor, extra_seats=body.extra_seats,
                                                                task_overrides=_clean_overrides(body.task_overrides)),
                          ref="cp-sat")
            if sc.get("status") in ("OPTIMAL", "FEASIBLE"):
                run.call("revalidate_plan", lambda: sc["revalidation"], ref=sc["scenario_id"])
                ex = run.call("explain_plan", lambda: explain_mod.plan_explanation(sc, ctx.lang,
                                                                                   sb.ai_enabled("explain")),
                              ref=sc["scenario_id"])
                sc["explanation"] = {"text": ex["text"], "source": ex["source"]}
                sb.record_trace({**ex["run"], "actor": ctx.actor, "input_ref": sc["scenario_id"]})
            rec = run.finish("completed")
            sc["agent_run"] = rec
        except AgentDenied as e:
            raise HTTPException(409, str(e)) from e
    return {**_summary(sc), "plan": sc.get("plan"), "grid": sc.get("grid"), "twin": sc.get("twin"),
            "draft_twin": sc.get("draft_twin"), "worker_messages": sc.get("worker_messages"),
            "agent_run": rec, "forecast_available": fc.get("available")}


def _clean_overrides(ov: dict[str, dict[str, Any]] | None) -> dict[str, dict[str, Any]] | None:
    if not ov:
        return None
    allowed = {"fixed_start", "deferrable", "duration_min"}
    return {tid: {k: v for k, v in o.items() if k in allowed} for tid, o in ov.items()}


class SimulateIn(BaseModel):
    base: str = "draft"                          # draft | plan id
    task_starts: dict[str, str] | None = None     # what-if: {"P1": "05:30"}
    extra_seats: dict[str, int] | None = None


@router.post("/plans/simulate")
def plan_simulate(body: SimulateIn, ctx: Ctx = Depends(context)):
    """What-if explorer (§10.5): read-only twin run with counterfactual changes, labelled SIMULATION."""
    ctx.require("plan.simulate")
    sb = ctx.sb
    world = copy.deepcopy(sb.world)
    for rid, add in (body.extra_seats or {}).items():
        for r in world["rest_areas"]:
            if r["id"] == rid:
                r["seats"] += int(add)
    fc = sb.forecast()
    g = grid(world, fc, REPLAY_DAY)
    if body.base == "draft":
        plan = draft_to_plan(world)
    else:
        sc = sb.plans.get(body.base)
        if not sc or "plan" not in sc:
            raise HTTPException(404, "Base plan not found")
        plan = copy.deepcopy(sc["plan"])
    for tid, start in (body.task_starts or {}).items():
        t = next((x for x in plan["tasks"] if x["id"] == tid), None)
        if t:
            n = t["duration_min"] // 30
            s0 = hhmm_to_slot(start)
            t["slots"] = list(range(s0, s0 + n))
    base_tw = simulate(sb.world, grid(sb.world, fc, REPLAY_DAY), draft_to_plan(sb.world) if body.base == "draft"
                       else sb.plans[body.base]["plan"])
    tw = simulate(world, g, plan)
    rv = cert.revalidate(world, g, plan, REPLAY_DAY)
    delta = {k: round(tw["metrics"][k] - base_tw["metrics"][k], 1) for k in tw["metrics"]
             if isinstance(tw["metrics"][k], (int, float))}
    return {"metrics": tw["metrics"], "baseline_metrics": base_tw["metrics"], "delta": delta,
            "rest_conflicts": tw["rest_conflicts"], "violations": tw["violations"][:20],
            "revalidation": {"result": rv["result"], "violations": len(rv["violations"])}, "label": "SIMULATION"}


@router.get("/sites/{site_id}/fairness")
def fairness_week(site_id: str, ctx: Ctx = Depends(context)):
    """Week-level fairness pattern by crew (T78). Crews only; never individual workers."""
    _site(site_id)
    ctx.require("plan.simulate")
    from ..planner.fairness import week_report
    rep = week_report(ctx.sb.world)
    sc = ctx.sb.plans.get(ctx.sb.active_plan_id or "") or next(
        (p for p in reversed(list(ctx.sb.plans.values())) if p.get("kind") == "optimised" and p.get("twin")), None)
    if sc and sc.get("twin"):
        sizes = {c["id"]: c["size"] for c in ctx.sb.world["crews"]}
        rep["today_plan"] = {"plan": sc["scenario_id"], "per_worker": {
            c: round(v / max(1, sizes.get(c, 1)), 1) for c, v in sc["twin"]["crew_harsh_hours"].items()}}
    return rep


@router.post("/plans/{plan_id}/approve")
def plan_approve(plan_id: str, ctx: Ctx = Depends(context)):
    ctx.require("plan.approve")
    sb = ctx.sb
    if plan_id not in sb.plans:
        raise HTTPException(404, "Plan not found")
    try:
        with sb.lock:
            sc = sb.approve_plan(plan_id, ctx.actor)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return _summary(sc)


@router.post("/plans/{plan_id}/activate")
def plan_activate(plan_id: str, ctx: Ctx = Depends(context)):
    ctx.require("plan.activate")
    sb = ctx.sb
    if plan_id not in sb.plans:
        raise HTTPException(404, "Plan not found")
    try:
        with sb.lock:
            sc = sb.activate_plan(plan_id, ctx.actor)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    return _summary(sc)


class FaultIn(BaseModel):
    kind: str = "midday"


@router.post("/plans/{plan_id}/fault-injection")
def plan_fault(plan_id: str, body: FaultIn, ctx: Ctx = Depends(context)):
    ctx.require("plan.simulate")
    sc = ctx.sb.plans.get(plan_id)
    if not sc or "plan" not in sc:
        raise HTTPException(404, "Plan not found")
    if body.kind not in ("midday", "withdrawal", "capacity", "remove_breaks"):
        raise HTTPException(422, "Unknown fault")
    g = grid(ctx.sb.world, ctx.sb.forecast(), REPLAY_DAY)
    bad = cert.inject_fault(sc["plan"], body.kind)
    rv = cert.revalidate(ctx.sb.world, g, bad, REPLAY_DAY)
    return {"fault": body.kind, "revalidation": {"result": rv["result"], "violations": rv["violations"][:12],
                                                 "violation_count": len(rv["violations"])},
            "activation": "blocked" if rv["result"] != "valid" else "possible",
            "label": "Fault injection test (T33/T75/T77)"}


# ------------------------------------------------------------- compliance
@router.get("/sites/{site_id}/compliance")
def compliance(site_id: str, ctx: Ctx = Depends(context)):
    _site(site_id)
    ctx.require("compliance.read")
    sb = ctx.sb
    h = history()
    tiers: dict[str, int] = {}
    states: dict[str, int] = {}
    for t in sb.ledger.tasks.values():
        states[t["state"]] = states.get(t["state"], 0) + 1
        if t["state"] == "verified":
            tiers[t["achieved_tier"]] = tiers.get(t["achieved_tier"], 0) + 1
    week = [d for d in h["days"] if d["date"] >= "2025-08-12"]
    midday = [{"date": d["date"], "outdoor_minutes_in_window": d["midday_outdoor_minutes"],
               "note": d["midday_note"]} for d in week]
    midday.append({"date": REPLAY_DAY, "outdoor_minutes_in_window": 0, "note": "Live: enforced by the rule engine"})
    breaks = {}
    for d in week:
        for crew, c in d["crews"].items():
            b = breaks.setdefault(crew, {"required": 0, "delivered_full": 0, "cut_short": 0})
            b["required"] += c["breaks_required"]
            b["delivered_full"] += c["breaks_delivered_full"]
            b["cut_short"] += c["breaks_cut_short"]
    checklist = [
        {"duty": "Heat-stress programme (CoP 11.0 §3.1.1(e))", "status": "in_place", "evidence": "Programme record",
         "tier": "E2"},
        {"duty": "TWL assessment and zone controls (§3.1.1(f))", "status": "live", "evidence": "Instrument records "
         "every 5 min (simulated)", "tier": "E3"},
        {"duty": "Acclimatization programme (§3.2(b)(i))", "status": "active", "evidence": "Daily reviews",
         "tier": "E2"},
        {"duty": "Potable water and electrolytes near work (§3.2(b)(v))", "status": "monitored",
         "evidence": "Water-point checks and worker disputes", "tier": "E3"},
        {"duty": "Shaded work, cooled rest and midday shelters (§3.2(c))", "status": "capacity_checked",
         "evidence": "Capacity certificate", "tier": "E3"},
        {"duty": "Training within 10 days (§2(d))", "status": "1 overdue", "evidence": "Training register",
         "tier": "E2"},
        {"duty": "Medical attention and first aid within 3 minutes (§3.1.1(l))", "status": "covered",
         "evidence": "3 responders on shift; drill pending", "tier": "E2"},
        {"duty": "Midday break 12:30-15:00 (MoHRE)", "status": "enforced", "evidence": "Rule engine + daily report",
         "tier": "E3"},
    ]
    rejected = [e for e in sb.audit.entries if e["action"] == "observation.quarantined"]
    failed_alerts = [n for n in sb.ledger.notifications if n["state"] != "delivered"]
    rates = []
    for crew, b in sorted(breaks.items()):
        if b["required"]:      # a crew with no required breaks (indoor work) has no rate, not a 0/0
            rates.append({"name": f"breaks_delivered_full:{crew}", "numerator": b["delivered_full"],
                          "denominator": b["required"], "tiers": ["E2"]})
    report = {"site": SITE, "date": REPLAY_DAY, "checklist": checklist, "midday": midday,
              "breaks_last_7_days": breaks, "tasks_by_state": states,
              "verified_by_tier": tiers, "tiers_never_merged": True, "training": h["training"],
              "rates": rates,
              "exclusions": {"rejected_readings": len(rejected), "failed_alerts": len(failed_alerts),
                             "disclosed": True,
                             "detail": ("Rejected readings (quarantined units or formats) and alerts that could "
                                        "not be delivered are counted here, not dropped.")},
              "rest_capacity": [{k: r[k] for k in ("id", "name", "seats", "cooled", "working", "open", "close")}
                                for r in sb.world["rest_areas"]],
              "responders": sb.world["responders"], "emergencies": len(sb.emergencies),
              "label": "SYNTHETIC; denominators shown; tiers reported separately"}
    report["validation"] = reporting.validate(report)
    return report


class ExemptionIn(BaseModel):
    task: str
    ref: str = Field(..., min_length=4, max_length=40)
    reason: str = Field(..., min_length=5, max_length=200)


@router.post("/exemptions")
def exemption(body: ExemptionIn, ctx: Ctx = Depends(context)):
    ctx.require("exemption.record", resource=body.task)
    rec = {"task": body.task, "ref": body.ref, "reason": body.reason, "authorised": True, "by": ctx.actor,
           "at": ctx.sb.now()}
    ctx.sb.world["exemptions"].append(rec)
    ctx.sb.audit.append(at=ctx.sb.now(), actor=ctx.actor, role=ctx.role, action="exemption.recorded",
                        resource=body.task, detail={"ref": body.ref})
    return rec


# ---------------------------------------------------------------- copilot
class CopilotIn(BaseModel):
    question: str = Field(..., min_length=2, max_length=400)


@router.post("/copilot/query")
def copilot(body: CopilotIn, ctx: Ctx = Depends(context)):
    ctx.require("copilot.query")
    sb = ctx.sb
    run_agent = AgentRun("compliance", sb)
    # Answer in the language the question was written in (found live: an Arabic question got an English answer).
    asked = gate_mod.language_of(body.question)
    lang = asked if asked in ("en", "ar") else ctx.lang
    out = run_agent.call("query_metrics", lambda: copilot_mod.query(body.question, lang=lang, sb=sb,
                                                                     ai_on=sb.ai_enabled("copilot")),
                         ref="metrics_layer")
    run_agent.finish("completed")
    run = sb.record_trace({**out["run"], "actor": ctx.actor, "question": body.question})
    sb.copilot_log.append({"at": sb.now(), "role": ctx.role, "question": body.question,
                           "decision": out["result"]["decision"], "query_hash": out["result"].get("query_hash"),
                           "health": (out["result"].get("plan") or {}).get("metric") in copilot_mod.HEALTH_METRICS})
    return {**out["result"], "trace_id": run["id"]}


# ------------------------------------------------------------ policy packs
@router.get("/policy/packs")
def packs(ctx: Ctx = Depends(context)):
    return {"active": [policy.heat_pack(), policy.midday_pack()],
            "drafts": list(ctx.sb.policy_drafts.values()),
            "source_document": compiler_mod.source_text()}


@router.post("/policy/drafts")
def compile_draft(ctx: Ctx = Depends(context)):
    ctx.require("policy.compile")
    sb = ctx.sb
    run = AgentRun("policy_compiler", sb)
    out = run.call("draft_rules", lambda: compiler_mod.compile_document(sb.ai_enabled("compile")),
                   ref="sharjah_demo_excerpt")
    run.call("generate_tests", lambda: None)
    run.finish("completed")
    d = out["draft"]
    did = f"draft_{len(sb.policy_drafts) + 1}"
    d["id"] = did
    sb.policy_drafts[did] = d
    sb.record_trace({**out["run"], "actor": ctx.actor, "input_ref": "sharjah_demo_excerpt"})
    sb.audit.append(at=sb.now(), actor=ctx.actor, role=ctx.role, action="policy.draft_compiled", resource=did)
    return d


class ApproveIn(BaseModel):
    note: str = Field(default="", max_length=300)


@router.post("/policy/drafts/{draft_id}/approve")
def approve_draft(draft_id: str, body: ApproveIn, ctx: Ctx = Depends(context)):
    ctx.require("policy.approve")
    d = ctx.sb.policy_drafts.get(draft_id)
    if not d:
        raise HTTPException(404, "Draft not found")
    try:
        compiler_mod.approve(d, actor=ctx.actor, role=ctx.role, at=ctx.sb.now(), note=body.note)
    except (PermissionError, ValueError) as e:
        raise HTTPException(409, str(e)) from e
    ctx.sb.audit.append(at=ctx.sb.now(), actor=ctx.actor, role=ctx.role, action="policy.approve", resource=draft_id)
    return d


@router.post("/policy/drafts/{draft_id}/activate")
def activate_draft(draft_id: str, ctx: Ctx = Depends(context)):
    ctx.require("policy.approve")
    d = ctx.sb.policy_drafts.get(draft_id)
    if not d:
        raise HTTPException(404, "Draft not found")
    try:
        compiler_mod.activate(d, actor=ctx.actor, at=ctx.sb.now())
    except (PermissionError, ValueError) as e:
        ctx.sb.audit.append(at=ctx.sb.now(), actor=ctx.actor, role=ctx.role, action="policy.activate",
                            resource=draft_id, decision="denied", reason=str(e))
        raise HTTPException(409, str(e)) from e
    ctx.sb.audit.append(at=ctx.sb.now(), actor=ctx.actor, role=ctx.role, action="policy.activate", resource=draft_id)
    return d


# --------------------------------------------------------------- insights
@router.get("/insights/signals")
def insights(ctx: Ctx = Depends(context)):
    ctx.require("insights.read")
    run = AgentRun("insight", ctx.sb)
    s = run.call("aggregate_query", watch_signals, ref="water_gap_events_by_subcontractor")
    run.finish("completed")
    return {**s, "review_tasks": ctx.sb.review_tasks}


class ReviewIn(BaseModel):
    signal_id: str


@router.post("/insights/review-tasks")
def review_task(body: ReviewIn, ctx: Ctx = Depends(context)):
    ctx.require("insights.approve")
    sig = next((s for s in watch_signals()["signals"] if s.get("signal_id") == body.signal_id and s.get("alarm")),
               None)
    if not sig:
        raise HTTPException(404, "No alarm for that signal")
    t = ctx.sb.ledger.create(action_code="HSE_REVIEW", zone="B", now=ctx.sb.now(),
                             rationale=sig["action"]["draft_review_task"], source="watch_signal_approved_by_hse",
                             rationale_ar=sig["action"].get("draft_review_task_ar"),
                             extra={"signal": body.signal_id})
    ctx.sb.review_tasks.append({"signal": body.signal_id, "task": t["id"], "approved_by": ctx.actor})
    return {"task": ctx.sb.ledger.public(t, ctx.role)}
