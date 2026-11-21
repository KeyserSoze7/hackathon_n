"""Shared Supabase/Postgres connection helper.

DATABASE_URL comes from the environment, or from a `.env` file at the repo root (see `.env.example`).
A variable already set in the environment wins over `.env`.
"""
import os, pathlib
import sqlalchemy as sa

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_env(path=ROOT / ".env"):
    """Minimal .env reader (KEY=VALUE lines, # comments, optional quotes). No extra dependency."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip().removeprefix("export ").strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        os.environ.setdefault(k, v)


load_env()


def engine():
    url = os.environ.get("DATABASE_URL", "")
    if not url or "<" in url or ">" in url:
        raise SystemExit("DATABASE_URL is not set: copy .env.example to .env at the repo root and fill in the "
                         "Supabase Session pooler URI (or export DATABASE_URL).")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):  # pin a driver; SQLAlchemy 2.1 defaults to psycopg 3
        try:
            import psycopg2  # noqa: F401
            url = "postgresql+psycopg2://" + url[len("postgresql://"):]
        except ImportError:
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return sa.create_engine(url, pool_pre_ping=True)
