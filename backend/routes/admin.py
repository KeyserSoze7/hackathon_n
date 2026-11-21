"""Admin & ward-officer dashboard: access requests, login, report queue + triage, contractor notices, flags awaiting
reply. Every route except POST /api/admin/access-requests and POST /api/admin/login needs
`Authorization: Bearer <token from /api/admin/login>`.

Roles: admin (every ward; approves access requests) and ward_officer (only their ward_codes). A report's ward is its
matched road's ward, else its matched locality's ward; reports with neither are visible to admins only.
Numbers (counts, hours, rupees) are computed here in SQL; rupees count each flagged bill once (flagged_queue)."""
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend import auth
from backend import report_lifecycle as lc
from backend import schemas as s
from backend.database import get_engine, invalid, norm_ward, one, rows
from backend.photos import public_url
from backend.routes.citizen import SURFACE_WORK, add_event, build_report, first_photo_url, hold_eligible
from backend.routes.road_story import draft_notice

router = APIRouter(tags=["Admin"])
ADMIN_ONLY = auth.require_admin("admin")
ANY_ADMIN = auth.require_admin()
IST_TZ = "Asia/Kolkata"

# Report ward (road's ward, else matched locality's ward) and SLA due time, shared by the queue, summary and detail.
REPORT_FROM = ("FROM citizen_reports cr LEFT JOIN roads rd ON rd.road_id = cr.road_id "
               "LEFT JOIN localities lo ON lo.locality = cr.matched_locality "
               "LEFT JOIN issue_sla i ON i.issue_type = cr.issue_type ")
WARD = "COALESCE(rd.ward_code, lo.ward_code)"
SLA_DUE = "COALESCE(cr.repair_due_at, cr.created_at + make_interval(hours => i.sla_hours))"
IN_SCOPE = f"(%(all)s OR {WARD} IN %(wards)s)"


def scope_params(wards):
    """SQL params for IN_SCOPE: wards None = every ward."""
    return {"all": wards is None, "wards": tuple(wards) if wards else ("",)}


def report_ward(report_id):
    return one(f"SELECT {WARD} AS ward_code {REPORT_FROM} WHERE cr.id = %(i)s", f"report {report_id}", i=report_id)["ward_code"]


def check_report_access(admin, report_id):
    """404 if unknown; 403 if a ward officer asks for a report outside their wards (or with no ward)."""
    auth.require_ward(admin, report_ward(report_id))


# ── Access requests ─────────────────────────────────────────────────────────
@router.post("/api/admin/access-requests", status_code=201, response_model=s.AccessRequestCreated,
             responses=s.CONFLICT, summary="Request officer access (public; an admin approves it)")
def request_access(req: s.AccessRequestReq):
    """Anyone can ask for ward-officer access. One pending request per email; 409 if pending or already an account."""
    ward, email = norm_ward(req.ward_code), req.email.strip().lower()
    if not rows("SELECT 1 FROM wards WHERE ward_code = %(w)s", w=ward):
        raise invalid("ward_code", f"unknown ward {req.ward_code}")
    if rows("SELECT 1 FROM admin_users WHERE email = %(e)s", e=email):
        raise HTTPException(409, "this email already has an account; sign in via POST /api/admin/login")
    try:
        with get_engine().begin() as c:
            rid = c.execute(text("INSERT INTO admin_access_requests (name, email, designation, ward_code, reason) "
                                 "VALUES (:n, :e, :d, :w, :r) RETURNING request_id"),
                            {"n": req.name.strip(), "e": email, "d": req.designation.strip(), "w": ward,
                             "r": req.reason.strip()}).scalar_one()
    except IntegrityError:  # admin_access_requests_one_pending
        raise HTTPException(409, "a request for this email is already pending")
    return {"request_id": rid, "status": "pending"}


@router.get("/api/admin/access-requests", response_model=list[s.AccessRequest], responses=s.AUTH,
            summary="List access requests (admin only)")
