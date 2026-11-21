"""Audit engine: run the flag detectors over data/*.csv and build the ward audit (View 1) and road receipts (View 2).

Stdlib only. Run from the repo root: python3 -m audit_engine.run_audit
Writes audit_engine/output/:
  summary.json, roads_audit.json        (frontend contract)
  flags.csv, ward_audit.csv             (Supabase load: supabase/load_audit_outputs.sql)
Detectors live in detectors.py. scorecard_planner/ (View 3) reads ward_audit for UNDER_REPORTED_WARD.
Every number is computed here; nothing downstream does arithmetic.
"""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from audit_engine.detectors import (DLP_SURFACE_METHODS, HEAVY_RAIN_MM, RATE_FLAG_RATIO, RATE_NORMAL_BAND,
                                    REPEAT_BILL_DAYS, detect_flags)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "audit_engine" / "output"



def read(name):
    with open(DATA / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def pct_rank(values):
    """Map each key to its percentile rank (0..1) among the values."""
    ordered = sorted(values.values())
    n = len(ordered) - 1 or 1
    return {k: ordered.index(v) / n for k, v in values.items()}


def ward_for_unassigned(complaints, localities):
    """Resolve blank complaint wards via locality name/aliases (case-insensitive)."""
    lookup = {}
    for loc in localities:
        for name in [loc["locality"], *loc["aliases"].split(";")]:
            if name.strip():
                lookup[name.strip().lower()] = loc["ward_code"]
    resolved = unresolved = 0
    for c in complaints:
        if not c["ward_code"]:
            ward = lookup.get(c["locality_text"].strip().lower())
            if ward:
                c["ward_code"] = ward
                resolved += 1
            else:
                unresolved += 1
    return resolved, unresolved


def write_csv(name, rows, cols):
    """CSV for psql \\copy: lists -> Postgres array literal, None -> NULL, bool -> true/false."""
    def cell(v):
        if isinstance(v, list):
            return "{" + ",".join('"' + str(e).replace('"', '\\"') + '"' for e in v) + "}"
        if isinstance(v, bool):
            return "true" if v else "false"
        return "" if v is None else v
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows([cell(r[c]) for c in cols] for r in rows)


def build():
    wards = read("wards.csv")
    roads = {r["road_id"]: r for r in read("roads.csv")}
    rate_card = {r["repair_method"]: r for r in read("rate_card.csv")}
    work_orders = read("work_orders.csv")
    complaints = read("complaints.csv")
    hotspots = Counter(h["ward_code"] for h in read("flood_hotspots.csv"))
    accidents = Counter(a["ward_code"] for a in read("accidents.csv"))
    contractors = {c["contractor_id"]: c["contractor_name"] for c in read("contractors.csv")}

    # Daily grain: worst station reading per date (prevents fan-out).
    rain_by_date = defaultdict(float)
    for r in read("rainfall_daily.csv"):
        rain_by_date[r["date"]] = max(rain_by_date[r["date"]], float(r["rainfall_mm"]))

    flags = detect_flags(work_orders, roads, rate_card, rain_by_date)
    resolved, unresolved = ward_for_unassigned(complaints, read("localities.csv"))

    # One queue row per work order; flags on the same bill never double-count rupees.
    wo_by_id = {w["work_order_id"]: w for w in work_orders}
    flags_by_wo = defaultdict(list)
    for f in flags:
        flags_by_wo[f["work_order_id"]].append(f)
    queue = []
    for wo_id, fs in flags_by_wo.items():
        wo = wo_by_id[wo_id]
        queue.append({
            "work_order_id": wo_id,
            "road_id": wo["road_id"],
            "road_name": roads[wo["road_id"]]["road_name"],
            "ward_code": wo["ward_code"],
            "contractor_id": wo["contractor_id"],
            "contractor_name": contractors[wo["contractor_id"]],
            "repair_method": wo["repair_method"],
            "cost_inr": round(float(wo["cost_inr"])),
            "completed_at": wo["completed_at"],
            "top_tier": min(f["tier"] for f in fs),
            "rupees_at_stake": max(f["rupees_at_stake"] for f in fs),
            "status_label": "Recoverable under DLP" if any(f["detector"] == "DLP_PAID_TWICE" for f in fs)
            else "Needs Explanation",
            "flags": fs,
        })
    queue.sort(key=lambda q: (-q["rupees_at_stake"], q["work_order_id"]))

    spend = defaultdict(float)
    for wo in work_orders:
        spend[wo["ward_code"]] += float(wo["cost_inr"])
    dlp_eligible = Counter(w["ward_code"] for w in work_orders
                           if roads[w["road_id"]]["under_dlp"] == "Y" and w["repair_method"] in DLP_SURFACE_METHODS)
    recoverable = defaultdict(int)
    flagged_count = Counter()
    for q in queue:
        flagged_count[q["ward_code"]] += 1
        recoverable[q["ward_code"]] += sum(f["rupees_at_stake"] for f in q["flags"] if f["detector"] == "DLP_PAID_TWICE")
    complaint_count = Counter(c["ward_code"] for c in complaints if c["ward_code"])

    # Under-reported = physical risk in top half, complaints per capita in bottom quartile.
    codes = [w["ward_code"] for w in wards]
    risk_parts = [
        pct_rank({w["ward_code"]: float(w["low_lying_index"]) for w in wards}),
        pct_rank({c: hotspots[c] for c in codes}),
        pct_rank({c: accidents[c] for c in codes}),
    ]
    risk = {c: sum(p[c] for p in risk_parts) / len(risk_parts) for c in codes}
    per_lakh = {w["ward_code"]: complaint_count[w["ward_code"]] / float(w["population_est"]) * 1e5 for w in wards}
    voice = pct_rank(per_lakh)

    ward_rows = []
    for w in wards:
        c = w["ward_code"]
        ward_rows.append({
            "ward_code": c,
            "ward_name": w["ward_name"],
            "budget_inr": round(float(w["monsoon_repair_budget_inr_2025"])),
            "spend_inr": round(spend[c]),
            "recoverable_dlp_inr": recoverable[c],
            "flagged_bills_count": flagged_count[c],
            # BMC paid every DLP-eligible job (no ₹0 work orders), so this is 0.0 wherever jobs exist.
            "warranty_enforcement_rate": 0.0 if dlp_eligible[c] else None,
            "dlp_eligible_jobs": dlp_eligible[c],
            # Use this to colour the map: share of ward spend that the DLP contractor owed.
            "dlp_leakage_rate": round(recoverable[c] / spend[c], 4) if spend[c] else 0.0,
            "physical_risk_score": round(risk[c], 3),
            "complaints_per_lakh": round(per_lakh[c], 1),
            "under_reported_flag": risk[c] >= 0.5 and voice[c] <= 0.25,
            "flood_hotspots_count": hotspots[c],
            "accidents_count": accidents[c],
        })

    summary = {
        "city_totals": {
            "total_budget_inr": sum(r["budget_inr"] for r in ward_rows),
            "total_spend_inr": round(sum(spend.values())),
            "recoverable_dlp_inr": sum(recoverable.values()),
            "flagged_bills_count": len(queue),
            "flags_by_detector": dict(Counter(f["detector"] for f in flags)),
        },
        "wards": ward_rows,
        "flagged_queue": queue,
        "meta": {
            "work_orders": len(work_orders),
            "complaints_ward_resolved_from_locality": resolved,
            "complaints_ward_unresolved": unresolved,
            "rules": {
                "heavy_rain_mm": HEAVY_RAIN_MM,
                "rate_flag_ratio": RATE_FLAG_RATIO,
                "rate_normal_band": RATE_NORMAL_BAND,
                "repeat_bill_days": REPEAT_BILL_DAYS,
                "dlp_surface_methods": sorted(DLP_SURFACE_METHODS),
            },
        },
    }
    check(summary, wo_by_id, roads)

    flags_by_road, wos_by_road = defaultdict(list), defaultdict(list)
    for f in flags:
        flags_by_road[f["road_id"]].append(f)
    for wo in sorted(work_orders, key=lambda w: w["assigned_at"]):
        wos_by_road[wo["road_id"]].append({
            "work_order_id": wo["work_order_id"],
            "contractor_id": wo["contractor_id"],
            "contractor_name": contractors[wo["contractor_id"]],
            "work_type": wo["work_type"],
            "repair_method": wo["repair_method"],
            "cost_inr": round(float(wo["cost_inr"])),
            "assigned_at": wo["assigned_at"],
            "completed_at": wo["completed_at"],
            "rain_mm_on_completion_day": rain_by_date.get(wo["completed_at"][:10], 0.0),
            "sla_met": wo["sla_met"] == "Y",
            "reopened_within_30d": wo["reopened_within_30d"] == "Y",
            "engineer_remark": wo["engineer_remark"],
            "linked_complaint_ids": [c for c in wo["linked_complaint_ids"].split("|") if c],
        })
    roads_audit = [{
        "road_id": rid,
        "road_name": r["road_name"],
        "ward_code": r["ward_code"],
        "road_type": r["road_type"],
        "surface": r["surface"],
        "under_dlp": r["under_dlp"] == "Y",
        "last_resurfaced": r["last_resurfaced"],
        "total_billed_inr": sum(w["cost_inr"] for w in wos_by_road[rid]),
        "rupees_at_stake": sum(max(f["rupees_at_stake"] for f in fs) for fs in
                               [[f for f in flags_by_road[rid] if f["work_order_id"] == wid]
                                for wid in {f["work_order_id"] for f in flags_by_road[rid]}]),
        "work_orders": wos_by_road[rid],
        "flags": flags_by_road[rid],
    } for rid, r in roads.items()]

    OUT.mkdir(exist_ok=True)
    for name, obj in [("summary.json", summary), ("roads_audit.json", roads_audit)]:
        (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv("flags.csv", flags, ["flag_id", "tier", "detector", "status_label", "ward_code", "road_id",
                                   "work_order_id", "contractor_id", "rupees_at_stake", "evidence_row_ids", "rule_text"])
    write_csv("ward_audit.csv", ward_rows, [k for k in ward_rows[0] if k != "ward_name"])
    return summary


def check(summary, wo_by_id, roads):
    t, wards, queue = summary["city_totals"], summary["wards"], summary["flagged_queue"]
    assert abs(t["total_spend_inr"] - sum(w["spend_inr"] for w in wards)) <= len(wards)  # rounding only
    assert t["recoverable_dlp_inr"] == sum(w["recoverable_dlp_inr"] for w in wards)
    assert t["flagged_bills_count"] == sum(w["flagged_bills_count"] for w in wards) == len(queue)
    assert len({q["work_order_id"] for q in queue}) == len(queue)
    all_ids = [f["flag_id"] for q in queue for f in q["flags"]]
    assert len(set(all_ids)) == len(all_ids)
    for q in queue:
        for f in q["flags"]:
            assert f["rupees_at_stake"] > 0
            for eid in f["evidence_row_ids"]:
                assert eid in wo_by_id or eid in roads or eid.startswith(("RATE:", "RAIN:")), eid
            if f["detector"] == "DLP_PAID_TWICE":
                assert roads[q["road_id"]]["under_dlp"] == "Y"


if __name__ == "__main__":
    s = build()
    print(json.dumps(s["city_totals"], indent=2))
    print("under-reported:", [w["ward_code"] for w in s["wards"] if w["under_reported_flag"]])
    print("top 3:", [(q["work_order_id"], q["rupees_at_stake"], q["status_label"]) for q in s["flagged_queue"][:3]])
