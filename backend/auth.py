"""Bearer-token auth for citizens (anonymous accounts) and admins / ward officers (email + password).

Tokens are random (`cit_...` / `adm_...`) and returned once; the database keeps only their sha256.
Passwords are hashed with scrypt (stdlib). Citizen tokens do not expire; admin sessions last ADMIN_SESSION_HOURS
(default 12). Send `Authorization: Bearer <token>`.
"""
import base64
import hashlib
import hmac
import os
import secrets
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text

from backend.database import get_engine, norm_ward, rows

CITIZEN_PREFIX, ADMIN_PREFIX = "cit_", "adm_"
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1

citizen_bearer = HTTPBearer(auto_error=False, scheme_name="CitizenToken",
                            description="Token from POST /api/citizens (cit_...)")
admin_bearer = HTTPBearer(auto_error=False, scheme_name="AdminToken",
                          description="Token from POST /api/admin/login (adm_...)")


def session_hours() -> int:
    try:
        return max(1, int(os.environ.get("ADMIN_SESSION_HOURS", "12")))
    except ValueError:
        return 12


# ── primitives (pure; unit-tested) ──────────────────────────────────────────
def new_token(prefix: str) -> str:
    return prefix + secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    b64 = lambda b: base64.b64encode(b).decode()
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${b64(salt)}${b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, dk = stored.split("$")
        if algo != "scrypt":
            return False
        want = base64.b64decode(dk)
        got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                             dklen=len(want))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, want)


def temporary_password() -> str:
    """Shown once to the approving admin, who passes it on to the new ward officer."""
    return secrets.token_urlsafe(12)


# ── FastAPI dependencies ────────────────────────────────────────────────────
def unauthorized(msg: str) -> HTTPException:
    return HTTPException(401, msg, headers={"WWW-Authenticate": "Bearer"})


def optional_citizen(creds: Optional[HTTPAuthorizationCredentials] = Depends(citizen_bearer)) -> Optional[dict]:
    """None without an Authorization header; 401 if a token is sent but is not a valid citizen token."""
    if creds is None:
        return None
    tok = creds.credentials
    if not tok.startswith(CITIZEN_PREFIX):
        raise unauthorized("invalid citizen token")
    with get_engine().begin() as c:  # one statement: look up the token and record last_seen_at
        r = c.execute(text("UPDATE citizens SET last_seen_at = now() WHERE token_hash = :h "
                           "RETURNING citizen_id::text AS citizen_id, display_name, joined_at"),
                      {"h": token_hash(tok)}).mappings().first()
    if r is None:
        raise unauthorized("invalid citizen token")
    return dict(r)


def require_citizen(citizen: Optional[dict] = Depends(optional_citizen)) -> dict:
    if citizen is None:
        raise unauthorized("citizen token required (POST /api/citizens)")
    return citizen


def current_admin(creds: Optional[HTTPAuthorizationCredentials] = Depends(admin_bearer)) -> dict:
    if creds is None:
        raise unauthorized("admin token required (POST /api/admin/login)")
    tok = creds.credentials
    if not tok.startswith(ADMIN_PREFIX):
        raise unauthorized("invalid or expired admin token")
    r = rows("SELECT a.admin_id::text AS admin_id, a.email, a.name, a.designation, a.role, a.ward_codes, "
             "s.expires_at FROM admin_sessions s JOIN admin_users a USING (admin_id) "
             "WHERE s.token_hash = %(h)s AND s.expires_at > now() AND a.active", h=token_hash(tok))
    if not r:
        raise unauthorized("invalid or expired admin token")
    return r[0] | {"token_hash": token_hash(tok)}


def require_admin(*roles: str):
    """Dependency factory: any signed-in admin/ward officer, or only the given roles (403 otherwise)."""
    def dep(admin: dict = Depends(current_admin)) -> dict:
        if roles and admin["role"] not in roles:
            raise HTTPException(403, f"requires role: {', '.join(roles)}")
        return admin
    return dep


def ward_scope(admin: dict, ward: Optional[str] = None) -> Optional[list[str]]:
    """Wards this request may touch. None = every ward (admin without a filter).
    A ward officer asking for a ward outside their ward_codes gets 403."""
    w = norm_ward(ward) if ward else None
    if admin["role"] == "admin":
        return [w] if w else None
    allowed = list(admin["ward_codes"] or [])
    if w:
        if w not in allowed:
            raise HTTPException(403, f"ward {w} is outside your wards ({', '.join(allowed) or 'none'})")
        return [w]
    return allowed


def require_ward(admin: dict, ward_code: Optional[str]) -> None:
    """403 unless the account may act on this ward (admins may act anywhere)."""
    if admin["role"] != "admin" and ward_code not in (admin["ward_codes"] or []):
        raise HTTPException(403, f"ward {ward_code} is outside your wards")