def list_access_requests(status: Optional[Literal["pending", "approved", "rejected"]] = Query(None),
                         admin: dict = Depends(ADMIN_ONLY)):
    return rows("SELECT request_id, name, email, designation, ward_code, reason, status, created_at, decided_at, "
                "decision_note, admin_id::text AS admin_id FROM admin_access_requests "
                "WHERE (%(s)s IS NULL OR status = %(s)s) ORDER BY (status = 'pending') DESC, created_at DESC",
                s=status)


def _pending_request(c, request_id):
    r = c.execute(text("SELECT * FROM admin_access_requests WHERE request_id = :i FOR UPDATE"),
                  {"i": request_id}).mappings().first()
    if r is None:
        raise HTTPException(404, f"unknown access request {request_id}")
    if r["status"] != "pending":
        raise HTTPException(409, f"access request {request_id} is already {r['status']}")
    return r


@router.post("/api/admin/access-requests/{request_id}/approve", response_model=s.AccessDecision,
             responses={**s.NOT_FOUND, **s.AUTH, **s.CONFLICT}, summary="Approve: creates the ward-officer account")
def approve_access_request(request_id: int, admin: dict = Depends(ADMIN_ONLY)):
    """Creates a ward_officer for the requested ward and returns a temporary password ONCE.
    Pass it to the officer; they sign in with POST /api/admin/login."""
    password = auth.temporary_password()
    with get_engine().begin() as c:
        r = _pending_request(c, request_id)
        if c.execute(text("SELECT 1 FROM admin_users WHERE email = :e"), {"e": r["email"]}).first():
            raise HTTPException(409, f"{r['email']} already has an account")
        new_id = c.execute(text(
            "INSERT INTO admin_users (email, name, designation, role, ward_codes, password_hash) "
            "VALUES (:e, :n, :d, 'ward_officer', ARRAY[:w], :h) RETURNING admin_id::text"),
            {"e": r["email"], "n": r["name"], "d": r["designation"], "w": r["ward_code"],
             "h": auth.hash_password(password)}).scalar_one()
        c.execute(text("UPDATE admin_access_requests SET status = 'approved', decided_at = now(), "
                       "decided_by = CAST(:by AS uuid), admin_id = CAST(:a AS uuid) WHERE request_id = :i"),
                  {"by": admin["admin_id"], "a": new_id, "i": request_id})
    return {"request_id": request_id, "status": "approved", "email": r["email"], "admin_id": new_id,
            "temporary_password": password}


@router.post("/api/admin/access-requests/{request_id}/reject", response_model=s.AccessDecision,
             responses={**s.NOT_FOUND, **s.AUTH, **s.CONFLICT}, summary="Reject an access request")
def reject_access_request(request_id: int, req: s.RejectReq, admin: dict = Depends(ADMIN_ONLY)):
    with get_engine().begin() as c:
        r = _pending_request(c, request_id)
        c.execute(text("UPDATE admin_access_requests SET status = 'rejected', decided_at = now(), "
                       "decided_by = CAST(:by AS uuid), decision_note = :n WHERE request_id = :i"),
                  {"by": admin["admin_id"], "n": req.reason.strip(), "i": request_id})
    return {"request_id": request_id, "status": "rejected", "email": r["email"], "admin_id": None,
            "temporary_password": None}


# ── Session ─────────────────────────────────────────────────────────────────
_DUMMY_HASH = auth.hash_password("not-a-real-password")  # equalises timing for unknown emails


@router.post("/api/admin/login", response_model=s.AdminSession, responses={401: s.AUTH[401]},
             summary="Sign in (email + password) -> bearer token")
