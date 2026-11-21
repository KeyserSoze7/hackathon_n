"""
View 3 backend: fair contractor scorecard (3A) + next-rupee planner (3B).

  python view3_pipeline.py --csv-dir path/to/data            # local, DuckDB on the CSVs
  DATABASE_URL=postgresql://... python view3_pipeline.py      # Supabase: reads tables, writes results back

SQL (sql/01_features.sql) builds the feature views; XGBoost + SHAP run here in Python;
results land in out/*.json (frontend contract) and, with DATABASE_URL, in Supabase tables.
Every number is computed in code. Claude only turns the `drivers` / `explanation` fields into prose.
"""
import argparse, json, os, pathlib
import numpy as np, pandas as pd, xgboost as xgb, shap
from scipy.stats import chi2, spearmanr
from sklearn.model_selection import StratifiedKFold, KFold
from sklearn.metrics import roc_auc_score

HERE = pathlib.Path(__file__).parent
TABLES = ["work_orders", "wards", "roads", "rate_card", "rainfall_daily", "tides", "traffic",
          "accidents", "facilities", "flood_hotspots", "complaints", "localities", "contractors"]
SEED = 7
PRIOR_K = 10          # pseudo-jobs of "as expected" performance; shrinks small samples toward 100
ADJUST_FOR_METHOD = False  # method choice is treated as the contractor's responsibility


# ---------------------------------------------------------------- data access
def load(csv_dir):
    feats_sql = (HERE / "sql" / "01_features.sql").read_text()
    url = os.environ.get("DATABASE_URL")
    if url:
        import sys; sys.path.insert(0, str(HERE.parent / "backend")); from db import engine
        eng = engine()
        with eng.begin() as c:
            c.exec_driver_sql(feats_sql)
            # Supabase exposes public views to the anon key. Run them as the caller (RLS applies) and make
            # them read-only: v_ward_station is auto-updatable and would otherwise write through to wards.
            for v in ["v_ward_station", "v_road_geo", "v_wo_context", "v_complaint_road", "v_road_static", "v_road_activity"]:
                c.exec_driver_sql(f"ALTER VIEW {v} SET (security_invoker = true)")
                c.exec_driver_sql(f"REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON {v} FROM anon, authenticated")
        q = lambda s: _yn(_floatify(pd.read_sql(s, eng)))
    else:
        import duckdb
        con = duckdb.connect()
        for t in TABLES:
            con.execute(f"CREATE TABLE {t} AS SELECT * FROM read_csv_auto('{csv_dir}/{t}.csv', header=true)")
        con.execute(feats_sql)
        q = lambda s: _yn(con.execute(s).df())
        eng = None
    d = {v: q(f"SELECT * FROM {v}") for v in ["v_wo_context", "v_road_static", "v_road_activity"]}
    for t in ["wards", "work_orders", "rate_card", "roads"]:
        d[t] = q(f"SELECT * FROM {t}")
    d["under_reported"] = under_reported_wards(eng)
    return d, eng


def under_reported_wards(eng):
    """UNDER_REPORTED_WARD comes from the audit engine (pipeline/build.py), so both views agree."""
    if eng is not None:
        return set(pd.read_sql("SELECT ward_code FROM ward_audit WHERE under_reported_flag", eng).ward_code)
    path = HERE.parent / "exports" / "ward_audit.csv"
    if not path.exists():
        raise SystemExit(f"{path} missing: run `python3 pipeline/build.py` first")
    wa = pd.read_csv(path)
    return set(wa.loc[wa.under_reported_flag.astype(str).str.lower() == "true", "ward_code"])


def _yn(df):
    """Supabase stores Y/N flags as boolean; this code compares against 'Y'/'N'. Map back."""
    for c in df.columns:
        vals = df[c].dropna()
        if len(vals) and vals.map(lambda v: isinstance(v, (bool, np.bool_))).all():
            df[c] = df[c].map({True: "Y", False: "N"})
    return df


def _floatify(df):
    """Postgres NUMERIC arrives as Python Decimal; XGBoost needs floats."""
    from decimal import Decimal
    for c in df.columns:
        if df[c].dtype == object and df[c].map(lambda v: isinstance(v, Decimal)).any():
            df[c] = df[c].astype(float)
    return df


def encode(df, cats):
    X = df.copy()
    for c in cats:
        X[c] = X[c].astype("category")
    return X


def xgb_clf():
    return xgb.XGBClassifier(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8,
                             colsample_bytree=0.8, min_child_weight=5, enable_categorical=True,
                             tree_method="hist", random_state=SEED, eval_metric="logloss")


# ---------------------------------------------------------------- 3A: fair scorecard
CTX_NUM = ["low_lying_index", "rain_next7_mm", "heavy_days_next7", "rain_during_mm", "big_tides_next7",
           "hotspot_dist_m", "lanes", "road_age_years", "peak_hour_vehicles", "congestion_index_0_10",
           "two_wheeler_share_pct", "area_sqm", "month"]
