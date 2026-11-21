"""Audit engine: flags + ward audit (View 1) and road receipts (View 2), from data/*.csv.

Stdlib only. Run: python3 pipeline/build.py
Writes exports/:
  summary.json, roads_audit.json        (frontend contract)
  flags.csv, ward_audit.csv             (Supabase load: supabase/load_audit.sql)
View 3 (scorecard + next-rupee) lives in view3/ and reads ward_audit for UNDER_REPORTED_WARD.
Every number is computed here; nothing downstream does arithmetic.
"""
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "exports"

# Road-surface repairs covered by the original contractor's DLP.
# Drainage/pumping/utility work is not a surface defect, so it is never "paid twice".
DLP_SURFACE_METHODS = {"Cold mix patch", "Hot mix patch", "Mastic asphalt", "Paver blocks relaid"}
# Hot-laid asphalt should not be laid in heavy rain. Cold mix is designed for wet weather, so excluded.
HOT_ASPHALT_METHODS = {"Hot mix patch", "Mastic asphalt"}
HEAVY_RAIN_MM = 64.5  # IMD "Heavy" threshold
RATE_NORMAL_BAND = 1.30  # dictionary: normal jobs vary ~20-30% around the rate
RATE_FLAG_RATIO = 1.50  # flag only well outside the band (clean break in the data)
REPEAT_BILL_DAYS = 7  # same road + issue billed again this soon, with no complaint behind it


def read(name):
    with open(DATA / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def pct_rank(values):
    """Map each key to its percentile rank (0..1) among the values."""
    ordered = sorted(values.values())
    n = len(ordered) - 1 or 1
    return {k: ordered.index(v) / n for k, v in values.items()}


def detect_flags(work_orders, roads, rate_card, rain_by_date):
    flags = []

    def add(tier, detector, wo, rupees, rule, evidence):
        flags.append({
            "flag_id": f"{detector}:{wo['work_order_id']}",  # stable across reruns
            "tier": tier,
            "detector": detector,
            "status_label": "Recoverable under DLP" if detector == "DLP_PAID_TWICE" else "Needs Explanation",
            "ward_code": wo["ward_code"],
            "road_id": wo["road_id"],
            "work_order_id": wo["work_order_id"],
            "contractor_id": wo["contractor_id"],
            "rupees_at_stake": round(rupees),
            "evidence_row_ids": evidence,
            "rule_text": rule,
            "right_of_reply": "",
        })

    for wo in work_orders:
        road = roads[wo["road_id"]]
        cost = float(wo["cost_inr"])
        wo_id = wo["work_order_id"]

        # Tier 1: paid surface repair on a road still under DLP.
        if road["under_dlp"] == "Y" and wo["repair_method"] in DLP_SURFACE_METHODS:
            add(1, "DLP_PAID_TWICE", wo, cost,
                f"{wo['repair_method']} billed at ₹{cost:,.0f} on {road['road_id']}, which is under the original "
                f"contractor's Defect Liability Period (last resurfaced {road['last_resurfaced']}).",
                [wo_id, road["road_id"]])

        # Tier 2: billed well above rate card.
        rate = rate_card[wo["repair_method"]]
        qty = float(wo["area_sqm"]) if rate["unit"] == "per sqm" else 1.0
        expected = float(rate["standard_rate_inr"]) * qty
        if cost > expected * RATE_FLAG_RATIO:
            add(2, "RATE_INFLATION", wo, cost - expected * RATE_NORMAL_BAND,
                f"Billed ₹{cost:,.0f} vs rate-card ₹{expected:,.0f} ({cost / expected:.2f}x). "
                f"At stake = amount above the normal +30% band.",
                [wo_id, f"RATE:{wo['repair_method']}"])

        # Tier 2: hot asphalt completed on a heavy-rain day.
        day = wo["completed_at"][:10]
        mm = rain_by_date.get(day, 0.0)
        if wo["repair_method"] in HOT_ASPHALT_METHODS and mm >= HEAVY_RAIN_MM:
            add(2, "RAIN_DAY_WORK", wo, cost,
                f"{wo['repair_method']} completed on {day} with {mm} mm rain (IMD heavy >= {HEAVY_RAIN_MM} mm).",
                [wo_id, f"RAIN:{day}"])

    # Tier 1: repeat bill with no complaint behind it. Every genuine job in this data has at least one linked
    # complaint; a bill with none, for the same road + issue fixed days earlier, is a likely duplicate.
    ts = lambda v: datetime.strptime(v[:16], "%Y-%m-%d %H:%M")
    by_issue = defaultdict(list)
    for wo in work_orders:
        by_issue[(wo["road_id"], wo["work_type"])].append(wo)
    for jobs in by_issue.values():
        jobs.sort(key=lambda w: w["completed_at"])
        for a, b in zip(jobs, jobs[1:]):
            gap = (ts(b["completed_at"]) - ts(a["completed_at"])).total_seconds() / 86400
            if not b["linked_complaint_ids"].strip() and gap <= REPEAT_BILL_DAYS:
                add(1, "REPEAT_BILL_NO_COMPLAINT", b, float(b["cost_inr"]),
                    f"{b['work_order_id']} bills {b['work_type'].lower()} on {b['road_id']} {gap:.1f} days after "
                    f"{a['work_order_id']} fixed the same issue, and no citizen complaint is linked to it.",
                    [b["work_order_id"], a["work_order_id"], b["road_id"]])

    # Tier 1: same road + same method with overlapping work windows.
    by_key = defaultdict(list)
    for wo in work_orders:
        by_key[(wo["road_id"], wo["repair_method"])].append(wo)
    for jobs in by_key.values():
        jobs.sort(key=lambda w: w["work_started_at"])
        for a, b in zip(jobs, jobs[1:]):
            if b["work_started_at"] < a["completed_at"]:
                add(1, "OVERLAPPING_WORK_ORDER", b, float(b["cost_inr"]),
                    f"{b['work_order_id']} started {b['work_started_at']} while {a['work_order_id']} "
                    f"(same road, same method) was still open until {a['completed_at']}.",
                    [b["work_order_id"], a["work_order_id"], b["road_id"]])
    return flags


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