def login(req: s.LoginReq):
    """Returns a session token valid for ADMIN_SESSION_HOURS (default 12). Wrong email or password -> 401."""
    u = rows("SELECT admin_id::text AS admin_id, role, ward_codes, password_hash FROM admin_users "
             "WHERE email = %(e)s AND active", e=req.email.strip().lower())
    ok = auth.verify_password(req.password, u[0]["password_hash"] if u else _DUMMY_HASH)
    if not (u and ok):
        raise auth.unauthorized("invalid email or password")
    token = auth.new_token(auth.ADMIN_PREFIX)
    with get_engine().begin() as c:
        c.execute(text("DELETE FROM admin_sessions WHERE admin_id = CAST(:a AS uuid) AND expires_at <= now()"),
                  {"a": u[0]["admin_id"]})
        exp = c.execute(text("INSERT INTO admin_sessions (token_hash, admin_id, expires_at) "
                             "VALUES (:h, CAST(:a AS uuid), now() + make_interval(hours => :hrs)) RETURNING expires_at"),
                        {"h": auth.token_hash(token), "a": u[0]["admin_id"], "hrs": auth.session_hours()}).scalar_one()
    role = u[0]["role"]
    return {"token": token, "role": role, "ward_codes": [] if role == "admin" else u[0]["ward_codes"], "expires_at": exp}


@router.post("/api/admin/logout", status_code=204, responses={401: s.AUTH[401]}, summary="End this session")
def logout(admin: dict = Depends(ANY_ADMIN)):
    with get_engine().begin() as c:
        c.execute(text("DELETE FROM admin_sessions WHERE token_hash = :h"), {"h": admin["token_hash"]})
    return Response(status_code=204)


@router.get("/api/admin/me", response_model=s.AdminMe, responses={401: s.AUTH[401]}, summary="The signed-in officer")
def admin_me(admin: dict = Depends(ANY_ADMIN)):
    return {"admin_id": admin["admin_id"], "email": admin["email"], "name": admin["name"],
            "designation": admin["designation"], "role": admin["role"],
            "ward_codes": [] if admin["role"] == "admin" else admin["ward_codes"],
            "session_expires_at": admin["expires_at"]}


# ── Dashboard ───────────────────────────────────────────────────────────────
@router.get("/api/admin/summary", response_model=s.AdminSummary, responses=s.AUTH, summary="Dashboard tiles")
def summary(ward: Optional[str] = Query(None, description="Ward code (K/W or K-W); default: all your wards"),
            admin: dict = Depends(ANY_ADMIN)):
    """reports_by_status, new_today (IST), overdue_sla (open and past sla_due_at), median_hours_to_resolve
    (created -> first resolved), rupees_held_inr (bills of reports in payment_held, each once), flags_awaiting_reply."""
    wards = auth.ward_scope(admin, ward)
    p = scope_params(wards) | {"open": tuple(sorted(lc.OPEN)), "tz": IST_TZ}
    by = {st: 0 for st in lc.STATUSES}
    for r in rows(f"SELECT cr.status, count(*) AS n {REPORT_FROM} WHERE {IN_SCOPE} GROUP BY cr.status", **p):
        by[r["status"]] = r["n"]
    t = one(f"SELECT count(*) FILTER (WHERE (cr.created_at AT TIME ZONE %(tz)s)::date = (now() AT TIME ZONE %(tz)s)::date) AS new_today, "
            f"count(*) FILTER (WHERE cr.status IN %(open)s AND {SLA_DUE} < now()) AS overdue_sla, "
            f"percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM cr.resolved_at - cr.created_at) / 3600) "
            f"  FILTER (WHERE cr.resolved_at IS NOT NULL) AS median_hours_to_resolve "
            f"{REPORT_FROM} WHERE {IN_SCOPE}", "summary", **p)
    held = one(f"SELECT COALESCE(sum(q.rupees_at_stake), 0)::bigint AS inr FROM flagged_queue q WHERE q.work_order_id IN "
               f"(SELECT f.work_order_id {REPORT_FROM} JOIN flags f ON f.flag_id = cr.flag_id "
               f" WHERE cr.status = 'payment_held' AND {IN_SCOPE})", "summary", **p)["inr"]
    awaiting = one("SELECT count(*) AS n FROM flags f WHERE (%(all)s OR f.ward_code IN %(wards)s) "
                   "AND NOT EXISTS (SELECT 1 FROM flag_replies fr WHERE fr.flag_id = f.flag_id)", "summary", **p)["n"]
    mh = t["median_hours_to_resolve"]
    return {"ward_codes": wards, "reports_by_status": by, "new_today": t["new_today"], "overdue_sla": t["overdue_sla"],
            "median_hours_to_resolve": None if mh is None else round(mh, 1), "rupees_held_inr": held,
            "flags_awaiting_reply": awaiting}


