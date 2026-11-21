"""Flag detectors: deterministic audit rules that turn work orders into flags.

Each flag: tier, detector, status_label ("Needs Explanation" / "Recoverable under DLP"), rupees_at_stake and
evidence_row_ids, so every number can be traced to source rows. Used by run_audit.py.
"""
from collections import defaultdict
from datetime import datetime

# Road-surface repairs covered by the original contractor's DLP.
# Drainage/pumping/utility work is not a surface defect, so it is never "paid twice".
DLP_SURFACE_METHODS = {"Cold mix patch", "Hot mix patch", "Mastic asphalt", "Paver blocks relaid"}
# Hot-laid asphalt should not be laid in heavy rain. Cold mix is designed for wet weather, so excluded.
HOT_ASPHALT_METHODS = {"Hot mix patch", "Mastic asphalt"}
HEAVY_RAIN_MM = 64.5  # IMD "Heavy" threshold
RATE_NORMAL_BAND = 1.30  # dictionary: normal jobs vary ~20-30% around the rate
RATE_FLAG_RATIO = 1.50  # flag only well outside the band (clean break in the data)
REPEAT_BILL_DAYS = 7  # same road + issue billed again this soon, with no complaint behind it


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
