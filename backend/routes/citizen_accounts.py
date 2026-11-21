"""View 4: citizen accounts. Anonymous bearer-token identity (no login wall), "my reports" with stats, and the
citizen's confirmation that a fix holds (or that the problem is back).

Create an account with POST /api/citizens, keep the token, and send `Authorization: Bearer <token>`.
All rupee figures are sums of flags' rupees_at_stake computed here, each flagged bill counted once."""
import secrets
from typing import Literal, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import text

from backend import auth
from backend import report_lifecycle as lc
from backend import schemas as s
from backend.database import get_engine, one, rows
from backend.routes.citizen import add_event, build_report, check_photo_ids, event_out, first_photo_url, report_events

router = APIRouter(tags=["View 4: Citizen Layer"])
OPEN, RESOLVED = tuple(sorted(lc.OPEN)), tuple(sorted(lc.RESOLVED))

# rupees at stake on the bills (work orders) of flags matched to a citizen's reports; flagged_queue = one row per bill
RUPEES_SQL = ("SELECT COALESCE(sum(q.rupees_at_stake), 0)::bigint AS inr FROM flagged_queue q WHERE q.work_order_id IN "
              "(SELECT f.work_order_id FROM citizen_reports cr JOIN flags f ON f.flag_id = cr.flag_id "
              " WHERE cr.citizen_id = CAST(%(c)s AS uuid) {extra})")


@router.post("/api/citizens", status_code=201, response_model=s.CitizenToken,
             summary="Create an anonymous citizen account (returns the bearer token once)")
def create_citizen(req: Optional[s.CitizenCreateReq] = None):
    """No login: the app calls this once, stores `token` and sends `Authorization: Bearer <token>` on citizen calls.
    The token is shown only here (the database keeps its hash). `phone` is optional and never returned."""
    req = req or s.CitizenCreateReq()
    token = auth.new_token(auth.CITIZEN_PREFIX)
    name = (req.display_name or "").strip() or f"Citizen {secrets.token_hex(2).upper()}"
    with get_engine().begin() as c:
        cid = c.execute(text("INSERT INTO citizens (display_name, token_hash, phone) VALUES (:n, :h, :p) "
                             "RETURNING citizen_id::text"),
                        {"n": name, "h": auth.token_hash(token), "p": req.phone}).scalar_one()
    return {"citizen_id": cid, "token": token, "display_name": name}


@router.get("/api/me", response_model=s.Me, responses={401: s.AUTH[401]}, summary="The signed-in citizen + report stats")
def me(citizen: dict = Depends(auth.require_citizen)):
    """stats: reports, distinct roads, open, resolved (resolved + confirmed_fixed), confirmed_fixed, and the rupees at
    stake on bills matched to these reports (rupees_flagged_inr) / on reports currently in payment_held (rupees_held_inr)."""
    st = one("SELECT count(*) AS reports, count(DISTINCT road_id) AS roads, "
             "count(*) FILTER (WHERE status IN %(open)s) AS open, "
             "count(*) FILTER (WHERE status IN %(res)s) AS resolved, "
             "count(*) FILTER (WHERE status = 'confirmed_fixed') AS confirmed_fixed "
             "FROM citizen_reports WHERE citizen_id = CAST(%(c)s AS uuid)", "citizen",
             c=citizen["citizen_id"], open=OPEN, res=RESOLVED)
    st["rupees_flagged_inr"] = rows(RUPEES_SQL.format(extra=""), c=citizen["citizen_id"])[0]["inr"]
    st["rupees_held_inr"] = rows(RUPEES_SQL.format(extra="AND cr.status = 'payment_held'"), c=citizen["citizen_id"])[0]["inr"]
    return {"citizen_id": citizen["citizen_id"], "display_name": citizen["display_name"],
            "joined_at": citizen["joined_at"], "stats": st}