SORTS = {"newest": "cr.created_at DESC, cr.id DESC", "oldest": "cr.created_at, cr.id",
         "sla_due": f"{SLA_DUE} NULLS LAST, cr.id"}


@router.get("/api/admin/reports", response_model=s.ReportPage, responses=s.AUTH, summary="Report queue (paged cards)")
def list_reports(request: Request,
                 ward: Optional[str] = Query(None, description="Ward code; default: all your wards"),
                 status: Optional[s.ReportStatus] = None, kind: Optional[s.ReportKind] = None,
                 issue_type: Optional[s.IssueType] = None,
                 q: Optional[str] = Query(None, max_length=200, description="Report id, road name, landmark or text"),
                 sort: s.AdminSort = "newest", page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                 admin: dict = Depends(ANY_ADMIN)):
    """Cards: id, created_at, age_hours, sla_due_at, status, issue_type, road, flag, first photo, citizen pseudonym.
    Never a phone number."""
    p = scope_params(auth.ward_scope(admin, ward)) | {
        "st": status, "k": kind, "it": issue_type, "q": f"%{q.strip()}%" if q and q.strip() else None,
        "lim": page_size, "off": (page - 1) * page_size}
    where = (f"WHERE {IN_SCOPE} AND (%(st)s IS NULL OR cr.status = %(st)s) AND (%(k)s IS NULL OR cr.kind = %(k)s) "
             f"AND (%(it)s IS NULL OR cr.issue_type = %(it)s) AND (%(q)s IS NULL OR cr.id::text ILIKE %(q)s "
             f"OR rd.road_name ILIKE %(q)s OR cr.landmark ILIKE %(q)s OR cr.text ILIKE %(q)s)")
    total = one(f"SELECT count(*) AS n {REPORT_FROM} {where}", "reports", **p)["n"]
    rs = rows(f"SELECT cr.id, cr.created_at, extract(epoch FROM now() - cr.created_at) / 3600 AS age_hours, "
              f"{SLA_DUE} AS sla_due_at, cr.status, cr.kind, cr.issue_type, cr.road_id, rd.road_name, rd.ward_code, "
              f"rd.under_dlp, f.flag_id, f.rupees_at_stake, COALESCE(ci.display_name, 'Anonymous') AS citizen, "
              f"ph.photo_id, ph.storage, ph.storage_path {REPORT_FROM} "
              f"LEFT JOIN flags f ON f.flag_id = cr.flag_id LEFT JOIN citizens ci ON ci.citizen_id = cr.citizen_id "
              f"LEFT JOIN LATERAL (SELECT p.* FROM citizen_report_photos crp JOIN photos p USING (photo_id) "
              f"  WHERE crp.report_id = cr.id ORDER BY crp.position LIMIT 1) ph ON true "
              f"{where} ORDER BY {SORTS[sort]} LIMIT %(lim)s OFFSET %(off)s", **p)
    items = [{"id": r["id"], "created_at": r["created_at"], "age_hours": round(r["age_hours"], 1),
              "sla_due_at": r["sla_due_at"], "status": r["status"], "kind": r["kind"], "issue_type": r["issue_type"],
              "road": {k: r[k] for k in ("road_id", "road_name", "ward_code", "under_dlp")} if r["road_id"] else None,
              "flag": {"flag_id": r["flag_id"], "rupees_at_stake": r["rupees_at_stake"]} if r["flag_id"] else None,
              "photo_url": first_photo_url(r, request), "citizen": r["citizen"]} for r in rs]
    return {"items": items, "page": page, "page_size": page_size, "total": total}


