"""Audit engine: compute every number the four views need, from data/*.csv.

Stdlib only. Run: python3 pipeline/build.py
Writes exports/:
  summary.json, roads_audit.json, contractors.json, next_rupee.json   (frontend contract)
  flags.csv, ward_audit.csv, contractor_scorecard.csv, road_priority.csv  (Supabase load)
Every number is computed here; nothing downstream does arithmetic.
"""
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
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

FLOOD_PRONE_LOW_LYING = 0.6  # ward low_lying_index at/above this counts as flood-prone
HOTSPOT_NEAR_M = 300  # road within this distance of a flood hotspot gets FLOOD_SPOT
ROAD_CONDITION_CAUSES = {"Pothole", "Uneven road / open chamber", "Waterlogged road"}
SEVERITY_WEIGHT = {"Minor": 1, "Grievous": 3, "Fatal": 5}
# Next-rupee priority weights (sum to 1). Under-reported wards get a flat bonus on top.
PRIORITY_WEIGHTS = {"flood": 0.25, "accidents": 0.25, "ambulance": 0.20, "traffic": 0.15, "repeat": 0.15}
UNDER_REPORTED_BONUS = 5
SMALL_SAMPLE_JOBS = 30


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


def wilson(k, n, z=1.96):
    """95% Wilson interval for k successes out of n."""
    if n == 0:
        return 0.0, 1.0
    p = k / n
    mid = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, mid - half), min(1.0, mid + half)


def contractor_scorecard(work_orders, wards, roads, contractors, rain_by_date, flags):
    """Context-adjusted reopen performance via indirect standardization.

    Each job's expected reopen chance = city reopen rate for jobs of the same
    (work_type, flood-prone ward, heavy-rain completion day). A contractor's
    observed/expected ratio scales the city rate; score = % fixes expected to survive 30 days.
    """
    low_lying = {w["ward_code"]: float(w["low_lying_index"]) for w in wards}
    traffic = {t["road_id"]: int(t["peak_hour_vehicles"]) for t in read("traffic.csv")}

    def stratum(wo):
        return (wo["work_type"], low_lying[wo["ward_code"]] >= FLOOD_PRONE_LOW_LYING,
                rain_by_date.get(wo["completed_at"][:10], 0.0) >= HEAVY_RAIN_MM)

    jobs_in, reopens_in = Counter(), Counter()
    for wo in work_orders:
        jobs_in[stratum(wo)] += 1
        reopens_in[stratum(wo)] += wo["reopened_within_30d"] == "Y"
    city_rate = sum(reopens_in.values()) / len(work_orders)

    by_c = defaultdict(list)
    for wo in work_orders:
        by_c[wo["contractor_id"]].append(wo)
    rows = []
    for cid, jobs in sorted(by_c.items()):
        n = len(jobs)
        observed = sum(w["reopened_within_30d"] == "Y" for w in jobs)
        expected = sum(reopens_in[stratum(w)] / jobs_in[stratum(w)] for w in jobs)
        scale = city_rate / (expected / n) if expected else 1.0  # raw rate -> context-adjusted rate
        lo, hi = wilson(observed, n)
        adj = min(1.0, observed / n * scale)
        cflags = [f for f in flags if f["contractor_id"] == cid]
        rows.append({
            "contractor_id": cid,
            "contractor_name": contractors[cid],
            "jobs_count": n,
            "total_billed_inr": round(sum(float(w["cost_inr"]) for w in jobs)),
            "reopen_rate_30d": round(observed / n, 4),
            "expected_reopen_rate_30d": round(expected / n, 4),
            "reopen_observed_to_expected": round(observed / expected, 3) if expected else None,
            "sla_met_rate": round(sum(w["sla_met"] == "Y" for w in jobs) / n, 4),
            "risk_adjusted_score": round(100 * (1 - adj), 1),
            "score_low": round(100 * (1 - min(1.0, hi * scale)), 1),
            "score_high": round(100 * (1 - min(1.0, lo * scale)), 1),
            "small_sample": n < SMALL_SAMPLE_JOBS,
            "tier1_flags_count": sum(f["tier"] == 1 for f in cflags),
            "flags_count": len(cflags),
            "recoverable_inr": sum(f["rupees_at_stake"] for f in cflags if f["detector"] == "DLP_PAID_TWICE"),
            "avg_rain_mm_on_completion_day": round(
                statistics.mean(rain_by_date.get(w["completed_at"][:10], 0.0) for w in jobs), 1),
            "flood_prone_share": round(
                sum(low_lying[w["ward_code"]] >= FLOOD_PRONE_LOW_LYING for w in jobs) / n, 3),
            "avg_peak_vehicles": round(statistics.mean(traffic.get(w["road_id"], 0) for w in jobs)),
        })
    return rows


