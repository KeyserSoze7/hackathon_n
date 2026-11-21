"""Load the hackathon CSVs into Supabase as tables with the same names.
   DATABASE_URL=postgresql://postgres:<pw>@db.<ref>.supabase.co:5432/postgres python load_to_supabase.py --csv-dir data
"""
import argparse, os, pandas as pd, sqlalchemy as sa

TABLES = ["work_orders", "wards", "roads", "rate_card", "rainfall_daily", "tides", "traffic",
          "accidents", "facilities", "flood_hotspots", "complaints", "localities", "contractors"]

ap = argparse.ArgumentParser(); ap.add_argument("--csv-dir", default="data"); a = ap.parse_args()
eng = sa.create_engine(os.environ["DATABASE_URL"])
for t in TABLES:
    df = pd.read_csv(f"{a.csv_dir}/{t}.csv")
    df.to_sql(t, eng, if_exists="replace", index=False, chunksize=1000, method="multi")
    print(f"{t}: {len(df)} rows")
