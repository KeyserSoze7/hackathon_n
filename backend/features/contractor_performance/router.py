"""FastAPI routes (read-only). GETs serve processed rows from contractor_monthly_scorecards; recompute is CLI-only
(python -m features.contractor_performance.refresh)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from backend.schemas import Error
from . import schemas as s
from .config import DEFAULT_VERSION, METHODOLOGIES
from .repository import PostgresRepository, StoreUnavailable
from .service import NotFound, ScorecardService, methodology_doc

TAG = "View 3: Scorecard & Next Rupee"
MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"
ERRORS = {404: {"model": Error}, 422: {"model": Error}, 503: {"model": Error}}
router = APIRouter(prefix="/api/v3/contractor-performance", tags=[TAG])

_service: Optional[ScorecardService] = None


def configure(engine) -> None:
    """Called with the shared engine (backend.database.get_engine) so the feature reuses its connection pool."""
    global _service
    _service = ScorecardService(PostgresRepository(engine))


def get_service() -> ScorecardService:
    global _service
    if _service is None:
        from backend.database import get_engine
        configure(get_engine())
    return _service


def _version(v: str) -> str:
    if v not in METHODOLOGIES:
        raise HTTPException(422, f"unknown methodology_version {v!r}; known: {sorted(METHODOLOGIES)}")
    return v


def _range(f: Optional[str], t: Optional[str]) -> None:
    if f and t and f > t:
        raise HTTPException(422, "'from' must be <= 'to'")


def _call(fn, *a):
    try:
        return fn(*a)
    except NotFound as e:
        raise HTTPException(404, str(e))
    except StoreUnavailable as e:
        raise HTTPException(503, str(e))


@router.get("/monthly", response_model=s.MonthlyResponse, responses=ERRORS,
            summary="Monthly contractor scorecards: separate speed / SLA / durability / cost ranks")
def monthly(month_from: Optional[str] = Query(None, alias="from", pattern=MONTH, examples=["2025-06"]),
            month_to: Optional[str] = Query(None, alias="to", pattern=MONTH, examples=["2025-09"]),
            min_jobs: int = Query(0, ge=0, description="Hide rows with fewer completed jobs (does not re-rank)"),
            sort_by: s.SortBy = Query("speed_rank", description="Null ranks sort last, then contractor_id"),
            methodology_version: str = Query(DEFAULT_VERSION),
            svc: ScorecardService = Depends(get_service)):
    """One block per month; every contractor-month carries four independent ranks (null when its own sample
    is below the methodology minimum, with the reason in `rank_eligibility`), known/missing denominators,
    descriptive context, and the work-order IDs used as evidence. No composite score."""
    _range(month_from, month_to)
    return _call(svc.monthly, _version(methodology_version), month_from, month_to, min_jobs, sort_by)


@router.get("/contractors/{contractor_id}", response_model=s.ContractorSeries, responses=ERRORS,
            summary="One contractor's monthly series with ranks, context and evidence IDs")
def contractor(contractor_id: str = Path(examples=["CT04"]),
               month_from: Optional[str] = Query(None, alias="from", pattern=MONTH),
               month_to: Optional[str] = Query(None, alias="to", pattern=MONTH),
               methodology_version: str = Query(DEFAULT_VERSION),
               svc: ScorecardService = Depends(get_service)):
    """404 for an unknown contractor; an empty `months` list if it has no completed jobs in range."""
    _range(month_from, month_to)
    return _call(svc.contractor, contractor_id, _version(methodology_version), month_from, month_to)


@router.get("/methodology", response_model=s.MethodologyDoc, responses=ERRORS,
            summary="Metric definitions, directions, tie rule, eligibility and limitations")
def methodology(methodology_version: str = Query(DEFAULT_VERSION)):
    return methodology_doc(_version(methodology_version))
