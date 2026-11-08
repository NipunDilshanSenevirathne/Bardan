"""On-the-day protection: live values govern and can only tighten the plan (§9, §10.4, §26.1).

For a worker at the sandbox clock this module resolves the current assignment
from the active plan, gathers typed inputs with provenance (live instrument
reading, known resource status, recent private check-ins, restriction label,
exemptions) and runs the deterministic policy engine. If the live state stops
the planned activity (for example a new worker when a zone turns to the buffer
band), the plan tightens at once: the worker is moved to the shaded task and
the supervisor gets a task. Nothing here ever relaxes a control.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from . import content, policy
from .scenario import simulated_reading
from ..planner.twin import hhmm_to_slot, slot_label


def current_slot(clock: str) -> int:
    return hhmm_to_slot(clock[11:16])


def assignment(sb, worker: dict[str, Any]) -> dict[str, Any]:
    """Where the active plan puts this worker now."""
    world = sb.world
    clock = sb.now()    # live during an observed drill
    plan = sb.active_plan()
    shaded = world["shaded_task"]
    if not plan or clock[:10] != plan["for_date"]:
        return {"kind": "off_shift", "label_en": "No active plan for today", "label_ar": "لا توجد خطة فعالة اليوم"}
    s = current_slot(clock)
    tight = sb.tightened.get(worker["id"])
    task = next((t for t in plan["plan"]["tasks"] if t["crew"] == worker["crew"]), None)
    if not task:
        return {"kind": "off_shift", "label_en": "Not scheduled", "label_ar": "غير مجدول"}
    zone = next(z for z in world["zones"] if z["id"] == task["zone"])
    if s not in task["slots"]:
        # Outside work slots: midday rest or finished.
        if policy.in_midday_window(datetime.fromisoformat(clock)) and zone["direct_sun"]:
            return {"kind": "midday_rest", "task": task, "zone": zone, "place": "R3"}
        return {"kind": "not_working", "task": task, "zone": zone,
                "next": next((slot_label(x) for x in task["slots"] if x > s), None)}
    a = (plan["plan"].get("assignments") or {}).get(worker["id"])
    on_heat = True
    if a is not None:
        on_heat = s in a["heat_slots"]
    if tight and tight["since_slot"] <= s:
        on_heat = False
    if worker.get("restriction") and worker["restriction"].get("label") in ("shaded_light_duty", "no_heat_work"):
        on_heat = False
    br = _break_now(plan, worker["crew"], clock)
    if not on_heat and (zone["outdoor"] or zone["direct_sun"]):
        sz = next(z for z in world["zones"] if z["id"] == shaded["zone"])
        return {"kind": "shaded_task", "task": {**shaded, "crew": worker["crew"]}, "zone": sz,
                "from_task": task, "tightened": bool(tight), "on_break": br}
    return {"kind": "task", "task": task, "zone": zone, "on_break": br}


def _break_now(plan: dict[str, Any], crew: str, clock: str) -> dict[str, Any] | None:
    t = int(clock[11:13]) * 60 + int(clock[14:16]) - 300
    q = t // 15
    for b in plan["plan"]["breaks"]:
        if crew in (b.get("crews") or [b["crew"]]):
            if b["start_q"] <= q < b["start_q"] + b["quarters"]:
                return b
    return None


def next_breaks(plan: dict[str, Any], crew: str, clock: str, n: int = 3) -> list[dict[str, Any]]:
    t = int(clock[11:13]) * 60 + int(clock[14:16]) - 300
    out = []
    for b in plan["plan"]["breaks"]:
        if crew in (b.get("crews") or [b["crew"]]) and (b["start_q"] + b["quarters"]) * 15 > t:
            m = 300 + b["start_q"] * 15
            out.append({"time": f"{m // 60:02d}:{m % 60:02d}", "rest_area": b["rest_area"], "minutes": 15 * b["quarters"]})
    return out[:n]


def worker_status(sb, worker_id: str, lang: str = "en", apply_tightening: bool = True) -> dict[str, Any]:
    world = sb.world
    w = next(x for x in world["workers"] if x["id"] == worker_id)
    clock = sb.now()    # live during an observed drill
    now = datetime.fromisoformat(clock)
    a = assignment(sb, w)
    restriction = sb.clinical.restrictions.get(worker_id)
    zone = a.get("zone")
    task = a.get("task")
    symptoms = sb.recent_symptoms(worker_id)
    obs = simulated_reading(world, zone["id"], clock) if zone else None
    water_ok = sb.water_status(zone["id"]) != "reported_empty" if zone else True
    exemption = sb.exemption_for(task["id"]) if task else None
    inp = {
        "now": clock,
        "zone": {"outdoor": zone["outdoor"], "direct_sun": zone["direct_sun"]} if zone else {},
        "task": {"workload": task["workload"], "outdoor": task["outdoor"]} if task else {},
        "worker": {"acclimatization": w["acclimatization"], "day": w["day"],
                   "restriction": (restriction or {}).get("label") if restriction and restriction["label"] != "none"
                   else None},
        "observation": {k: obs[k] for k in ("kind", "value", "observed_at", "provenance")} if obs else None,
        "resources": {"water_available": water_ok},
        "symptoms": symptoms,
        "exemption": {"authorised": True, "ref": exemption["ref"]} if exemption else None,
    }
    if a["kind"] in ("off_shift", "not_working", "midday_rest") and not symptoms:
        res = policy.evaluate({**inp, "task": {"workload": "light", "outdoor": False},
                               "zone": {"outdoor": False, "direct_sun": False}})
        if a["kind"] == "midday_rest":
            res = {**res, "actions": sorted(set(res["actions"]) | {"MOVE_TO_SHADE"}),
                   "reasons": ["AE-FED-MIDDAY:window", *res["reasons"]]}
    else:
        res = policy.evaluate(inp)
    tightened = None
    if apply_tightening and a["kind"] == "task" and res["state"] == "stop" and \
            "UNACCLIMATIZED_STOP_HEAT_WORK" in res["actions"] and not symptoms:
        tightened = sb.tighten(w, a, res, obs)
        a = assignment(sb, w)
        task, zone = a.get("task"), a.get("zone")
        obs2 = simulated_reading(world, zone["id"], clock)
        res2 = policy.evaluate({**inp, "zone": {"outdoor": zone["outdoor"], "direct_sun": zone["direct_sun"]},
                                "task": {"workload": task["workload"], "outdoor": task["outdoor"]},
                                "observation": {k: obs2[k] for k in ("kind", "value", "observed_at", "provenance")}})
        res = {**res2, "tightened_from": {"task": tightened["from_task"], "reasons": res["reasons"]}}
        obs = obs2
    age_min = None
    if obs and obs.get("observed_at"):
        age_min = int((now - datetime.fromisoformat(obs["observed_at"])).total_seconds() // 60)
    plan = sb.active_plan()
    breaks = next_breaks(plan, w["crew"], clock) if plan else []
    msg = explain_template(sb, w, a, res, lang, breaks)
    return {
        "worker": {"id": w["id"], "name": w["name"], "crew": w["crew"], "acclimatization": w["acclimatization"],
                   "day": w["day"], "exposure_percent": policy.acclimatization_percent(w), "buddy": w.get("buddy"),
                   "buddy_name": next((x["name"] for x in sb.world["workers"] if x["id"] == w.get("buddy")), None),
                   "lang": w["lang"]},
        "clock": clock, "assignment": _public_assignment(a), "decision": res,
        "inputs": {
            "observation": {**obs, "age_min": age_min} if obs else None,
            "water": "reported_empty" if not water_ok else "available",
            "symptoms_recent": bool(symptoms), "restriction_label": (restriction or {}).get("label"),
            "exemption": exemption["ref"] if exemption else None,
        },
        "breaks": breaks, "message": msg, "tightened": tightened is not None or bool(a.get("tightened")),
        "policy_versions": world["site"]["policy_packs"],
        "state_label": content.STATE_LABELS[res["state"]][lang],
        "actions": [{"code": c, "label": content.label(content.ACTION_LABELS, c, lang)} for c in res["actions"]],
    }


def explain_template(sb, w, a, res, lang: str, breaks: list[dict[str, Any]]) -> dict[str, Any]:
    world = sb.world
    rest = {r["id"]: r for r in world["rest_areas"]}
    state = res["state"]
    if state == "emergency":
        tid = "msg.emergency"
        slots = {}
    elif "triage:possible_muscle_breakdown" in res["reasons"]:
        tid, slots = "msg.muscle_dark_urine", {}
    elif "triage:concerning_symptom" in res["reasons"]:
        tid, slots = "msg.concerning_symptom", {}
    elif state == "unavailable":
        tid, slots = "msg.assessment_unavailable", {}
    elif "resources:water_unavailable" in res["reasons"]:
        tid, slots = "msg.missing_resource", {}
    elif a["kind"] == "midday_rest" or "AE-FED-MIDDAY:window" in res["reasons"]:
        tid, slots = "msg.midday_break", {"place": _name(rest["R3"], lang)}
    elif a["kind"] == "shaded_task" and a.get("tightened"):
        tid, slots = "msg.new_worker_harsh", {"name": w["name"].split()[0]}
    elif state == "stop":
        place = _name(rest[a["zone"]["rest_area"]], lang) if a.get("zone") else ""
        tname = (a.get("task") or {}).get("name_ar" if lang == "ar" else "name", "")
        tid, slots = "msg.stop_task", {"task": tname, "place": place}
    elif state == "enhanced":
        place = _name(rest[a["zone"]["rest_area"]], lang) if a.get("zone") else ""
        minutes = policy.heat_pack()["rest_minutes_per_hour_demo"].get(res.get("band") or "acclimatization", 10)
        tid, slots = "msg.enhanced", {"place": place, "minutes": minutes}
    else:
        tid, slots = ("msg.routine_plan_fluid" if sb.clinical.has_fluid_plan(w["id"]) else "msg.routine_plan"), {}
    return {"template_id": tid, "text": content.render(tid, lang, **slots), "lang": lang, "source": "approved_template"}


def _name(obj: dict[str, Any], lang: str) -> str:
    return obj.get("name_ar") if lang == "ar" and obj.get("name_ar") else obj["name"]


def _public_assignment(a: dict[str, Any]) -> dict[str, Any]:
    out = {"kind": a["kind"]}
    if a.get("task"):
        t = a["task"]
        out["task"] = {k: t.get(k) for k in ("id", "name", "name_ar", "workload", "outdoor", "zone")}
    if a.get("zone"):
        z = a["zone"]
        out["zone"] = {k: z.get(k) for k in ("id", "name", "name_ar", "outdoor", "direct_sun", "rest_area",
                                              "water_point", "walk_min")}
    if a.get("from_task"):
        out["from_task"] = {k: a["from_task"].get(k) for k in ("id", "name", "name_ar", "zone")}
    for k in ("tightened", "next", "place"):
        if a.get(k) is not None:
            out[k] = a[k]
    if a.get("on_break"):
        out["on_break"] = True
    return out
