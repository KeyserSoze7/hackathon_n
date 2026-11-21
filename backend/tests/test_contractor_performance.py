"""Monthly contractor scorecards: processor + API, against fixture data (no database)."""
from datetime import date, datetime, timezone

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from features.contractor_performance import router as cp_router
from features.contractor_performance.config import METHODOLOGIES, Methodology
from features.contractor_performance.processor import SourceData, process
from features.contractor_performance.repository import MemoryStore, PostgresRepository
from features.contractor_performance.service import ScorecardService

M = METHODOLOGIES["v1"]
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def job(i, contractor="CT01", completed="2025-07-10 12:00", method="Drain desilting", cost=90000, area=10,
        sla="Y", reopen="N", road="RD1", ward="A", assigned="2025-07-09 00:00", started=None):
    return {"work_order_id": f"WO{i:03d}", "ward_code": ward, "road_id": road, "work_type": "Waterlogging",
            "repair_method": method, "contractor_id": contractor, "assigned_at": assigned,
            "work_started_at": started or assigned, "completed_at": completed, "area_sqm": area, "cost_inr": cost,
            "sla_met": sla, "reopened_within_30d": reopen}


def src(jobs, links=(), **ctx):
    wo = pd.DataFrame(jobs)
    return SourceData(
        work_orders=wo,
        contractors=pd.DataFrame({"contractor_id": ["CT01", "CT02", "CT03"],
                                  "contractor_name": ["Alpha (synthetic)", "Beta (synthetic)", "Gamma (synthetic)"]}),
        rate_card=pd.DataFrame({"repair_method": ["Drain desilting", "Cold mix patch"],
                                "unit": ["per job", "per sqm"], "standard_rate_inr": [90000, 1800]}),
        roads=pd.DataFrame({"road_id": ["RD1", "RD2"], "ward_code": ["A", "B"]}),
        complaint_links=pd.DataFrame(list(links), columns=["work_order_id", "complaint_id", "received_at"]),
        **ctx)


def by(rows, cid, month="2025-07"):
    return next(r for r in rows if r["contractor_id"] == cid and r["month"].strftime("%Y-%m") == month)


def links_for(ids, received="2025-07-10 00:00"):
    return [(f"WO{i:03d}", f"C{i:03d}", received) for i in ids]


# ── processor ────────────────────────────────────────────────────────────────
def test_month_from_completed_at_and_null_completion_excluded():
    jobs = [job(1, completed="2025-06-30 23:59"), job(2, completed="2025-07-01 00:01"), job(3, completed=None)]
    res = process(src(jobs), M, T0)
    months = sorted(r["month"] for r in res.rows)
    assert months == [date(2025, 6, 1), date(2025, 7, 1)]
    assert res.run["data_quality"]["jobs_without_completed_at"] == {"count": 1, "work_order_ids": ["WO003"]}
    assert sum(r["completed_jobs"] for r in res.rows) == 2


def test_no_fan_out_from_complaints_rain_stations_or_tides():
    jobs = [job(1, cost=100000, assigned="2025-07-08 00:00", completed="2025-07-10 12:00")]
    links = [("WO001", "C1", "2025-07-09 12:00"), ("WO001", "C2", "2025-07-08 12:00"),
             ("WO001", "C3", "2025-07-10 00:00"), ("WO001", "C3", "2025-07-10 00:00")]  # duplicate link
    days = ["2025-07-08", "2025-07-09", "2025-07-10"]
    rain = pd.DataFrame([(d, s, mm, cat) for d in days for s, mm, cat in
                         (("Santacruz", 80, "Heavy"), ("Colaba", 10, "Light"))],
                        columns=["date", "station", "rainfall_mm", "imd_category"])
    tides = pd.DataFrame([(d, t, 4.6, "Y") for d in days for t in ("01:00", "13:00")],
                         columns=["date", "high_tide_time", "height_m", "big_tide_flag"])
    r = process(src(jobs, links, rainfall_daily=rain, tides=tides), M, T0).rows[0]
    assert r["completed_jobs"] == 1 and r["total_billed_inr"] == 100000
    assert r["evidence_work_order_ids"] == ["WO001"]
    assert r["speed_median_hours"] == 48.0  # earliest complaint (07-08 12:00) -> 07-10 12:00
    assert r["context"]["rainfall"]["jobs_covered"] == 1
    assert r["context"]["rainfall"]["median_window_max_rainfall_mm"] == 80
    assert r["context"]["rainfall"]["jobs_with_heavy_rain_day"] == 1
    assert r["context"]["tides"]["jobs_with_big_tide_day"] == 1


