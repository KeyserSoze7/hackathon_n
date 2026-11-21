"""View 2: Road Story / Rupee Receipt. Road header + work orders + flags, connected timeline, Right-of-Reply."""
from fastapi import APIRouter, Path
from sqlalchemy import text

from backend import schemas as s
from backend.database import get_engine, one, rows

router = APIRouter(tags=["View 2: Road Story"])


@router.get("/api/roads/{road_id}", response_model=s.RoadReceipt, responses=s.NOT_FOUND, summary="Road receipt: header, work orders, flags + replies")
def road(road_id: str = Path(examples=["RD0058"])):
    """View 2 header card + work orders + flags (with replies)."""
    r = one("SELECT * FROM road_audit WHERE road_id = %(r)s", f"road {road_id}", r=road_id)
    r["work_orders"] = rows(
        "SELECT wo.work_order_id, wo.contractor_id, c.contractor_name, wo.work_type, wo.repair_method, wo.cost_inr, "
        "wo.assigned_at, wo.completed_at, wo.sla_met, wo.reopened_within_30d, wo.engineer_remark "
        "FROM work_orders wo JOIN contractors c USING (contractor_id) WHERE wo.road_id = %(r)s ORDER BY wo.assigned_at",
        r=road_id)
    r["flags"] = rows(
        "SELECT f.*, COALESCE((SELECT json_agg(rp ORDER BY rp.created_at) FROM flag_replies rp "
        "WHERE rp.flag_id = f.flag_id), '[]') AS replies FROM flags f WHERE f.road_id = %(r)s "
        "ORDER BY f.tier, f.rupees_at_stake DESC", r=road_id)
    return r


@router.get("/api/roads/{road_id}/timeline", response_model=list[s.TimelineEvent], responses=s.NOT_FOUND, summary="Connected trail: complaints -> work orders -> accidents -> reports")
def road_timeline(road_id: str = Path(examples=["RD0058"])):
    """View 2 connected trail, chronological."""
    one("SELECT 1 FROM roads WHERE road_id = %(r)s", f"road {road_id}", r=road_id)
    return rows("SELECT * FROM road_timeline WHERE road_id = %(r)s ORDER BY event_at, event_type", r=road_id)


@router.get("/api/flags/{flag_id}", response_model=s.FlagWithReplies, responses=s.NOT_FOUND, summary="One flag with its replies")
def flag(flag_id: str = Path(description="<DETECTOR>:<work_order_id>", examples=["DLP_PAID_TWICE:WO25-01994"])):
    f = one("SELECT * FROM flags WHERE flag_id = %(f)s", f"flag {flag_id}", f=flag_id)
    f["replies"] = rows("SELECT * FROM flag_replies WHERE flag_id = %(f)s ORDER BY created_at", f=flag_id)
    return f


@router.post("/api/flags/{flag_id}/replies", status_code=201, response_model=s.Reply, responses=s.NOT_FOUND, summary="Add Right-of-Reply to a flag")
def add_reply(flag_id: str, req: s.ReplyReq):
    """View 2 Right-of-Reply."""
    one("SELECT 1 FROM flags WHERE flag_id = %(f)s", f"flag {flag_id}", f=flag_id)
    with get_engine().begin() as c:
        r = c.execute(text("INSERT INTO flag_replies (flag_id, author_role, author_name, body) "
                           "VALUES (:f, :role, :name, :body) RETURNING id, flag_id, author_role, author_name, body, created_at"),
                      {"f": flag_id, "role": req.author_role, "name": req.author_name, "body": req.body}).mappings().one()
    return dict(r)
