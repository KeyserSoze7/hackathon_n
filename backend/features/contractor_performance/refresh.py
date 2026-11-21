"""Refresh CLI: recompute monthly contractor scorecards and upsert them into Supabase.
Run from backend/:
    DATABASE_URL=... python -m backend.features.contractor_performance.refresh                 # Supabase -> Supabase
    python -m backend.features.contractor_performance.refresh --csv-dir data --dry-run --export /tmp/cp.json
Idempotent: re-running a methodology version replaces that version's rows in one transaction.
"""
import argparse
import logging
import sys

from .config import DEFAULT_VERSION, METHODOLOGIES
from .exporter import export_json
from .repository import CsvRepository, MemoryStore, PostgresRepository
from .service import ScorecardService


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--methodology", default=DEFAULT_VERSION, choices=sorted(METHODOLOGIES))
    ap.add_argument("--csv-dir", help="read sources from data/*.csv instead of the database")
    ap.add_argument("--dry-run", action="store_true", help="compute only; do not write to the database")
    ap.add_argument("--export", help="also write a JSON snapshot to this path")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if a.csv_dir and not a.dry_run:
        ap.error("--csv-dir is for local debugging; combine it with --dry-run (load CSVs into Supabase via "
                 "supabase/load_source.sql, then refresh from the database)")
    if a.csv_dir:
        source, store = CsvRepository(a.csv_dir), MemoryStore()
    else:
        from backend.database import engine
        pg = PostgresRepository(engine())
        source, store = pg, pg

    result = ScorecardService(store, source).refresh(a.methodology, dry_run=a.dry_run)
    for n in result.notes:
        logging.warning(n)
    sc = result.run["source_counts"]
    logging.info("methodology %s: %d contractor-month rows from %d jobs (%d work orders)%s",
                 a.methodology, len(result.rows), sc["jobs_scored"], sc["work_orders"],
                 " [dry run, nothing written]" if a.dry_run else " upserted")
    if a.export:
        logging.info("snapshot written to %s", export_json(result, a.export))
    return 0


if __name__ == "__main__":
    sys.exit(main())
