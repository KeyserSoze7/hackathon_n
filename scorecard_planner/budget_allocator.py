"""
3B as budget allocation (no forecasting).

Problem: choose which (road, issue) items to fund and with which repair method, to maximise
harm avoided within a budget. A multiple-choice knapsack, solved exactly as a MILP (SciPy/HiGHS).

  item i      = one road segment x one issue type seen there this season (867 items)
  n_i         = how many times it needed fixing this season (+ open complaints) = demand, from history
  H_i         = harm per occurrence = severity (from SLA class) x impact (who gets hurt)
  method m    : r_m = observed 30-day failure rate, c_im = rate-card cost on this road
  benefit_im  = n_i * H_i * (1 - r_m)         harm avoided, durable methods avoid more
  cost_im     = n_i * c_im * (1 + r_m)        rate-card price incl. expected re-work

  max  sum benefit_im x_im
  s.t. sum_m x_im <= 1                        one method per item
       sum cost_im x_im <= B                  budget
       sum_{i in ward w} cost x >= floor_w    equity floor per ward (optional)
  Surface defects on roads under DLP are not in the budget: they go to Bucket A (contractor owes the fix,
  Rs 0 to BMC). Drainage/manhole/utility issues on those roads are not DLP liability, so BMC still pays (Bucket B).
"""
import json, pathlib
import numpy as np, pandas as pd
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import lil_matrix

MIN_METHOD_JOBS = 15
EQUITY_FLOOR = 0.5   # each ward gets >= 50% of its proportional share of the budget (if it has the demand)
# Issue types the original contractor's DLP covers (road-surface defects). Matches the audit engine's
# DLP_PAID_TWICE detector (audit_engine/detectors.py: cold/hot mix, mastic, paver relaid). Cave-ins are excluded:
# they are excavation/pipeline (utility) jobs in this data.
DLP_WORK_TYPES = {"Pothole", "Broken paver blocks"}
UNDER_REPORTED_IMPACT = 0.3  # silence-adjusted need: wards with high physical risk but few complaints


# ------------------------------------------------------------------ build items
def impact_table(st, act, under_reported=frozenset()):
    s = st.merge(act, on="road_id")
    s["under_reported"] = s.ward_code.isin(under_reported)
    p90 = lambda c: max(float(s[c].quantile(.9)), 1.0)
    s["impact"] = (1
                   + 0.8 * (s.hotspot_dist_m < 800)
                   + 0.8 * (s.hospitals_emergency > 0)
                   + 0.4 * (s.schools > 0)
                   + 0.5 * s.peak_hour_vehicles / s.peak_hour_vehicles.max()
                   + 0.3 * (s.bus_route == "Y")
                   + 0.6 * np.minimum(s.road_accident_harm / p90("road_accident_harm"), 1)
                   + 0.4 * np.minimum(s.open_complaints / p90("open_complaints"), 1)
                   + UNDER_REPORTED_IMPACT * s.under_reported)
    q75 = {c: s[c].quantile(.75) for c in ["peak_hour_vehicles", "road_accident_harm"]}
    def codes(r):
        c = []
        if r.hotspot_dist_m < 800: c.append("FLOOD_SPOT")
        if r.hospitals_emergency > 0: c.append("AMBULANCE_ROUTE")
        if r.schools > 0: c.append("SCHOOL_ZONE")
        if r.peak_hour_vehicles >= q75["peak_hour_vehicles"]: c.append("HIGH_TRAFFIC")
        if r.road_accident_harm > 0 and r.road_accident_harm >= q75["road_accident_harm"]: c.append("ACCIDENT_PRONE")
        if r.all_reopens >= 2: c.append("REPEAT_FAILURE")
        if r.open_complaints > 0: c.append("OPEN_COMPLAINTS")
        if r.under_reported: c.append("UNDER_REPORTED_WARD")
        if r.under_dlp == "Y": c.append("UNDER_DLP")
        return c
    s["reason_codes"] = s.apply(codes, axis=1)
    return s


