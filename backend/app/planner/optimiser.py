"""Plan: CP-SAT crew scheduling over the Site Heat Twin (finalsystem.md §10.3 step 4, §11.5, G31).

Decision variables
  x[t, s]     crew of task t works in 30-minute slot s
  y[w, s]     unacclimatized worker w does heat work in slot s (else the shaded task)
  b[c, h, q]  crew c takes its hourly break in quarter q of hour h at its rest area

Hard constraints (never turned into penalties)
  earliest / latest times; contiguous pours; at most two segments otherwise
  required work is completed unless the supervisor marked the task deferrable
  no outdoor work in the forecast withdrawal band (conservative upper bound)
  no outdoor direct-sun work in the federal midday window (no exemption on file)
  every heat-work hour in acclimatization or buffer has a shaded break
  rest seats per 15-minute block never exceed working, accessible capacity
  unacclimatized workers: no heat work in buffer or harsher, minutes within the
  documented schedule (§9.6), induction and daily review before 07:00 for new
  workers, and shaded-task capacity respected

Lexicographic objectives (solved in sequence, each optimum fixed before the next)
  1. heavy-work worker-slots in the buffer band (G25)
  2. deferred work (deferrable tasks only)
  3. fairness: the largest crew share of harsh slots, plus moderate harsh work
  4. disruption: distance from the supervisor's draft
  5. acclimatization progress: use the documented schedule in safe bands

If no protected plan exists the result says so, names the binding constraints
and tests permitted remedies (counterfactuals). It never trades a rule for cost.
The result is a proposal only: the rule engine re-validates it independently
(certificate.py) and a supervisor approves it before anything is activated.
"""
from __future__ import annotations

import time
from typing import Any

from ortools.sat.python import cp_model

from ..core import policy
from .twin import HARSH, REST_MIN, SLOT_MIN, SLOTS, heat_allowance_min, hhmm_to_slot, slot_label

MAX_SEGMENTS = 2
INDUCTION_END = "07:00"   # new workers: daily review and training first (CoP 11.0 training duty)


def restriction_label(w: dict[str, Any]) -> str | None:
    """The clinician's operational label only (never the reason)."""
    r = w.get("restriction")
    label = r.get("label") if isinstance(r, dict) else r
    return label if label in ("shaded_light_duty", "no_heat_work") else None