@router.get("/api/me/reports", response_model=list[s.MyReport], responses={401: s.AUTH[401]},
            summary="The signed-in citizen's reports, newest first, with history")
def my_reports(request: Request,
               status: Optional[Union[s.ReportStatus, Literal["open", "closed"]]] = Query(
                   None, description="One status, or open / closed (closed = resolved, confirmed_fixed, rejected, duplicate)"),
               citizen: dict = Depends(auth.require_citizen)):
    statuses = OPEN if status == "open" else tuple(sorted(lc.CLOSED)) if status == "closed" else (status,) if status else None
    rs = rows("SELECT cr.id, cr.kind, cr.issue_type, cr.status, cr.created_at, cr.road_id, r.road_name, r.ward_code, "
              "r.under_dlp, f.flag_id, f.rupees_at_stake, p.photo_id, p.storage, p.storage_path "
              "FROM citizen_reports cr LEFT JOIN roads r ON r.road_id = cr.road_id "
              "LEFT JOIN flags f ON f.flag_id = cr.flag_id "
              "LEFT JOIN LATERAL (SELECT p.* FROM citizen_report_photos crp JOIN photos p USING (photo_id) "
              "  WHERE crp.report_id = cr.id ORDER BY crp.position LIMIT 1) p ON true "
              "WHERE cr.citizen_id = CAST(%(c)s AS uuid) AND (%(any)s OR cr.status IN %(st)s) "
              "ORDER BY cr.created_at DESC, cr.id DESC",
              c=citizen["citizen_id"], any=statuses is None, st=statuses or ("",))
    evs = report_events([r["id"] for r in rs])
    return [{"id": r["id"], "kind": r["kind"], "issue_type": r["issue_type"], "status": r["status"],
             "created_at": r["created_at"],
             "road": {k: r[k] for k in ("road_id", "road_name", "ward_code", "under_dlp")} if r["road_id"] else None,
             "photo_url": first_photo_url(r, request),
             "flag": {"flag_id": r["flag_id"], "rupees_at_stake": r["rupees_at_stake"]} if r["flag_id"] else None,
             "events": [event_out(e) for e in evs[r["id"]]]} for r in rs]


@router.post("/api/citizen-reports/{report_id}/confirm", response_model=s.CitizenReport,
             responses={**s.NOT_FOUND, **s.AUTH, **s.CONFLICT},
             summary="Citizen confirms a fix holds (resolved -> confirmed_fixed) or reopens it")
def confirm_report(report_id: int, req: s.ConfirmReq, request: Request,
                   citizen: dict = Depends(auth.require_citizen)):
    """Only the citizen who filed the report (with their token) can confirm it. fixed=true needs status resolved;
    fixed=false reopens a resolved or confirmed_fixed report. Photos are kept on the history event."""
    check_photo_ids(req.photo_ids)
    with get_engine().begin() as c:
        r = c.execute(text("SELECT status, citizen_id::text AS citizen_id FROM citizen_reports WHERE id = :i FOR UPDATE"),
                      {"i": report_id}).mappings().first()
        if r is None:
            raise HTTPException(404, f"unknown report {report_id}")
        if r["citizen_id"] != citizen["citizen_id"]:
            raise HTTPException(403, "only the citizen who filed this report can confirm it")
        target = lc.confirm_target(r["status"], req.fixed)
        if target is None:
            need = ", ".join(lc.CONFIRM[req.fixed])
            raise HTTPException(409, f"cannot {'confirm' if req.fixed else 'reopen'} a {r['status']} report "
                                     f"(allowed when status is {need})")
        c.execute(text("UPDATE citizen_reports SET status = :t, status_updated_at = now() WHERE id = :i"),
                  {"t": target, "i": report_id})
        add_event(c, report_id, "citizen", "confirm", r["status"], target, note=req.note, photo_ids=req.photo_ids,
                  meta={"fixed": req.fixed})
    return build_report(report_id, request)