def build_items(d):
    wo = d["v_wo_context"]
    rc = d["rate_card"].set_index("repair_method")
    roads = impact_table(d["v_road_static"], d["v_road_activity"], d.get("under_reported", frozenset()))

    meth = (wo.groupby(["work_type", "repair_method"])
              .agg(jobs=("cost_inr", "size"), reopen=("reopened_within_30d", lambda s: (s == "Y").mean()))
              .reset_index())
    meth = meth[meth.jobs >= MIN_METHOD_JOBS]

    it = (wo.groupby(["road_id", "work_type"])
            .agg(jobs=("work_order_id", "size"), median_area=("area_sqm", "median"),
                 sla_hours=("sla_hours", "median"), spent_2025=("cost_inr", "sum"),
                 reopens=("reopened_within_30d", lambda s: (s == "Y").sum()),
                 wo_ids=("work_order_id", lambda s: list(s)[:8]))
            .reset_index())
    it = it.merge(roads, on="road_id")
    # open complaints are attached to the road's most frequent issue type
    dom = it.sort_values("jobs", ascending=False).drop_duplicates("road_id").set_index("road_id").work_type
    it["n"] = it.jobs + np.where(it.work_type.values == dom.reindex(it.road_id).values, it.open_complaints, 0)
    it["severity"] = 168.0 / it.sla_hours          # 24h SLA -> 7, 168h -> 1
    it["H"] = it.severity * it.impact
    it["item_id"] = it.road_id + "|" + it.work_type
    it["dlp_owed"] = (it.under_dlp == "Y") & it.work_type.isin(DLP_WORK_TYPES)

    opts = []
    for i, r in it.iterrows():
        for _, m in meth[meth.work_type == r.work_type].iterrows():
            unit = rc.loc[m.repair_method]
            c = unit.standard_rate_inr * (r.median_area if unit.unit == "per sqm" else 1)
            opts.append({"item_id": r.item_id, "method": m.repair_method, "method_reopen": m.reopen,
                         "unit_cost": c, "cost": r.n * c * (1 + m.reopen),
                         "benefit": r.n * r.H * (1 - m.reopen)})
    return it.reset_index(drop=True), pd.DataFrame(opts), meth


# ------------------------------------------------------------------ solve
def solve(items, opts, budget, floors=None):
    """Exact MILP. floors: {ward_code: min spend}. Returns opts subset chosen."""
    o = opts.reset_index(drop=True)
    k = len(o)
    item_ix = {iid: j for j, iid in enumerate(o.item_id.unique())}
    A = lil_matrix((len(item_ix) + 1 + len(floors or {}), k))
    for col, iid in enumerate(o.item_id):
        A[item_ix[iid], col] = 1
    A[len(item_ix), :] = o.cost.values
    lo = [0] * len(item_ix) + [0]
    hi = [1] * len(item_ix) + [budget]
    ward = o.item_id.map(items.set_index("item_id").ward_code)
    for j, (w, f) in enumerate((floors or {}).items()):
        row = len(item_ix) + 1 + j
        for col in np.where(ward.values == w)[0]:
            A[row, col] = o.cost.iat[col]
        lo.append(f); hi.append(np.inf)
    res = milp(c=-o.benefit.values, constraints=LinearConstraint(A.tocsr(), lo, hi),
               integrality=np.ones(k), bounds=Bounds(0, 1), options={"time_limit": 60, "mip_rel_gap": 1e-4})
    if res.x is None:
        raise RuntimeError(res.message)
    return o[res.x > 0.5]


def equity_floors(items, opts, d, budget):
    w = d["wards"].set_index("ward_code").monsoon_repair_budget_inr_2025
    share = w / w.sum()
    max_need = (opts.groupby("item_id").cost.min()
                .groupby(items.set_index("item_id").ward_code).sum())
    return {k: float(min(EQUITY_FLOOR * share[k] * budget, 0.95 * max_need.get(k, 0))) for k in share.index}


# ------------------------------------------------------------------ baselines (same budget)
def greedy(items, opts, budget, rank_key, method_rule):
    chosen, spent = [], 0
    pick = opts.loc[opts.groupby("item_id")[method_rule].idxmin()].set_index("item_id")
    order = items.sort_values(rank_key, ascending=False).item_id
    for iid in order:
        if iid in pick.index and spent + pick.loc[iid, "cost"] <= budget:
            spent += pick.loc[iid, "cost"]; chosen.append(iid)
    return pick.loc[chosen].reset_index()


# ------------------------------------------------------------------ outputs
def explain(r, alt):
    pl = lambda k, w: f"{k} {w}" + ("" if k == 1 else "s")
    s = (f"{r.work_type} on {r.road_name} ({r.ward_code}): needed {pl(int(r.jobs), 'repair')} this season"
         + (f", {pl(int(r.open_complaints), 'complaint')} still open" if r.open_complaints and r.work_type == r.dom else "") + ". ")
    if r.reason_codes:
        s += "High stakes: " + ", ".join(c.replace("_", " ").lower() for c in r.reason_codes if c != "UNDER_DLP") + ". "
    if r.bucket == "A_OWED_BY_CONTRACTOR_DLP":
        return s + "Road is under warranty, so the original contractor must fix it at no cost to BMC."
    if r.under_dlp == "Y":
        s += "Road is under warranty, but this is not a surface defect, so BMC pays. "
    if r.funded:
        s += f"Funded with {r.method} ({r.method_reopen:.0%} fail rate)"
        if alt is not None and alt.method != r.method:
            s += (f" instead of {alt.method} ({alt.method_reopen:.0%}): the extra Rs {r.cost - alt.cost:,.0f} "
                  f"avoids {100 * (r.benefit / alt.benefit - 1):.0f}% more harm, which is worth it on a road with these stakes")
        return s + "."
    return s + "Not funded at this budget: lower harm avoided per rupee than the funded items."