FLAG_SELECT = ("SELECT f.flag_id, f.tier, f.detector, f.status_label, f.ward_code, f.road_id, r.road_name, f.work_order_id, "
               "f.contractor_id, c.contractor_name, f.rupees_at_stake, f.rule_text, COALESCE(rep.n, 0) AS replies_count, "
               "rep.last_at AS last_reply_at FROM flags f JOIN roads r ON r.road_id = f.road_id "
               "JOIN contractors c ON c.contractor_id = f.contractor_id "
               "LEFT JOIN (SELECT flag_id, count(*) AS n, max(created_at) AS last_at FROM flag_replies GROUP BY flag_id) rep "
               "ON rep.flag_id = f.flag_id ")


def report_detail(report_id, request):
    """CitizenReport + what an officer needs to act: citizen pseudonym, confirm photos, flags, work orders,
    duplicate candidates, notices and the statuses PATCH accepts next."""
    rep = build_report(report_id, request)
    x = one("SELECT cr.kind, cr.road_id, cr.issue_type, cr.status, cr.flag_id, cr.linked_work_order_id, "
            "cr.location_lat, cr.location_lon, rd.under_dlp, COALESCE(ci.display_name, 'Anonymous') AS citizen "
            "FROM citizen_reports cr LEFT JOIN roads rd ON rd.road_id = cr.road_id "
            "LEFT JOIN citizens ci ON ci.citizen_id = cr.citizen_id WHERE cr.id = %(i)s", f"report {report_id}", i=report_id)
    confirm_ids = [pid for e in rep["events"] if e["event_type"] == "confirm" for pid in e["photo_ids"]]
    confirm_photos = rows("SELECT photo_id, storage, storage_path, width, height FROM photos WHERE photo_id IN %(ids)s",
                          ids=tuple(confirm_ids)) if confirm_ids else []
    order = {pid: i for i, pid in enumerate(confirm_ids)}
    flags = rows(FLAG_SELECT + "WHERE f.road_id = %(r)s OR f.flag_id = %(f)s "
                 "ORDER BY (f.flag_id = %(f)s) DESC, f.tier, f.rupees_at_stake DESC, f.flag_id",
                 r=x["road_id"] or "", f=x["flag_id"] or "")
    wos = rows("SELECT wo.work_order_id, wo.contractor_id, c.contractor_name, wo.work_type, wo.repair_method, wo.cost_inr, "
               "wo.completed_at, wo.sla_met, wo.reopened_within_30d, (wo.work_order_id = %(l)s) AS linked "
               "FROM work_orders wo JOIN contractors c USING (contractor_id) WHERE wo.road_id = %(r)s "
               "ORDER BY (wo.work_order_id = %(l)s) DESC, wo.completed_at DESC NULLS LAST, wo.work_order_id DESC",
               r=x["road_id"] or "", l=x["linked_work_order_id"] or "")
    dups = rows("SELECT o.id, o.created_at, o.status, o.issue_type, o.road_id, "
                "CASE WHEN %(lat)s::float8 IS NOT NULL AND o.location_lat IS NOT NULL "
                "  THEN round(approx_m(%(lat)s, %(lon)s, o.location_lat, o.location_lon)::numeric, 1) END AS distance_m, "
                "CASE WHEN o.road_id = %(r)s AND o.issue_type IS NOT DISTINCT FROM %(it)s "
                "  AND abs(extract(epoch FROM o.created_at - me.created_at)) <= 7 * 86400 "
                "  THEN 'same_road_and_issue_7d' ELSE 'within_200m' END AS reason "
                "FROM citizen_reports o, citizen_reports me WHERE me.id = %(i)s AND o.id <> me.id "
                "AND o.status IN %(open)s AND ("
                " (o.road_id = %(r)s AND o.issue_type IS NOT DISTINCT FROM %(it)s "
                "  AND abs(extract(epoch FROM o.created_at - me.created_at)) <= 7 * 86400) "
                " OR (%(lat)s::float8 IS NOT NULL AND o.location_lat IS NOT NULL "
                "     AND approx_m(%(lat)s, %(lon)s, o.location_lat, o.location_lon) <= 200)) "
                "ORDER BY o.created_at, o.id LIMIT 20",
                i=report_id, r=x["road_id"] or "", it=x["issue_type"], lat=x["location_lat"], lon=x["location_lon"],
                open=tuple(sorted(lc.OPEN)))
    return {**rep, "citizen": x["citizen"],
            "confirm_photos": [{"photo_id": p["photo_id"], "width": p["width"], "height": p["height"],
                                "photo_url": public_url(p["storage"], p["storage_path"], p["photo_id"], request)}
                               for p in sorted(confirm_photos, key=lambda p: order[p["photo_id"]])],
            "flags": flags, "work_orders": wos, "duplicate_candidates": dups, "notices": notices_for(report_id),
            "allowed_next": lc.allowed_next(x["status"], hold_eligible(x))}


