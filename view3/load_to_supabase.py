"""Load the hackathon CSVs into Supabase as tables with the same names.
   DATABASE_URL=postgresql://postgres.<ref>:<pw>@aws-0-<region>.pooler.supabase.com:5432/postgres \
   python load_to_supabase.py --csv-dir data
Safe to re-run: drops the View 3 views first (they depend on these tables), the pipeline recreates them.
"""
import argparse, pathlib, sys, pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from db import engine

TABLES = ["work_orders", "wards", "roads", "rate_card", "rainfall_daily", "tides", "traffic",
          "accidents", "facilities", "flood_hotspots", "complaints", "localities", "contractors"]
VIEWS = ["v_road_activity", "v_road_static", "v_complaint_road", "v_wo_context", "v_road_geo", "v_ward_station"]

ap = argparse.ArgumentParser(); ap.add_argument("--csv-dir", default="data"); a = ap.parse_args()
eng = engine()
with eng.begin() as c:
    for v in VIEWS:
        c.exec_driver_sql(f"DROP VIEW IF EXISTS {v} CASCADE")
for t in TABLES:
    df = pd.read_csv(f"{a.csv_dir}/{t}.csv")
    df.to_sql(t, eng, if_exists="replace", index=False, chunksize=1000, method="multi")
    print(f"{t}: {len(df)} rows")
