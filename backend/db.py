"""Shared Supabase/Postgres connection helper."""
import os, sqlalchemy as sa


def engine():
    url = os.environ["DATABASE_URL"]
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):  # pin a driver; SQLAlchemy 2.1 defaults to psycopg 3
        try:
            import psycopg2  # noqa: F401
            url = "postgresql+psycopg2://" + url[len("postgresql://"):]
        except ImportError:
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return sa.create_engine(url, pool_pre_ping=True)