def notices_for(report_id):
    return [n | {"delivery": "recorded"} for n in rows(
        "SELECT n.id, n.report_id, n.channel, n.flag_id, n.work_order_id, n.contractor_id, c.contractor_name, n.message, "
        "n.generated_by, a.name AS sent_by, n.created_at FROM contractor_notices n "
        "JOIN admin_users a ON a.admin_id = n.sent_by LEFT JOIN contractors c ON c.contractor_id = n.contractor_id "
        "WHERE n.report_id = %(i)s ORDER BY n.created_at, n.id", i=report_id)]


@router.get("/api/admin/reports/{report_id}", response_model=s.AdminReportDetail,
            responses={**s.NOT_FOUND, **s.AUTH}, summary="Full report for triage")
def get_report(report_id: int, request: Request, admin: dict = Depends(ANY_ADMIN)):
    """Events, photos (incl. confirmation photos), location, matched flags and work orders, duplicate candidates
    (same road + issue within 7 days, or within 200 m), notices sent, and allowed_next statuses."""
    check_report_access(admin, report_id)
    return report_detail(report_id, request)


def _as_ist(d: Optional[datetime]) -> Optional[datetime]:
    return d if d is None or d.tzinfo else d.replace(tzinfo=s.IST)


@router.patch("/api/admin/reports/{report_id}", response_model=s.AdminReportDetail,
              responses={**s.NOT_FOUND, **s.AUTH}, summary="Triage: change status, add a note, set repair due date")
