"""View 4: Citizen Accessibility Layer. Free-text road lookup and citizen reports with the accountability tracker."""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from backend import schemas as s
from backend.database import get_engine, one, rows

router = APIRouter(tags=["View 4: Citizen Layer"])
TRACKER = ["reported", "matched_to_contract", "payment_held", "contractor_notified"]


def tracker(status):
    return [{"step": step, "done": TRACKER.index(step) <= TRACKER.index(status)} for step in TRACKER]


@router.get("/api/lookup", response_model=s.Lookup, responses=s.NOT_FOUND, summary="Free-text landmark/road lookup -> road receipt")
def lookup(q: str = Query(min_length=2, max_length=200, description="Free text: road name, locality, alias or Devanagari",
                          examples=["Andheri subway ke bahar wapas khadda ho gaya, paisa kahan gaya?"])):
    """View 4 deterministic lookup: free text -> road receipt.
    Tries a road name in the text first ("Andheri subway ke bahar..."), then any locality name/alias/Devanagari.
    Fuzzy/vernacular parsing beyond this is the Claude /api/citizen-query layer's job."""
    match = rows("SELECT r.road_id, r.road_name AS matched_text, r.ward_code, NULL::text AS locality, 0 AS approx_m "
                 "FROM roads r WHERE position(lower(r.road_name) in lower(%(q)s)) > 0 "
                 "ORDER BY length(r.road_name) DESC, r.segment_no LIMIT 1", q=q)
    via = "road_name"
    if not match:
        match = rows("SELECT n.road_id, a.alias AS matched_text, n.ward_code, n.locality, n.approx_m "
                     "FROM locality_aliases a JOIN locality_nearest_road n USING (locality) "
                     "WHERE position(a.alias in lower(%(q)s)) > 0 ORDER BY length(a.alias) DESC LIMIT 1", q=q)
        via = "locality"
    if not match:
        raise HTTPException(404, "no road or locality matched; try a road name or area name")
    match = match[0]
    receipt = one("SELECT * FROM road_audit WHERE road_id = %(r)s", "road", r=match["road_id"])
    return {"matched_via": via, "matched_text": match["matched_text"], "matched_locality": match["locality"],
            "ward_code": match["ward_code"], "matched_road_id": match["road_id"], "road_distance_m": match["approx_m"],
            "warranty_status": "UNDER_DLP" if receipt["under_dlp"] else "OUT_OF_DLP", "road": receipt}


@router.post("/api/citizen-reports", status_code=201, response_model=s.CitizenReport, responses=s.NOT_FOUND, summary="Submit citizen report (server sets tracker status)")
def add_citizen_report(req: s.CitizenReportReq):
    """View 4 report. Tracker status is set deterministically here (anon clients cannot set it)."""
    status, flag_id = "reported", None
    if req.road_id:
        road = one("SELECT road_id, under_dlp FROM roads WHERE road_id = %(r)s", f"road {req.road_id}", r=req.road_id)
        status = "matched_to_contract"
        if road["under_dlp"] and req.kind == "still_broken":
            status = "payment_held"  # DLP road: the original contractor owes the fix, BMC holds payment
            f = rows("SELECT flag_id FROM flags WHERE road_id = %(r)s AND detector = 'DLP_PAID_TWICE' "
                     "ORDER BY rupees_at_stake DESC LIMIT 1", r=req.road_id)
            flag_id = f[0]["flag_id"] if f else None
    with get_engine().begin() as c:
        r = c.execute(text(
            "INSERT INTO citizen_reports (kind, input_mode, text, language, photo_url, matched_locality, road_id, "
            "work_order_id, flag_id, status) VALUES (:kind, :input_mode, :text, :language, :photo_url, "
            ":matched_locality, :road_id, :work_order_id, :flag_id, :status) RETURNING *"),
            {**req.model_dump(), "flag_id": flag_id, "status": status}).mappings().one()
    return {**dict(r), "tracker": tracker(status)}


@router.get("/api/citizen-reports/{report_id}", response_model=s.CitizenReport, responses=s.NOT_FOUND, summary="Citizen report status + tracker")
def citizen_report(report_id: int):
    r = one("SELECT * FROM citizen_reports WHERE id = %(i)s", f"report {report_id}", i=report_id)
    return {**r, "tracker": tracker(r["status"])}
