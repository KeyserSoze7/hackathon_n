"""Health check: confirms the API can reach the database and the pipelines have run."""
from fastapi import APIRouter

from backend import schemas as s
from backend.database import one

router = APIRouter(tags=["Meta"])


@router.get("/api/health", response_model=s.Health, summary="Health + row counts")
def health():
    return one("SELECT (SELECT count(*) FROM work_orders) AS work_orders, (SELECT count(*) FROM flags) AS flags, "
               "(SELECT count(*) FROM v3_next_rupee) AS v3_items", "db")