def patch_report(report_id: int, req: s.ReportPatchReq, request: Request, admin: dict = Depends(ANY_ADMIN)):
    """Validates the transition (422 lists allowed_next). rejected needs rejection_reason; duplicate needs
    duplicate_of (follows a chain to the original). Every change writes a history event."""
    check_report_access(admin, report_id)
    if req.rejection_reason and req.status != "rejected":
        raise invalid("rejection_reason", "rejection_reason is only used with status=rejected")
    if req.duplicate_of is not None and req.status != "duplicate":
        raise invalid("duplicate_of", "duplicate_of is only used with status=duplicate")
    if req.status == "rejected" and not req.rejection_reason:
        raise invalid("rejection_reason", "rejection_reason is required with status=rejected")
    if req.status == "duplicate" and req.duplicate_of is None:
        raise invalid("duplicate_of", "duplicate_of is required with status=duplicate")
    with get_engine().begin() as c:
        r = c.execute(text("SELECT cr.id, cr.kind, cr.status, cr.road_id, cr.issue_type, rd.under_dlp FROM citizen_reports cr "
                           "LEFT JOIN roads rd ON rd.road_id = cr.road_id WHERE cr.id = :i FOR UPDATE OF cr"),
                        {"i": report_id}).mappings().one()
        sets, params = [], {"i": report_id}
        if req.status:
            err = lc.transition_error(r["status"], req.status, hold_eligible(r))
            if err:
                raise invalid("status", err)
            sets += ["status = :st", "status_updated_at = now()"]
            params["st"] = req.status
            if req.status == "resolved":
                sets.append("resolved_at = COALESCE(resolved_at, now())")
            if req.status == "rejected":
                sets.append("rejection_reason = :rr")
                params["rr"] = req.rejection_reason.strip()
            if req.status == "duplicate":
                root, seen = req.duplicate_of, {report_id}
                while True:
                    t = c.execute(text("SELECT id, duplicate_of, status FROM citizen_reports WHERE id = :d"),
                                  {"d": root}).mappings().first()
                    if t is None:
                        raise invalid("duplicate_of", f"unknown report {root}")
                    if t["id"] in seen:
                        raise invalid("duplicate_of", "a report cannot be a duplicate of itself")
                    seen.add(t["id"])
                    if t["status"] != "duplicate" or t["duplicate_of"] is None:
                        break
                    root = t["duplicate_of"]
                sets.append("duplicate_of = :dup")
                params["dup"] = root
        if "repair_due_at" in req.model_fields_set:
            sets.append("repair_due_at = :due")
            params["due"] = _as_ist(req.repair_due_at)
        if sets:
            c.execute(text(f"UPDATE citizen_reports SET {', '.join(sets)} WHERE id = :i"), params)
        meta = {}
        if "dup" in params:
            meta["duplicate_of"] = params["dup"]
        if "rr" in params:
            meta["rejection_reason"] = params["rr"]
        if "repair_due_at" in req.model_fields_set:
            meta["repair_due_at"] = params["due"]
        etype = "duplicate" if req.status == "duplicate" else "status_change" if req.status else "note"
        add_event(c, report_id, "admin", etype, r["status"], req.status or r["status"], note=req.note,
                  admin_id=admin["admin_id"], meta=meta)
    return report_detail(report_id, request)


NOTICE_TEMPLATE = ("Ward office notice regarding citizen report #{rid} on {road} ({road_id}), ward {ward}: "
                   "{issue}. Work order {wo} (contractor {contractor}) is linked to this location. "
                   "Please inspect and rectify, and record your reply with the ward office.")


@router.post("/api/admin/reports/{report_id}/notify-contractor", status_code=201, response_model=s.ContractorNotice,
             responses={**s.NOT_FOUND, **s.AUTH, **s.CONFLICT}, summary="Record a notice to the responsible contractor")