def metres_to_segment(lat, lon, road):
    """Approx distance (m) from a point to a road segment; equirectangular is fine at city scale."""
    k = math.cos(math.radians(19.05)) * 111320
    px, py = lon * k, lat * 110540
    ax, ay = float(road["start_lon"]) * k, float(road["start_lat"]) * 110540
    bx, by = float(road["end_lon"]) * k, float(road["end_lat"]) * 110540
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy or 1)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def road_priority(roads, work_orders, ward_rows):
    """Next-rupee ranking. Bucket A: under DLP (₹0 to BMC). Bucket B: ranked by priority per lakh."""
    hotspots = read("flood_hotspots.csv")
    traffic = {t["road_id"]: int(t["peak_hour_vehicles"]) for t in read("traffic.csv")}
    under_reported = {w["ward_code"] for w in ward_rows if w["under_reported_flag"]}

    ambulance = Counter()
    for f in read("facilities.csv"):
        ambulance[f["ambulance_entry_road"]] += 3 if f["emergency_services"] == "Y" else 1
    accident_harm, accident_ids = Counter(), defaultdict(list)
    for a in read("accidents.csv"):
        if a["probable_cause"] in ROAD_CONDITION_CAUSES:
            accident_harm[a["road_id"]] += SEVERITY_WEIGHT[a["severity"]]
            accident_ids[a["road_id"]].append(a["accident_id"])
    reopened, surface_spend = Counter(), Counter()
    for wo in work_orders:
        reopened[wo["road_id"]] += wo["reopened_within_30d"] == "Y"
        if wo["repair_method"] in DLP_SURFACE_METHODS:
            surface_spend[wo["road_id"]] += float(wo["cost_inr"])

    ids = list(roads)
    nearest = {}
    for rid in ids:
        d, hid = min((metres_to_segment(float(h["lat"]), float(h["lon"]), roads[rid]), h["hotspot_id"]) for h in hotspots)
        nearest[rid] = (round(d), hid)
    parts = {
        "flood": {r: 1.0 if nearest[r][0] <= HOTSPOT_NEAR_M else 0.0 for r in ids},
        "accidents": pct_rank({r: accident_harm[r] for r in ids}),
        "ambulance": pct_rank({r: ambulance[r] for r in ids}),
        "traffic": pct_rank({r: traffic.get(r, 0) for r in ids}),
        "repeat": pct_rank({r: reopened[r] for r in ids}),
    }
    # ponytail: repair cost proxy = this season's surface-repair spend on the road (else ward median), floored.
    # Swap for an engineering estimate (length x lanes x rate) if the team gets one.
    ward_spends = defaultdict(list)
    for rid, s in surface_spend.items():
        ward_spends[roads[rid]["ward_code"]].append(s)
    city_median = statistics.median(surface_spend.values())

    rows = []
    for rid in ids:
        road = roads[rid]
        score = 100 * sum(PRIORITY_WEIGHTS[k] * parts[k][rid] for k in PRIORITY_WEIGHTS)
        if road["ward_code"] in under_reported:
            score += UNDER_REPORTED_BONUS
        score = min(100.0, score)
        ward_median = statistics.median(ward_spends[road["ward_code"]]) if ward_spends[road["ward_code"]] else city_median
        # Floor at city median so one tiny patch doesn't make a road look absurdly cheap per point of harm.
        cost = max(surface_spend[rid] or ward_median, city_median)
        dlp = road["under_dlp"] == "Y"
        reasons = [code for code, hit in [
            ("FLOOD_SPOT", parts["flood"][rid] == 1.0),
            ("AMBULANCE_ROUTE", ambulance[rid] > 0),
            ("HIGH_TRAFFIC", parts["traffic"][rid] >= 0.75),
            ("ACCIDENT_PRONE", accident_harm[rid] > 0 and parts["accidents"][rid] >= 0.75),
            ("REPEAT_FAILURE", reopened[rid] >= 2),
            ("UNDER_REPORTED_WARD", road["ward_code"] in under_reported),
        ] if hit]
        rows.append({
            "road_id": rid,
            "road_name": road["road_name"],
            "ward_code": road["ward_code"],
            "under_dlp": dlp,
            "priority_score": round(score, 1),
            "estimated_repair_cost_inr": round(cost),
            "cost_to_bmc_inr": 0 if dlp else round(cost),
            "priority_per_lakh": None if dlp else round(score / (cost / 1e5), 3),
            "bucket": "A_DLP_OWED" if dlp else "B_INVEST",
            "reason_codes": reasons,
            "nearest_hotspot_id": nearest[rid][1],
            "nearest_hotspot_m": nearest[rid][0],
            "ambulance_weight": ambulance[rid],
            "road_condition_accident_harm": accident_harm[rid],
            "reopened_jobs": reopened[rid],
            "peak_hour_vehicles": traffic.get(rid),
            "evidence_row_ids": [rid, *accident_ids[rid]],
        })
    # A: highest harm first (contractor owes it). B: most priority per rupee first.
    rows.sort(key=lambda r: (r["bucket"], -(r["priority_score"] if r["under_dlp"] else r["priority_per_lakh"]), r["road_id"]))
    rank = Counter()
    for r in rows:
        rank[r["bucket"]] += 1
        r["bucket_rank"] = rank[r["bucket"]]
    return rows


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
                "dlp_surface_methods": sorted(DLP_SURFACE_METHODS),
            },
        },
    }
    check(summary, wo_by_id, roads)
    scorecard = contractor_scorecard(work_orders, wards, roads, contractors, rain_by_date, flags)
    priority = road_priority(roads, work_orders, ward_rows)

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
    for name, obj in [("summary.json", summary), ("roads_audit.json", roads_audit),
                      ("contractors.json", scorecard), ("next_rupee.json", priority)]:
        (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv("flags.csv", flags, ["flag_id", "tier", "detector", "status_label", "ward_code", "road_id",
                                   "work_order_id", "contractor_id", "rupees_at_stake", "evidence_row_ids", "rule_text"])
    write_csv("ward_audit.csv", ward_rows, [k for k in ward_rows[0] if k != "ward_name"])
    write_csv("contractor_scorecard.csv", scorecard, [k for k in scorecard[0] if k != "contractor_name"])
    write_csv("road_priority.csv", priority, [k for k in priority[0] if k not in ("road_name", "ward_code", "under_dlp")])
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
