"""View 1: City & Ward Overview. KPI strip, ward list/map, flagged bills queue."""
import json
import pathlib
from functools import lru_cache
from typing import Optional, Union

from fastapi import APIRouter, Header, Query

from backend import schemas as s
from backend.database import norm_ward, one, rows
from backend.routes.road_story import inr  # shared ₹ formatter

router = APIRouter(tags=["View 1: City & Ward Overview"])
WARDS_GEOJSON = pathlib.Path(__file__).resolve().parents[2] / "data" / "wards.geojson"


@router.get("/api/city", response_model=s.CityKPIs, summary="City KPI strip")
def city():
    """View 1 KPI strip."""
    return one("SELECT * FROM city_kpis", "city")


@router.get("/api/wards", response_model=Union[s.Ward, list[s.Ward]], responses=s.NOT_FOUND, summary="All wards, or one ward via ?ward= / X-Ward-Code")
def ward_list(ward: Optional[str] = Query(None, description="Ward code, e.g. K/W. Returns that ward only."),
              x_ward_code: Optional[str] = Header(None, description="Same as ?ward=; the query param wins if both are sent.")):
    """View 1 ward map: all wards as a list, or one ward as an object when a ward code is given
    (query param or X-Ward-Code header; K/W, K-W and k_w all work). Colour the map by dlp_leakage_rate; join to wards.geojson on ward_code."""
    code = norm_ward(ward or x_ward_code or "")
    if code:
        return one("SELECT * FROM ward_overview WHERE ward_code = %(w)s", f"ward {code}", w=code)
    return rows("SELECT * FROM ward_overview ORDER BY ward_code")


@lru_cache(maxsize=1)
def _ward_polygons():
    gj = json.loads(WARDS_GEOJSON.read_text(encoding="utf-8"))
    return {f["properties"]["ward_code"]: f["geometry"] for f in gj["features"]}


@router.get("/api/wards/map", response_model=s.WardMap, summary="Ward map as GeoJSON (polygons + ward metrics)")
def ward_map():
    """View 1 map: polygons from data/wards.geojson, every ward_overview column in properties.
    Colour by dlp_leakage_rate."""
    polys = _ward_polygons()
    return {"type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": w, "geometry": polys.get(w["ward_code"])}
                         for w in rows("SELECT * FROM ward_overview ORDER BY ward_code")]}


@router.get("/api/flagged-queue", response_model=list[s.FlaggedBill], summary="Flagged bills ranked by rupees at stake")
def flagged_queue(ward: Optional[str] = Query(None, description="Ward code filter (K/W or K-W)", examples=["K/W"]),
                  tier: Optional[int] = Query(None, ge=1, le=3, description="Top tier filter: 1 contractual, 2 implausible, 3 lead"),
                  detector: Optional[s.Detector] = Query(None, description="Only bills with this detector"),
                  limit: int = Query(50, ge=1, le=500),
                  offset: int = Query(0, ge=0, description="Paging: skip this many rows")):
    """View 1 flagged bills, ranked by rupees at stake. ?ward=K/W&tier=1&detector=REPEAT_BILL_NO_COMPLAINT&limit=20&offset=0"""
    return rows("SELECT * FROM flagged_queue WHERE (%(w)s IS NULL OR ward_code = %(w)s) "
                "AND (%(t)s IS NULL OR top_tier = %(t)s) AND (%(d)s IS NULL OR %(d)s = ANY(detectors)) "
                "ORDER BY rupees_at_stake DESC, work_order_id LIMIT %(n)s OFFSET %(o)s",
                w=norm_ward(ward), t=tier, d=detector, n=max(1, min(limit, 500)), o=offset)


@router.get("/api/wards/{ward_code:path}/money-trail", response_model=s.MoneyTrail, responses=s.NOT_FOUND,
            summary="Ward money trail: budget vs spend, by contractor and repair method, failed repairs")
def money_trail(ward_code: str):
    """Where a ward's monsoon repair money went: budget vs billed spend, spend and 30-day failures by contractor
    (canonical names) and by repair method, and the spend on jobs that failed within 30 days. Every job counts once
    (work_orders grain; no joins that multiply rows). `summary` is one sentence built from these numbers."""
    w = norm_ward(ward_code)
    ward = one("SELECT ward_code, monsoon_repair_budget_inr_2025 AS budget_inr FROM wards WHERE ward_code = %(w)s",
               f"ward {ward_code}", w=w)
    by_c = rows("SELECT wo.contractor_id, c.contractor_name, count(*) AS jobs, COALESCE(sum(wo.cost_inr), 0)::bigint AS spend_inr, "
                "count(*) FILTER (WHERE wo.reopened_within_30d) AS failed_30d, "
                "COALESCE(sum(wo.cost_inr) FILTER (WHERE wo.reopened_within_30d), 0)::bigint AS failed_spend_inr "
                "FROM work_orders wo JOIN contractors c ON c.contractor_id = wo.contractor_id WHERE wo.ward_code = %(w)s "
                "GROUP BY wo.contractor_id, c.contractor_name ORDER BY spend_inr DESC, wo.contractor_id", w=w)
    by_m = rows("SELECT repair_method, count(*) AS jobs, COALESCE(sum(cost_inr), 0)::bigint AS spend_inr, "
                "count(*) FILTER (WHERE reopened_within_30d) AS failed_30d FROM work_orders WHERE ward_code = %(w)s "
                "GROUP BY repair_method ORDER BY spend_inr DESC, repair_method", w=w)
    spend = sum(c["spend_inr"] for c in by_c)
    failed = {"jobs": sum(c["failed_30d"] for c in by_c), "spend_inr": sum(c["failed_spend_inr"] for c in by_c)}
    jobs = sum(c["jobs"] for c in by_c)
    summary = (f"Ward {w} billed {inr(spend)} against a {inr(ward['budget_inr'])} monsoon budget across {jobs} jobs; "
               f"{failed['jobs']} of them failed within 30 days ({inr(failed['spend_inr'])} billed on those).")
    return {"ward_code": w, "budget_inr": ward["budget_inr"], "spend_inr": spend, "by_contractor": by_c,
            "by_repair_method": by_m, "failed_within_30d": failed, "summary": summary}