def test_null_outcomes_are_missing_not_failures():
    jobs = [job(i, sla=s, reopen=o) for i, (s, o) in enumerate([("Y", "Y"), ("N", None), (None, "N"), ("", "N")])]
    r = process(src(jobs), M, T0).rows[0]
    assert (r["sla_known"], r["sla_met"], r["sla_missing"], r["sla_rate"]) == (2, 1, 2, 0.5)
    assert (r["reopen_known"], r["reopened"], r["reopen_missing"]) == (3, 1, 1)
    assert r["reopen_rate"] == pytest.approx(1 / 3, abs=1e-6)


def test_speed_normalized_by_month_and_method_cohort():
    # Drain jobs: CT01 takes 10h, CT02 30h -> cohort median 20h. Cold mix: CT01 100h, CT02 300h -> 200h.
    jobs, links = [], []
    i = 0
    for cid, hrs_drain, hrs_cold in (("CT01", 10, 100), ("CT02", 30, 300)):
        for _ in range(3):
            for meth, h in (("Drain desilting", hrs_drain), ("Cold mix patch", hrs_cold)):
                i += 1
                done = pd.Timestamp("2025-07-01 00:00") + pd.Timedelta(hours=h)
                jobs.append(job(i, contractor=cid, method=meth, completed=str(done), assigned="2025-07-01 00:00"))
                links.append((f"WO{i:03d}", f"C{i}", "2025-07-01 00:00"))
    rows = process(src(jobs, links), M, T0).rows
    a, b = by(rows, "CT01"), by(rows, "CT02")
    assert a["speed_relative_index"] == 0.5 and b["speed_relative_index"] == 1.5
    assert a["speed_rank"] == 1 and b["speed_rank"] == 2
    assert a["workload_mix"]["speed_by_repair_method"]["Cold mix patch"]["cohort_median_hours"] == 200


def test_speed_excludes_unlinked_negative_and_small_cohort_jobs():
    jobs = [job(i) for i in range(1, 6)] + [job(6, method="Cold mix patch")]
    links = links_for([1, 2, 3]) + [("WO004", "C004", "2025-07-11 00:00")]  # WO004 complaint after completion
    links += links_for([6])  # alone in its cohort
    r = process(src(jobs, links), M, T0).rows[0]
    assert r["data_quality"]["speed_missing_reasons"] == {
        "cohort_too_small": 1, "complaint_after_completion": 1, "no_linked_complaint": 1}
    assert r["speed_sample"] == 3 and r["speed_missing"] == 3 and r["speed_raw_sample"] == 4


def test_eligibility_is_metric_specific():
    # CT01: 5 jobs, no complaint links -> SLA ranked, speed unranked with a reason.
    jobs = [job(i, contractor="CT01") for i in range(1, 6)]
    r = process(src(jobs), M, T0).rows[0]
    assert r["sla_rank"] == 1 and r["speed_rank"] is None
    assert r["rank_eligibility"]["speed"] == {"eligible": False, "sample": 0, "min_sample": 5,
                                              "reason": "no known values"}
    small = process(src([job(i, contractor="CT01") for i in range(1, 4)]), M, T0).rows[0]
    assert small["rank_eligibility"]["sla"]["reason"] == "sample 3 < min 5" and small["sla_rank"] is None


def test_ties_share_rank_competition_style():
    jobs = [job(n * 5 + k, contractor=cid, sla=sla)
            for n, (cid, sla) in enumerate((("CT01", "Y"), ("CT02", "Y"), ("CT03", "N"))) for k in range(5)]
    rows = process(src(jobs), M, T0).rows
    assert [by(rows, c)["sla_rank"] for c in ("CT01", "CT02", "CT03")] == [1, 1, 3]
    assert all(r["rank_cohort_sizes"]["sla"] == 3 for r in rows)


