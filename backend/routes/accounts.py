"""Unified sign-in for the frontend: one email + password account; the role decides ward-office access.

- POST /api/auth/signup creates a **citizen** account (officers are created by approving an access request, or by
  backend/admin_cli.py), returning a citizen token.
- POST /api/auth/login checks officer/admin accounts first, then citizen accounts, and returns that account's token
  and role. Officer tokens (`adm_...`) expire after ADMIN_SESSION_HOURS; citizen tokens (`cit_...`) do not.

The anonymous POST /api/citizens and the officer-only POST /api/admin/login stay available."""
from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend import auth
from backend import schemas as s
from backend.database import get_engine, rows
from backend.routes.admin import _DUMMY_HASH, start_admin_session

router = APIRouter(tags=["Accounts"])


@router.post("/api/auth/signup", status_code=201, response_model=s.AuthSession, responses=s.CONFLICT,
             summary="Create a citizen account (email + password) -> citizen token")
def signup(req: s.SignupReq):
    """409 if the email already has a citizen or officer account. Officers do not sign up here: they ask via
    POST /api/admin/access-requests."""
    email = req.email.strip().lower()
    if rows("SELECT 1 FROM admin_users WHERE email = %(e)s UNION ALL SELECT 1 FROM citizens WHERE email = %(e)s", e=email):
        raise HTTPException(409, "this email already has an account; sign in via POST /api/auth/login")
    token = auth.new_token(auth.CITIZEN_PREFIX)
    try:
        with get_engine().begin() as c:
            cid = c.execute(text("INSERT INTO citizens (display_name, token_hash, email, password_hash) "
                                 "VALUES (:n, :h, :e, :p) RETURNING citizen_id::text"),
                            {"n": req.name.strip(), "h": auth.token_hash(token), "e": email,
                             "p": auth.hash_password(req.password)}).scalar_one()
    except IntegrityError:  # concurrent signup with the same email
        raise HTTPException(409, "this email already has an account; sign in via POST /api/auth/login")
    return {"token": token, "role": "citizen", "ward_codes": [], "name": req.name.strip(), "email": email,
            "expires_at": None, "citizen_id": cid, "admin_id": None}


@router.post("/api/auth/login", response_model=s.AuthSession, responses={401: s.AUTH[401]},
             summary="Sign in (officer, admin or citizen) -> token + role")
def login(req: s.LoginReq):
    """Officer/admin accounts are checked first, then citizen accounts. Wrong email or password -> 401."""
    email = req.email.strip().lower()
    a = rows("SELECT admin_id::text AS admin_id, name, role, ward_codes, password_hash FROM admin_users "
             "WHERE email = %(e)s AND active", e=email)
    if a:
        if not auth.verify_password(req.password, a[0]["password_hash"]):
            raise auth.unauthorized("invalid email or password")
        token, exp = start_admin_session(a[0]["admin_id"])
        role = a[0]["role"]
        return {"token": token, "role": role, "ward_codes": [] if role == "admin" else a[0]["ward_codes"],
                "name": a[0]["name"], "email": email, "expires_at": exp, "citizen_id": None, "admin_id": a[0]["admin_id"]}
    c = rows("SELECT citizen_id::text AS citizen_id, display_name, password_hash FROM citizens WHERE email = %(e)s", e=email)
    ok = auth.verify_password(req.password, c[0]["password_hash"] if c else _DUMMY_HASH)
    if not (c and ok):
        raise auth.unauthorized("invalid email or password")
    token = auth.new_token(auth.CITIZEN_PREFIX)
    with get_engine().begin() as conn:
        conn.execute(text("INSERT INTO citizen_sessions (token_hash, citizen_id) VALUES (:h, CAST(:c AS uuid))"),
                     {"h": auth.token_hash(token), "c": c[0]["citizen_id"]})
    return {"token": token, "role": "citizen", "ward_codes": [], "name": c[0]["display_name"], "email": email,
            "expires_at": None, "citizen_id": c[0]["citizen_id"], "admin_id": None}