CTX_CAT = ["work_type", "road_type", "surface", "under_dlp"] + (["repair_method"] if ADJUST_FOR_METHOD else [])

FEATURE_TEXT = {
    "rain_next7_mm": "rain in the week after the repair",
    "heavy_days_next7": "heavy-rain days right after the repair",
    "rain_during_mm": "rain while the work was being done",
    "big_tides_next7": "big tides right after the repair",
    "low_lying_index": "how flood-prone the ward is",
    "hotspot_dist_m": "closeness to a flood hotspot",
    "work_type": "the kind of jobs assigned",
    "road_type": "the type of roads worked on",
    "surface": "road surface type",
    "road_age_years": "age of the road surface",
    "peak_hour_vehicles": "traffic load",
    "congestion_index_0_10": "congestion",
    "two_wheeler_share_pct": "two-wheeler share",
    "area_sqm": "size of the jobs",
    "month": "time of the season",
    "lanes": "road width",
    "under_dlp": "warranty status of the roads",
    "repair_method": "repair method",
}


def oof_expected(X, y):
    """Out-of-fold P(event | context), so no job is scored by a model that saw it."""
    p = np.zeros(len(y))
    for tr, te in StratifiedKFold(5, shuffle=True, random_state=SEED).split(X, y):
        m = xgb_clf().fit(X.iloc[tr], y[tr])
        p[te] = m.predict_proba(X.iloc[te])[:, 1]
    full = xgb_clf().fit(X, y)
    return p, full, roc_auc_score(y, p)


def poisson_ci(o, e, a=0.10):
    lo = chi2.ppf(a / 2, 2 * o) / 2 / e if o > 0 else 0.0
    hi = chi2.ppf(1 - a / 2, 2 * (o + 1)) / 2 / e
    return lo, hi


def index_vs_expected(O, E):
    """0-100 index. 50 = exactly as expected for these conditions; higher = fewer events than expected."""
    shr = (O + PRIOR_K * 1.0) / (E + PRIOR_K * 1.0)     # shrunk observed/expected ratio
    lo, hi = poisson_ci(O, E)
    verdict = ("better than expected" if hi < 1 else "worse than expected" if lo > 1
               else "within the normal range")
    return round(float(np.clip(50 + 50 * (1 - shr), 0, 100)), 1), round(O / E, 3), (round(lo, 3), round(hi, 3)), verdict


def scorecard(d):
    wo = d["v_wo_context"].copy()
    X = encode(wo[CTX_NUM + CTX_CAT], CTX_CAT)
    y_re = (wo.reopened_within_30d == "Y").astype(int).values
    y_sla = (wo.sla_met == "N").astype(int).values

    wo["p_reopen"], m_re, auc_re = oof_expected(X, y_re)
    wo["p_sla_miss"], _, auc_sla = oof_expected(X, y_sla)
    sv = shap.TreeExplainer(m_re).shap_values(X)  # log-odds contributions per job
    sv = pd.DataFrame(sv, columns=X.columns, index=wo.index)
    city_ctx = wo[["rain_next7_mm", "heavy_days_next7", "big_tides_next7", "low_lying_index"]].mean()
    city_reopen = y_re.mean()

    rows, job_rows = [], []
    for (cid, cname), g in wo.groupby(["contractor_id", "contractor_name"]):
        idx = g.index
        O, E = y_re[idx].sum(), g.p_reopen.sum()
        dur_idx, oe, ci, verdict = index_vs_expected(O, E)
        Os, Es = y_sla[idx].sum(), g.p_sla_miss.sum()
        spd_idx, _, _, spd_verdict = index_vs_expected(Os, Es)

        # Context story: which conditions made this contractor's jobs harder than the city average?
        diff = sv.loc[idx].mean() - sv.mean()
        top = diff.sort_values(ascending=False)
        drivers = [{"feature": f, "plain": FEATURE_TEXT.get(f, f), "effect_logodds": round(float(v), 3),
                    "direction": "made failures more likely" if v > 0 else "made failures less likely"}
                   for f, v in pd.concat([top.head(2), top.tail(1)]).items() if abs(v) > 0.01]

        cost_ratio = g.cost_vs_rate
        method_mix = g.repair_method.value_counts(normalize=True).head(3).round(2).to_dict()
        rows.append({
            "contractor_id": cid, "contractor_name": cname,
            "jobs_count": int(len(g)), "total_billed_inr": int(g.cost_inr.sum()),
            "reopen_rate_30d": round(float(y_re[idx].mean()), 3),
            "expected_reopen_rate_30d": round(float(E / len(g)), 3),
            "sla_met_rate": round(float(1 - y_sla[idx].mean()), 3),
            "expected_sla_met_rate": round(float(1 - Es / len(g)), 3),
            "durability_index": dur_idx, "durability_verdict": verdict,
            "durability_ratio_obs_over_exp": oe, "durability_ratio_ci90": ci,
            "speed_index": spd_idx, "speed_verdict": spd_verdict,
            "risk_adjusted_score": round(0.6 * dur_idx + 0.4 * spd_idx, 1),
            "cost_vs_rate_median": round(float(cost_ratio.median()), 3),
            "jobs_over_130pct_rate": int((cost_ratio > 1.3).sum()),
            "method_mix_top3": method_mix,
            "context": {
                "avg_rain_next7_mm": round(float(g.rain_next7_mm.mean()), 1),
                "city_avg_rain_next7_mm": round(float(city_ctx.rain_next7_mm), 1),
                "avg_big_tides_next7": round(float(g.big_tides_next7.mean()), 2),
                "avg_low_lying_index": round(float(g.low_lying_index.mean()), 3),
                "flood_prone_share": round(float((g.hotspot_dist_m < 1000).mean()), 3),
                "avg_peak_vehicles": int(g.peak_hour_vehicles.mean()),
            },
            "drivers": drivers,
            "evidence_reopened_wo_ids": g.loc[g.reopened_within_30d == "Y", "work_order_id"].head(10).tolist(),
        })
        rows[-1]["explanation"] = explain_contractor(rows[-1], city_reopen)

    for _, r in wo.iterrows():
        job_rows.append((r.work_order_id, r.contractor_id, round(r.p_reopen, 4), round(r.p_sla_miss, 4)))
    jobs = pd.DataFrame(job_rows, columns=["work_order_id", "contractor_id", "p_reopen_expected", "p_sla_miss_expected"])
    meta = {"reopen_model_auc_oof": round(auc_re, 3), "sla_model_auc_oof": round(auc_sla, 3),
            "city_reopen_rate": round(float(city_reopen), 3), "prior_k": PRIOR_K,
            "adjusted_for_method": ADJUST_FOR_METHOD}
    return sorted(rows, key=lambda r: -r["risk_adjusted_score"]), jobs, meta