def run(d, budget=None, out_dir=None):
    items, opts, meth = build_items(d)
    dlp = items.dlp_owed
    a_items, b_items = items[dlp], items[~dlp]
    b_opts = opts[opts.item_id.isin(b_items.item_id)]
    full_need = float(b_opts.groupby("item_id").cost.min().sum())
    wb = d["wards"].set_index("ward_code").monsoon_repair_budget_inr_2025
    spent_w = d["work_orders"].groupby("ward_code").cost_inr.sum()
    remaining_w = (wb - spent_w.reindex(wb.index).fillna(0)).clip(lower=0)
    budget = budget or float(remaining_w.sum())   # default scenario: money wards still have left in 2025

    floors = equity_floors(b_items, b_opts, d, budget)
    chosen = solve(b_items, b_opts, budget, floors)
    total_possible = float(b_opts.groupby("item_id").benefit.max().sum())

    base1 = greedy(b_items, b_opts, budget, "n", "unit_cost")                 # complaint/volume-driven, cheapest patch
    base2 = greedy(b_items, b_opts, budget, "H", "unit_cost")                 # stakes-first, cheapest patch
    hv = lambda df: float(df.benefit.sum())
    comparison = {
        "optimizer": {"harm_avoided": round(hv(chosen)), "spend_inr": int(chosen.cost.sum()), "items": len(chosen)},
        "baseline_volume_first_cheapest_patch": {"harm_avoided": round(hv(base1)), "spend_inr": int(base1.cost.sum()), "items": len(base1)},
        "baseline_stakes_first_cheapest_patch": {"harm_avoided": round(hv(base2)), "spend_inr": int(base2.cost.sum()), "items": len(base2)},
        "max_possible_harm_avoided": round(total_possible),
    }
    comparison["uplift_vs_volume_first_pct"] = round(100 * (hv(chosen) / hv(base1) - 1), 1)
    comparison["uplift_vs_stakes_first_pct"] = round(100 * (hv(chosen) / hv(base2) - 1), 1)

    curve = []
    for f in [0.1, 0.2, 0.3, 0.5, 0.75, 1.0]:
        B = f * full_need
        o = solve(b_items, b_opts, B, equity_floors(b_items, b_opts, d, B))
        g1 = greedy(b_items, b_opts, B, "n", "unit_cost"); g2 = greedy(b_items, b_opts, B, "H", "unit_cost")
        curve.append({"share_of_need": f, "budget_inr": int(B), "optimizer": round(hv(o)),
                      "volume_first_cheapest": round(hv(g1)), "stakes_first_cheapest": round(hv(g2))})

    # per-ward: recommended budget vs 2025, and the marginal value of the next lakh
    wards = d["wards"].set_index("ward_code")
    spent25 = d["work_orders"].groupby("ward_code").cost_inr.sum()
    ward_rows = []
    by_w = chosen.assign(ward_code=chosen.item_id.map(items.set_index("item_id").ward_code))
    for w in wards.index:
        wi, wo_ = b_items[b_items.ward_code == w], b_opts[b_opts.item_id.isin(b_items[b_items.ward_code == w].item_id)]
        alloc = float(by_w[by_w.ward_code == w].cost.sum())
        nxt = 0.0
        if len(wo_):
            more = solve(wi, wo_, alloc + 100_000)
            nxt = hv(more) - hv(by_w[by_w.ward_code == w])
        ward_rows.append({
            "ward_code": w, "ward_name": wards.loc[w, "ward_name"],
            "budget_2025_inr": int(wards.loc[w, "monsoon_repair_budget_inr_2025"]),
            "spend_2025_inr": int(spent25.get(w, 0)),
            "remaining_2025_inr": int(remaining_w.get(w, 0)),
            "recommended_budget_inr": int(round(alloc, -3)),
            "equity_floor_inr": int(floors.get(w, 0)),
            "harm_avoided": round(hv(by_w[by_w.ward_code == w])),
            "harm_avoided_per_next_lakh": round(nxt, 1),
            "dlp_items_owed_by_contractor": int((a_items.ward_code == w).sum()),
            "dlp_value_owed_inr": int(opts[opts.item_id.isin(a_items[a_items.ward_code == w].item_id)]
                                      .groupby("item_id").cost.min().sum()),
        })

    # item-level rows (the next_rupee.json contract)
    pick = chosen.set_index("item_id")
    cheapest = opts.loc[opts.groupby("item_id").unit_cost.idxmin()].set_index("item_id")
    best_durable = opts.loc[opts.groupby("item_id").method_reopen.idxmin()].set_index("item_id")
    names = d["roads"].set_index("road_id").road_name
    dom = items.sort_values("jobs", ascending=False).drop_duplicates("road_id").set_index("road_id").work_type
    rows = []
    for _, r in items.iterrows():
        a = bool(r.dlp_owed)
        f = r.item_id in pick.index
        sel = pick.loc[r.item_id] if f else (best_durable.loc[r.item_id] if a and r.item_id in best_durable.index else None)
        rr = r.copy()
        rr["road_name"], rr["dom"] = names.get(r.road_id), dom.get(r.road_id)
        rr["bucket"] = "A_OWED_BY_CONTRACTOR_DLP" if a else "B_NEXT_RUPEE"
        rr["funded"] = f
        for k in ["method", "method_reopen", "cost", "benefit"]:
            rr[k] = sel[k] if sel is not None else None
        alt = cheapest.loc[r.item_id] if r.item_id in cheapest.index else None
        rows.append({
            "item_id": r.item_id, "road_id": r.road_id, "road_name": rr.road_name, "ward_code": r.ward_code,
            "issue": r.work_type, "under_dlp": r.under_dlp == "Y", "bucket": rr.bucket, "funded": bool(f),
            "recommended_method": rr.method, "method_reopen_rate": None if rr.method_reopen is None else round(float(rr.method_reopen), 3),
            "estimated_repair_cost_inr": None if rr.cost is None else int(round(rr.cost, -2)),
            "cost_to_bmc_inr": 0 if a else (None if rr.cost is None else int(round(rr.cost, -2))),
            "harm_avoided": None if rr.benefit is None else round(float(rr.benefit), 1),
            "harm_per_lakh": None if rr.benefit is None or not rr.cost else round(float(rr.benefit / rr.cost * 1e5), 1),
            "priority_score": None,
            "reason_codes": r.reason_codes,
            "inputs": {"repairs_this_season": int(r.jobs), "open_complaints_attached": int(r.n - r.jobs),
                       "severity": round(float(r.severity), 2), "impact": round(float(r.impact), 2),
                       "spent_2025_inr": int(r.spent_2025), "reopens_2025": int(r.reopens)},
            "evidence_wo_ids": r.wo_ids,
            "explanation": explain(rr, alt if f else None),
        })
    # priority score = harm avoided per rupee of the chosen/best option, 0-100 within the city
    hp = pd.Series([x["harm_per_lakh"] or 0 for x in rows])
    lg = np.log1p(hp)
    for x, v in zip(rows, 100 * lg / lg.max()):
        x["priority_score"] = round(float(v), 1)
    rows.sort(key=lambda x: (x["bucket"] != "A_OWED_BY_CONTRACTOR_DLP", not x["funded"], -x["priority_score"]))

    summary = {"budget_inr": int(budget), "rate_card_cost_to_fix_everything_inr": int(full_need),
               "harm_units": "harm points = repairs needed x severity (from SLA class) x impact (flood, hospital, school, traffic, bus, accidents, open complaints, under-reported ward) x share of fixes that hold",
               # Future surface fixes owed by DLP contractors (rate card). Not the same as the audit engine's
               # recoverable_dlp_inr, which is money BMC already paid for DLP-covered repairs.
               "budget_curve": curve,
               "equity_floor_share": EQUITY_FLOOR, "comparison_same_budget": comparison,
               "method_failure_rates": meth.round(3).to_dict(orient="records"),
               "dlp_items": int(dlp.sum()),
               "dlp_value_owed_inr": int(opts[opts.item_id.isin(a_items.item_id)].groupby("item_id").cost.min().sum())}
    if out_dir:
        p = pathlib.Path(out_dir); p.mkdir(parents=True, exist_ok=True)
        (p / "next_rupee.json").write_text(json.dumps(rows, indent=1, default=str))
        (p / "ward_allocation.json").write_text(json.dumps(ward_rows, indent=1))
        (p / "allocation_summary.json").write_text(json.dumps(summary, indent=1))
    return rows, ward_rows, summary, (items, opts)


def allocate_ward(items, opts, ward_code, budget_inr):
    """Slider endpoint: exact re-solve for one ward at any budget (<1 s)."""
    wi = items[(items.ward_code == ward_code) & ~items.dlp_owed]
    wo_ = opts[opts.item_id.isin(wi.item_id)]
    ch = solve(wi, wo_, budget_inr)
    return {"ward_code": ward_code, "budget_inr": budget_inr, "spend_inr": int(ch.cost.sum()),
            "harm_avoided": round(float(ch.benefit.sum()), 1),
            "funded": ch[["item_id", "method", "cost", "benefit"]].round(1).to_dict(orient="records")}