def test_cost_alignment_rewards_closeness_not_cheapness():
    m = Methodology("t", cost_tolerance=0.30, min_sample=1, min_cohort=3, rank_decimals=6)
    jobs = [job(1, contractor="CT01", cost=90000),                         # exact -> 0% dev
            job(2, contractor="CT02", cost=45000),                         # 50% under -> 0.5 dev
            job(3, contractor="CT03", method="Cold mix patch", area=10, cost=27000),  # 18000 benchmark, +50%
            job(4, contractor="CT03", method="Unknown method", cost=1)]
    rows = process(src(jobs), m, T0).rows
    a, b, c = by(rows, "CT01"), by(rows, "CT02"), by(rows, "CT03")
    assert a["cost_rank"] == 1 and b["cost_rank"] == 2 and b["cost_under_tolerance_count"] == 1
    assert b["cost_over_tolerance_count"] == 0
    assert c["cost_median_abs_pct_dev"] == 0.5 and c["cost_over_tolerance_count"] == 1
    assert c["data_quality"]["cost_missing_reasons"] == {"no_rate_card": 1} and c["cost_sample"] == 1


def test_per_sqm_without_area_is_missing():
    r = process(src([job(1, method="Cold mix patch", area=None)]), M, T0).rows[0]
    assert r["cost_sample"] == 0 and r["data_quality"]["cost_missing_reasons"] == {"missing_area": 1}


def test_ward_mismatch_reported_not_silently_resolved():
    res = process(src([job(1, road="RD2", ward="A")]), M, T0)
    r = res.rows[0]
    assert r["data_quality"]["ward_mismatch_work_order_ids"] == ["WO001"]
    assert r["workload_mix"]["wards"] == {"A": 1}
    assert res.run["data_quality"]["ward_mismatch_count"] == 1


def test_context_tables_aggregate_once_and_missing_tables_are_null():
    jobs = [job(1, road="RD1"), job(2, road="RD1"), job(3, road="RD2", ward="B")]
    ctx = dict(
        flood_hotspots=pd.DataFrame({"hotspot_id": ["H1", "H2"], "ward_code": ["A", "A"],
                                     "flood_threshold_mm_per_day": [60, 90], "tide_sensitive": ["Y", "N"]}),
        traffic=pd.DataFrame({"road_id": ["RD1"], "peak_hour_vehicles": [1000], "congestion_index_0_10": [5]}),
        accidents=pd.DataFrame({"accident_id": ["A1", "A2", "A3"], "road_id": ["RD1", "RD1", "RD2"],
                                "occurred_at": ["2025-07-02 10:00", "2025-08-02 10:00", "2025-07-20 10:00"],
                                "severity": ["Minor", "Fatal", "Grievous"]}),
        facilities=pd.DataFrame({"facility_id": ["F1", "F2"], "type": ["Hospital", "School"],
                                 "ambulance_entry_road": ["RD1", "RD1"]}),
    )
    res = process(src(jobs, **ctx), M, T0)
    c = res.rows[0]["context"]
    assert res.rows[0]["completed_jobs"] == 3  # two hotspots / two facilities do not multiply jobs
    assert c["flood_hotspots"]["jobs_in_hotspot_wards"] == 2
    assert c["flood_hotspots"]["jobs_in_tide_sensitive_hotspot_wards"] == 2
    assert c["traffic"]["jobs_covered"] == 2 and c["traffic"]["mean_peak_hour_vehicles"] == 1000
    assert c["accidents"]["accidents"] == 2 and c["accidents"]["by_severity"] == {"Grievous": 1, "Minor": 1}
    assert c["facility_access"]["jobs_on_ambulance_entry_roads"] == 2
    assert c["facility_access"]["distinct_facilities_by_type"] == {"Hospital": 1, "School": 1}
    assert c["rainfall"] is None and c["tides"] is None
    assert set(res.run["data_quality"]["context_tables_missing"]) == {"rainfall_daily", "tides"}


def test_unknown_contractor_is_reported_and_skipped():
    res = process(src([job(1), job(2, contractor="CT99")]), M, T0)
    assert res.run["data_quality"]["unknown_contractor_work_order_ids"] == ["WO002"]
    assert [r["contractor_id"] for r in res.rows] == ["CT01"]


def test_refresh_is_deterministic_and_idempotent():
    jobs = [job(i, contractor=c) for i, c in enumerate(["CT01"] * 6 + ["CT02"] * 6)]
    assert process(src(jobs), M, T0).rows == process(src(jobs), M, T0).rows
    store = MemoryStore()
    store.write(process(src(jobs), M, T0))
    store.write(process(src(jobs), M, T0))
    assert len(store.rows) == 2
    store.write(process(src(jobs[:6]), M, T0))  # CT02 gone -> its stale row is removed
    assert [k[0] for k in store.rows] == ["CT01"]