def explain_contractor(r, city):
    s = (f"{r['contractor_name']} did {r['jobs_count']} jobs. {r['reopen_rate_30d']:.0%} failed within 30 days; "
         f"given the rain, tides and roads they worked on, about {r['expected_reopen_rate_30d']:.0%} would be expected "
         f"(city average {city:.0%}). Durability is {r['durability_verdict']} (score {r['durability_index']:.0f}/100, where 50 = as expected). ")
    harder = [x["plain"] for x in r["drivers"] if x["effect_logodds"] > 0]
    if harder:
        s += "Their jobs were harder than average because of " + " and ".join(harder) + ". "
    s += (f"Deadlines met: {r['sla_met_rate']:.0%} vs {r['expected_sla_met_rate']:.0%} expected. "
          f"Median bill was {r['cost_vs_rate_median']:.2f}x the rate card")
    s += f"; {r['jobs_over_130pct_rate']} jobs were above 1.3x." if r["jobs_over_130pct_rate"] else "."
    return s


# 3B lives in allocator.py (budget allocation as an exact MILP; no forecasting).
import sys; sys.path.insert(0, str(HERE)); import allocator


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv-dir", default="data")
    ap.add_argument("--out", default=str(HERE / "out"))
    ap.add_argument("--budget", type=float, default=None, help="city budget in Rs; default = 2025 money left in wards")
    a = ap.parse_args()
    d, eng = load(a.csv_dir)
    cards, jobs, meta_a = scorecard(d)
    out = pathlib.Path(a.out); out.mkdir(exist_ok=True, parents=True)
    roads, ward_alloc, meta_b, _ = allocator.run(d, budget=a.budget, out_dir=out)
    dump = lambda name, obj: (out / name).write_text(json.dumps(obj, indent=2, default=_json))
    dump("contractors.json", cards)
    dump("view3_model_meta.json", {"scorecard": meta_a, "allocation": meta_b})
    jobs.to_csv(out / "job_expected_risk.csv", index=False)
    if eng is not None:
        # Tables, types (jsonb for nested fields) and RLS live in supabase/migrations/20261121000100_audit_views.sql.
        # Truncate + insert in one transaction: readers never see a half-written or unprotected table.
        flat = lambda rows: pd.DataFrame([{k: (json.dumps(v, default=_json) if isinstance(v, (dict, list, tuple)) else v)
                                           for k, v in r.items()} for r in rows])
        out_tables = [("v3_contractor_scorecard", flat(cards)), ("v3_next_rupee", flat(roads)),
                      ("v3_ward_allocation", pd.DataFrame(ward_alloc)), ("v3_job_expected_risk", jobs)]
        with eng.begin() as c:
            c.exec_driver_sql("TRUNCATE " + ", ".join(t for t, _ in out_tables))
            for t, df in out_tables:
                df.to_sql(t, c, if_exists="append", index=False, method="multi", chunksize=1000)
    print(json.dumps({"scorecard": meta_a, "allocation": {k: v for k, v in meta_b.items() if k != "method_failure_rates"}}, indent=2))


def _json(o):
    if isinstance(o, (np.integer,)): return int(o)
    if isinstance(o, (np.floating,)): return float(o)
    if isinstance(o, (np.bool_,)): return bool(o)
    return str(o)


if __name__ == "__main__":
    main()