def notify_contractor(report_id: int, req: s.NotifyReq, admin: dict = Depends(ANY_ADMIN)):
    """Contractor = the contractor of the report's flagged bill; without a flag, the linked work order's contractor,
    else the road's latest surface-repair contractor, else its latest contractor. Without `message`, the notice is drafted from the report's flag via the
    draft-notice logic (Claude, template fallback). The notice is RECORDED (delivery: recorded), not sent. Moves the
    report to contractor_notified when that transition is allowed; closed reports -> 409."""
    check_report_access(admin, report_id)
    x = one("SELECT cr.status, cr.road_id, cr.flag_id, cr.issue_type, cr.linked_work_order_id, rd.road_name, rd.ward_code "
            "FROM citizen_reports cr LEFT JOIN roads rd ON rd.road_id = cr.road_id WHERE cr.id = %(i)s",
            f"report {report_id}", i=report_id)
    if x["status"] in lc.CLOSED:
        raise HTTPException(409, f"report is {x['status']}; reopen it before notifying the contractor")
    if not x["road_id"]:
        raise invalid("report", "report has no matched road; set one before notifying a contractor")
    if x["flag_id"]:  # the notice concerns the flagged bill, so it goes to that bill's contractor
        wo = rows("SELECT wo.work_order_id, wo.contractor_id, c.contractor_name FROM flags f "
                  "JOIN work_orders wo ON wo.work_order_id = f.work_order_id JOIN contractors c ON c.contractor_id = wo.contractor_id "
                  "WHERE f.flag_id = %(f)s", f=x["flag_id"])
    else:
        wo = rows("SELECT wo.work_order_id, wo.contractor_id, c.contractor_name FROM work_orders wo "
                  "JOIN contractors c USING (contractor_id) WHERE wo.road_id = %(r)s "
                  "ORDER BY (wo.work_order_id = %(l)s) DESC, (wo.work_type IN %(sw)s) DESC, "
                  "wo.completed_at DESC NULLS LAST, wo.work_order_id DESC LIMIT 1",
                  r=x["road_id"], l=x["linked_work_order_id"] or "", sw=SURFACE_WORK)
    if not wo:
        raise invalid("report", f"no contractor has billed work on road {x['road_id']}")
    wo = wo[0]
    if req.message:
        message, by = req.message.strip(), "officer"
    elif x["flag_id"]:  # slow path (Claude); runs before the transaction so no row lock is held meanwhile
        d = draft_notice(s.DraftNoticeReq(flag_id=x["flag_id"], language=req.language, doc_type="defect_notice"))
        message, by = f"{d['title']}\n\n{d['body']}", d["generated_by"]
    else:
        message, by = NOTICE_TEMPLATE.format(rid=report_id, road=x["road_name"], road_id=x["road_id"],
                                             ward=x["ward_code"], issue=x["issue_type"] or "reported problem",
                                             wo=wo["work_order_id"], contractor=wo["contractor_name"]), "template"
    with get_engine().begin() as c:
        cur = c.execute(text("SELECT status FROM citizen_reports WHERE id = :i FOR UPDATE"), {"i": report_id}).scalar_one()
        if cur in lc.CLOSED:
            raise HTTPException(409, f"report is {cur}; reopen it before notifying the contractor")
        nid = c.execute(text("INSERT INTO contractor_notices (report_id, flag_id, work_order_id, contractor_id, channel, "
                             "message, generated_by, sent_by) VALUES (:r, :f, :w, :c, :ch, :m, :g, CAST(:a AS uuid)) "
                             "RETURNING id"),
                        {"r": report_id, "f": x["flag_id"], "w": wo["work_order_id"], "c": wo["contractor_id"],
                         "ch": req.channel, "m": message, "g": by, "a": admin["admin_id"]}).scalar_one()
        to = "contractor_notified" if "contractor_notified" in lc.TRANSITIONS.get(cur, ()) else cur
        if to != cur:
            c.execute(text("UPDATE citizen_reports SET status = :t, status_updated_at = now() WHERE id = :i"),
                      {"t": to, "i": report_id})
        add_event(c, report_id, "admin", "contractor_notified", cur, to, admin_id=admin["admin_id"],
                  meta={"notice_id": nid, "channel": req.channel, "contractor_id": wo["contractor_id"]})
    return next(n for n in notices_for(report_id) if n["id"] == nid)


@router.get("/api/admin/flags", response_model=s.FlagPage, responses=s.AUTH, summary="Flags in your wards (awaiting reply)")
def list_flags(ward: Optional[str] = Query(None), awaiting_reply: Optional[bool] = Query(
                   None, description="true: only flags with no Right-of-Reply yet; false: only replied flags"),
               page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
               admin: dict = Depends(ANY_ADMIN)):
    """Ranked by rupees at stake. Reply with POST /api/flags/{flag_id}/replies (officer token)."""
    p = scope_params(auth.ward_scope(admin, ward)) | {"aw": awaiting_reply, "lim": page_size, "off": (page - 1) * page_size}
    where = ("WHERE (%(all)s OR f.ward_code IN %(wards)s) AND (%(aw)s IS NULL OR "
             "(%(aw)s AND rep.n IS NULL) OR (NOT %(aw)s AND rep.n IS NOT NULL)) ")
    total = one("SELECT count(*) AS n FROM flags f LEFT JOIN (SELECT flag_id, count(*) AS n FROM flag_replies "
                "GROUP BY flag_id) rep ON rep.flag_id = f.flag_id " + where, "flags", **p)["n"]
    items = rows(FLAG_SELECT + where + "ORDER BY f.rupees_at_stake DESC, f.flag_id LIMIT %(lim)s OFFSET %(off)s", **p)
    return {"items": items, "page": page, "page_size": page_size, "total": total}