def test_postgres_write_builds_one_transaction_with_upsert():
    calls = []

    class Conn:
        def execute(self, stmt, params=None):
            calls.append((str(stmt), params))

    class Begin:
        def __enter__(self): return Conn()
        def __exit__(self, *a): return False

    class Eng:
        def begin(self): return Begin()

    res = process(src([job(1), job(2)]), M, T0)
    assert PostgresRepository(Eng()).write(res) == 1
    sql = [c[0] for c in calls]
    assert "INSERT INTO contractor_scorecard_runs" in sql[0] and "ON CONFLICT (methodology_version)" in sql[0]
    assert sql[1].startswith("DELETE FROM contractor_monthly_scorecards")
    assert "ON CONFLICT (contractor_id, month, methodology_version) DO UPDATE" in sql[2]
    assert calls[1][1]["keys"] == ["CT01|2025-07-01"]


# ── API ──────────────────────────────────────────────────────────────────────
@pytest.fixture
def client():
    jobs = ([job(i, contractor="CT01", sla="Y") for i in range(1, 7)]
            + [job(i, contractor="CT02", sla="N") for i in range(7, 13)]
            + [job(13, contractor="CT03", completed="2025-08-03 10:00")])
    store = MemoryStore({"CT01": "Alpha (synthetic)", "CT02": "Beta (synthetic)", "CT03": "Gamma (synthetic)"})
    svc = ScorecardService(store)
    store.write(process(src(jobs, links_for(range(1, 13))), M, T0))
    app = FastAPI()
    app.include_router(cp_router.router)
    app.dependency_overrides[cp_router.get_service] = lambda: svc
    return TestClient(app)


BASE = "/api/v3/contractor-performance"


def test_monthly_endpoint_shape_sort_and_filters(client):
    r = client.get(f"{BASE}/monthly", params={"from": "2025-07", "to": "2025-08", "sort_by": "sla_rank"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [m["month"] for m in body["months"]] == ["2025-07", "2025-08"]
    jul = body["months"][0]["contractors"]
    assert [c["contractor_id"] for c in jul] == ["CT01", "CT02"]
    assert jul[0]["sla"] == {"count": 6, "known": 6, "missing": 0, "rate": 1.0, "rank": 1, "cohort_size": 2}
    assert jul[0]["evidence_work_order_ids"][0] == "WO001"
    aug = body["months"][1]["contractors"][0]
    assert aug["sla"]["rank"] is None and aug["rank_eligibility"]["sla"]["reason"] == "sample 1 < min 5"
    assert body["run"]["params"]["min_sample"] == 5
    r = client.get(f"{BASE}/monthly", params={"min_jobs": 2})
    assert [m["month"] for m in r.json()["months"]] == ["2025-07"]


def test_monthly_validation(client):
    assert client.get(f"{BASE}/monthly", params={"from": "2025-7"}).status_code == 422
    assert client.get(f"{BASE}/monthly", params={"from": "2025-09", "to": "2025-06"}).status_code == 422
    assert client.get(f"{BASE}/monthly", params={"sort_by": "overall"}).status_code == 422
    assert client.get(f"{BASE}/monthly", params={"methodology_version": "v9"}).status_code == 422


def test_contractor_series_and_404s(client):
    r = client.get(f"{BASE}/contractors/CT03")
    assert r.status_code == 200 and [m["month"] for m in r.json()["months"]] == ["2025-08"]
    assert client.get(f"{BASE}/contractors/CT03", params={"to": "2025-07"}).json()["months"] == []
    assert client.get(f"{BASE}/contractors/CT99").status_code == 404


def test_no_run_yet_is_404_and_methodology_doc(client):
    app = FastAPI()
    app.include_router(cp_router.router)
    app.dependency_overrides[cp_router.get_service] = lambda: ScorecardService(MemoryStore({"CT01": "x"}))
    r = TestClient(app).get(f"{BASE}/monthly")
    assert r.status_code == 404 and "refresh" in r.json()["detail"]
    doc = client.get(f"{BASE}/methodology").json()
    assert [d["key"] for d in doc["dimensions"]] == ["speed", "sla", "durability", "cost_alignment"]