def _build(world, g, extra_seats=None, task_overrides=None, relax: set[str] | None = None):
    relax = relax or set()
    zones = {z["id"]: z for z in world["zones"]}
    crews = {c["id"]: c for c in world["crews"]}
    rest = {r["id"]: dict(r) for r in world["rest_areas"]}
    for rid, add in (extra_seats or {}).items():
        rest[rid]["seats"] += add
    tasks = [dict(t, **(task_overrides or {}).get(t["id"], {})) for t in world["plan_tomorrow"]["tasks"]]
    shaded_cap = world["shaded_task"]["capacity"]
    m = cp_model.CpModel()
    x: dict[tuple[str, int], Any] = {}
    starts: dict[str, list] = {}
    deferred: dict[str, Any] = {}
    for t in tasks:
        z = zones[t["zone"]]
        heat = bool(t["outdoor"] or z["direct_sun"])
        lo = max(0, hhmm_to_slot(t["earliest"]))
        hi = min(SLOTS, hhmm_to_slot(t["latest_end"]))
        req = t["duration_min"] // SLOT_MIN
        fixed = t.get("fixed_start")
        for s in range(SLOTS):
            v = m.NewBoolVar(f"x_{t['id']}_{s}")
            x[(t["id"], s)] = v
            band = g["zones"][t["zone"]][s]["band"]
            # The withdrawal band is the zone's own measured heat: it stops ordinary work in that zone whether
            # the task is outdoors or not (the rule engine does the same; found by re-validation, 15 Aug replay).
            forbidden = (s < lo or s >= hi
                         or (band in ("withdrawal", "unavailable") and "withdrawal" not in relax)
                         or (t["outdoor"] and z["direct_sun"] and g["midday"][s] and "midday" not in relax))
            if forbidden:
                m.Add(v == 0)
        total = sum(x[(t["id"], s)] for s in range(SLOTS))
        d = m.NewIntVar(0, req, f"def_{t['id']}")
        deferred[t["id"]] = d
        m.Add(total + d == req)
        if not t.get("deferrable") and "deferral" not in relax:
            m.Add(d == 0)
        st = [m.NewBoolVar(f"st_{t['id']}_{s}") for s in range(SLOTS)]
        for s in range(SLOTS):
            prev = x[(t["id"], s - 1)] if s > 0 else 0
            m.Add(st[s] >= x[(t["id"], s)] - prev)
        if t.get("contiguous"):
            m.Add(sum(st) <= 1)
            done = m.NewBoolVar(f"done_{t['id']}")
            m.Add(d == 0).OnlyEnforceIf(done)
            m.Add(total == 0).OnlyEnforceIf(done.Not())
        else:
            m.Add(sum(st) <= MAX_SEGMENTS)
        if fixed:
            fs = hhmm_to_slot(fixed)
            for s in range(SLOTS):
                m.Add(x[(t["id"], s)] == (1 if fs <= s < fs + req else 0))
        starts[t["id"]] = st

    task_by_crew = {t["crew"]: t for t in tasks}
    bvars: dict[tuple[str, int, int], Any] = {}
    for c, t in task_by_crew.items():
        heat = bool(t["outdoor"] or zones[t["zone"]]["direct_sun"])
        for h in range(SLOTS // 2):
            need_min = max(REST_MIN.get(g["zones"][t["zone"]][2 * h + k]["band"], 0) for k in (0, 1))
            qs = [m.NewBoolVar(f"b_{c}_{h}_{q}") for q in range(4)]
            for q in range(4):
                bvars[(c, h, q)] = qs[q]
            works = m.NewBoolVar(f"w_{c}_{h}")
            m.AddMaxEquality(works, [x[(t["id"], 2 * h)], x[(t["id"], 2 * h + 1)]])
            if heat and need_min:
                m.Add(sum(qs) == 1).OnlyEnforceIf(works)
                m.Add(sum(qs) == 0).OnlyEnforceIf(works.Not())
                for q in range(4):
                    m.AddImplication(qs[q], x[(t["id"], 2 * h + q // 2)])
            else:
                m.Add(sum(qs) == 0)
    if "rest_capacity" not in relax:
        for rid, r in rest.items():
            cap = r["seats"] if r["working"] and r["accessible"] else 0
            open_q = (int(r["open"][:2]) * 60 + int(r["open"][3:]) - 300) // 15
            close_q = (int(r["close"][:2]) * 60 + int(r["close"][3:]) - 300) // 15
            users_by_crew = [c for c, t in task_by_crew.items() if zones[t["zone"]]["rest_area"] == rid]
            for h in range(SLOTS // 2):
                for q in range(4):
                    qq = 4 * h + q
                    users = [(c, bvars[(c, h, q)]) for c in users_by_crew]
                    if not users:
                        continue
                    if qq < open_q or qq >= close_q:
                        for _, v in users:
                            m.Add(v == 0)
                    m.Add(sum(crews[c]["size"] * v for c, v in users) <= cap)

    y: dict[tuple[str, int], Any] = {}
    # Individually scheduled workers: unacclimatized workers and anyone with a clinician restriction label.
    # Labels are never relaxed by a remedy (never_relaxed: clinician_restrictions).
    unaccl = [w for w in world["workers"] if policy.is_unacclimatized(w) or restriction_label(w)]
    shaded_use: dict[int, list] = {s: [] for s in range(SLOTS)}
    induction_slot = hhmm_to_slot(INDUCTION_END)
    for w in unaccl:
        t = task_by_crew.get(w["crew"])
        if not t:
            continue
        heat = bool(t["outdoor"] or zones[t["zone"]]["direct_sun"])
        label = restriction_label(w)
        blocked = (label == "no_heat_work" and heat) or \
            (label == "shaded_light_duty" and (t["workload"] == "heavy" or zones[t["zone"]]["direct_sun"]))
        is_unaccl = policy.is_unacclimatized(w)
        allowance = heat_allowance_min(w) // SLOT_MIN
        for s in range(SLOTS):
            v = m.NewBoolVar(f"y_{w['id']}_{s}")
            y[(w["id"], s)] = v
            m.AddImplication(v, x[(t["id"], s)])
            band = g["zones"][t["zone"]][s]["band"]
            if blocked:
                m.Add(v == 0)
            elif is_unaccl and heat and band in HARSH and "unacclimatized" not in relax:
                m.Add(v == 0)
            if not blocked and is_unaccl and heat and w.get("acclimatization") == "new" and s < induction_slot:
                m.Add(v == 0)
            if not heat and not blocked:
                m.Add(v == x[(t["id"], s)])
            off = m.NewBoolVar(f"off_{w['id']}_{s}")
            m.Add(off >= x[(t["id"], s)] - v)
            m.Add(off <= x[(t["id"], s)])
            m.Add(off <= 1 - v)
            shaded_use[s].append(off)
        if is_unaccl and "unacclimatized" not in relax:
            m.Add(sum(y[(w["id"], s)] for s in range(SLOTS)) <= allowance)
    for s, offs in shaded_use.items():
        if offs and "shaded_capacity" not in relax:
            m.Add(sum(offs) <= shaded_cap)

    heavy, moderate, crew_harsh = [], [], {}
    for t in tasks:
        size = crews[t["crew"]]["size"]
        heat = bool(t["outdoor"] or zones[t["zone"]]["direct_sun"])
        terms = [x[(t["id"], s)] for s in range(SLOTS) if heat and g["zones"][t["zone"]][s]["band"] in HARSH]
        expr = size * sum(terms) if terms else 0
        (heavy if t["workload"] == "heavy" else moderate if t["workload"] == "moderate" else []).append(expr)
        ch = m.NewIntVar(0, size * SLOTS, f"ch_{t['crew']}")
        m.Add(ch == expr)
        crew_harsh[t["crew"]] = ch
    max_crew = m.NewIntVar(0, 10000, "max_crew_harsh")
    m.AddMaxEquality(max_crew, list(crew_harsh.values()))
    disruption = []
    for t in tasks:
        d0 = hhmm_to_slot(t["draft_start"])
        disruption += [abs(s - d0) * starts[t["id"]][s] for s in range(SLOTS)]
        # Prefer one block of work over split segments.
        disruption.append(4 * sum(starts[t["id"]]))
    # Prefer breaks after 30-45 minutes of work in each hour (spread out, not back to back).
    disruption += [(3 - q) * v for (c, h, q), v in bvars.items()]
    objectives = [
        ("harsh_exposure", sum(heavy)),
        ("deferred_work", sum(deferred.values())),
        ("fairness", max_crew * 10 + sum(moderate)),
        ("disruption", sum(disruption)),
        ("acclimatization_progress", -sum(y.values()) if y else 0),
    ]
    return m, x, y, bvars, deferred, tasks, task_by_crew, zones, unaccl, objectives


def solve(world: dict[str, Any], g: dict[str, Any], time_limit_s: float = 8.0,
          extra_seats: dict[str, int] | None = None, task_overrides: dict[str, dict[str, Any]] | None = None,
          diagnose: bool = True) -> dict[str, Any]:
    t0 = time.perf_counter()
    m, x, y, bvars, deferred, tasks, task_by_crew, zones, unaccl, objectives = _build(
        world, g, extra_seats, task_overrides)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = 8
    stages, status = [], None
    for name, obj in objectives:
        m.Minimize(obj)
        status = solver.Solve(m)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            break
        val = int(round(solver.ObjectiveValue()))
        stages.append({"objective": name, "value": val, "status": solver.StatusName(status)})
        m.Add(obj <= val)
    runtime = round(time.perf_counter() - t0, 2)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        out = {"status": "NO_FEASIBLE_PROTECTED_PLAN", "solver": {"engine": "cp-sat (OR-Tools)",
               "status": solver.StatusName(status), "runtime_s": runtime}, "stages": stages,
               "message": "No feasible protected plan exists under the rules and resources given."}
        if diagnose:
            out["diagnosis"] = diagnose_infeasible(world, g, extra_seats, task_overrides)
        return out
    plan_tasks = []
    for t in tasks:
        slots = [s for s in range(SLOTS) if solver.Value(x[(t["id"], s)])]
        plan_tasks.append({**t, "slots": slots, "deferred_slots": solver.Value(deferred[t["id"]])})
    breaks = []
    for (c, h, q), v in bvars.items():
        if solver.Value(v):
            t = task_by_crew[c]
            breaks.append({"crew": c, "crews": [c], "start_q": 4 * h + q, "quarters": 1,
                           "rest_area": zones[t["zone"]]["rest_area"]})
    breaks.sort(key=lambda b: (b["start_q"], b["crew"]))
    assignments = {}
    for w in unaccl:
        t = task_by_crew.get(w["crew"])
        if not t:
            continue
        heat_slots = [s for s in range(SLOTS) if solver.Value(y[(w["id"], s)])]
        crew_slots = [s for s in range(SLOTS) if solver.Value(x[(t["id"], s)])]
        assignments[w["id"]] = {"heat_slots": heat_slots,
                                "shaded_slots": [s for s in crew_slots if s not in heat_slots],
                                "allowance_min": heat_allowance_min(w)}
    return {"status": "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE",
            "solver": {"engine": "cp-sat (OR-Tools)", "status": solver.StatusName(status), "runtime_s": runtime},
            "stages": stages,
            "plan": {"tasks": plan_tasks, "breaks": breaks, "assignments": assignments}}


REMEDIES = [
    ("rest_capacity", "Open a second approved rest area or add shaded seats"),
    ("deferral", "Postpone part of the work to another day"),
    ("unacclimatized", "Give unacclimatized workers other shaded tasks"),
    ("shaded_capacity", "Add shaded-task places for workers coming off heat work"),
]
REMEDIES_AR = {
    "rest_capacity": "افتح مكان راحة معتمداً ثانياً أو أضف مقاعد مظللة",
    "deferral": "أجّل جزءاً من العمل إلى يوم آخر",
    "unacclimatized": "أعطِ العمال غير المتأقلمين مهام أخرى في الظل",
    "shaded_capacity": "أضف أماكن لمهام الظل للعمال الخارجين من العمل في الحر",
    "reschedule": "انقل العمل إلى يوم أو ساعات خارج النطاق القاسي ونافذة منتصف النهار",
}


def diagnose_infeasible(world, g, extra_seats=None, task_overrides=None) -> dict[str, Any]:
    """Find which constraint families bind, by testing permitted remedies one at a time.

    Legal windows and the withdrawal band are never relaxed: they are reported as
    binding if nothing else helps."""
    binding, remedies = [], []
    for key, text in REMEDIES:
        m, *_rest = _build(world, g, extra_seats, task_overrides, relax={key})
        s = cp_model.CpSolver()
        s.parameters.max_time_in_seconds = 3.0
        st = s.Solve(m)
        if st in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            binding.append(key)
            remedies.append({"remedy": key, "text": text, "text_ar": REMEDIES_AR[key], "restores_feasibility": True})
    if not binding:
        binding = ["legal_window_or_withdrawal_band"]
        remedies.append({"remedy": "reschedule", "text": "Move the work to a day or hours outside the harsh "
                         "band and the midday window", "text_ar": REMEDIES_AR["reschedule"],
                         "restores_feasibility": None})
    return {"binding_constraints": binding, "permitted_remedies": remedies,
            "never_relaxed": ["midday_window", "withdrawal_band", "emergency_rules", "clinician_restrictions"]}


def changes_vs_draft(world: dict[str, Any], plan: dict[str, Any], g: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    zones = {z["id"]: z for z in world["zones"]}
    for t in plan["tasks"]:
        d0 = hhmm_to_slot(t["draft_start"])
        n = t["duration_min"] // SLOT_MIN
        before = f"{slot_label(d0)}-{slot_label(d0 + n)}"
        segs = _segments(t["slots"])
        after = ", ".join(f"{slot_label(a)}-{slot_label(b + 1)}" for a, b in segs) or "deferred"
        if before != after:
            harsh = [g["zones"][t["zone"]][s]["band"] for s in range(d0, min(SLOTS, d0 + n))]
            reason, reason_ar = [], []
            if "withdrawal" in harsh:
                reason.append(f"forecast withdrawal band in Zone {t['zone']}")
                reason_ar.append(f"نطاق الانسحاب المتوقع في المنطقة {t['zone']}")
            if any(g["midday"][s] for s in range(d0, min(SLOTS, d0 + n))) and zones[t["zone"]]["direct_sun"]:
                reason.append("federal midday break 12:30-15:00")
                reason_ar.append("استراحة منتصف النهار الاتحادية 12:30-15:00")
            if "buffer" in harsh and not reason:
                reason.append("less heavy work in the buffer band")
                reason_ar.append("عمل شاق أقل في النطاق العازل")
            out.append({"task": t["id"], "name": t["name"], "name_ar": t.get("name_ar"), "from": before,
                        "to": after, "reason": "; ".join(reason) or "fits rest capacity",
                        "reason_ar": "؛ ".join(reason_ar) or "يتناسب مع سعة أماكن الراحة"})
    return out


def _segments(slots: list[int]) -> list[tuple[int, int]]:
    segs = []
    for s in sorted(slots):
        if segs and s == segs[-1][1] + 1:
            segs[-1] = (segs[-1][0], s)
        else:
            segs.append((s, s))
    return segs
