"""Create admin / ward-officer accounts from the command line (the first admin can't be approved by anyone).
Run from the repo root (DATABASE_URL from the environment or .env):
    python -m backend.admin_cli create-admin --email ops@example.org --name "Ops Admin"
    python -m backend.admin_cli create-admin --email ae.kw@example.org --name "AE K/W" --role ward_officer --ward K/W
The password is prompted (or read from ADMIN_PASSWORD for scripted setups). Re-running for an existing email
resets that account's password, role and wards.
"""
import argparse
import getpass
import os
import sys

from sqlalchemy import text

from backend import auth
from backend.database import get_engine, norm_ward, rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-admin", help="create or reset an admin / ward-officer account")
    c.add_argument("--email", required=True)
    c.add_argument("--name", required=True)
    c.add_argument("--designation")
    c.add_argument("--role", choices=["admin", "ward_officer"], default="admin")
    c.add_argument("--ward", action="append", default=[], help="ward code (repeatable); required for ward_officer")
    a = ap.parse_args(argv)

    email = a.email.strip().lower()
    wards = [norm_ward(w) for w in a.ward]
    if a.role == "ward_officer" and not wards:
        ap.error("--ward is required for --role ward_officer")
    if wards:
        known = {r["ward_code"] for r in rows("SELECT ward_code FROM wards WHERE ward_code IN %(w)s", w=tuple(wards))}
        if unknown := sorted(set(wards) - known):
            ap.error(f"unknown ward(s): {', '.join(unknown)}")
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Password (min 10 chars): ")
    if len(password) < 10:
        ap.error("password must be at least 10 characters")
    with get_engine().begin() as conn:
        admin_id = conn.execute(text(
            "INSERT INTO admin_users (email, name, designation, role, ward_codes, password_hash) "
            "VALUES (:e, :n, :d, :r, :w, :h) ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name, "
            "designation = EXCLUDED.designation, role = EXCLUDED.role, ward_codes = EXCLUDED.ward_codes, "
            "password_hash = EXCLUDED.password_hash, active = true RETURNING admin_id::text"),
            {"e": email, "n": a.name, "d": a.designation, "r": a.role, "w": wards,
             "h": auth.hash_password(password)}).scalar_one()
        conn.execute(text("DELETE FROM admin_sessions WHERE admin_id = CAST(:a AS uuid)"), {"a": admin_id})
    print(f"{a.role} {email} ready (admin_id {admin_id}). Sign in with POST /api/admin/login.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
