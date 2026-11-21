"""Photo storage: Supabase Storage over its S3 API (bucket `report-photos`, public), or local disk as a fallback.

Supabase is used when SUPABASE_S3_ACCESS_KEY_ID and SUPABASE_S3_SECRET_ACCESS_KEY are set (repo-root .env;
Supabase dashboard -> Project Settings -> Storage -> S3 access keys). The project ref and region are read from
DATABASE_URL unless SUPABASE_URL / SUPABASE_S3_REGION are given. Without keys, files go to UPLOAD_DIR and the API
serves them at GET /api/uploads/photo/{photo_id} (fine for local dev; files stay on that machine).
"""
import os
import pathlib
import re
from functools import lru_cache

import backend.database  # noqa: F401  (loads the repo-root .env)

BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "report-photos")
UPLOAD_DIR = pathlib.Path(os.environ.get("UPLOAD_DIR", pathlib.Path(__file__).resolve().parent.parent / "uploads"))


def _project():
    """(project_url, region) from env, else from the Supabase pooler DATABASE_URL (user postgres.<ref>@aws-N-<region>)."""
    url = os.environ.get("DATABASE_URL", "")
    ref = re.search(r"//postgres\.([a-z0-9]+)[:@]", url)
    region = re.search(r"@aws-\d+-([a-z0-9-]+)\.pooler\.supabase\.com", url)
    project_url = os.environ.get("SUPABASE_URL") or (f"https://{ref.group(1)}.supabase.co" if ref else None)
    return project_url, os.environ.get("SUPABASE_S3_REGION") or (region.group(1) if region else None)


def backend_name():
    keys = os.environ.get("SUPABASE_S3_ACCESS_KEY_ID") and os.environ.get("SUPABASE_S3_SECRET_ACCESS_KEY")
    return "supabase" if keys and _project()[0] else "local"


@lru_cache(maxsize=1)
def _s3():
    import boto3
    project_url, region = _project()
    return boto3.client("s3", endpoint_url=f"{project_url}/storage/v1/s3", region_name=region or "ap-southeast-1",
                        aws_access_key_id=os.environ["SUPABASE_S3_ACCESS_KEY_ID"],
                        aws_secret_access_key=os.environ["SUPABASE_S3_SECRET_ACCESS_KEY"])


def store(key: str, data: bytes, content_type: str) -> str:
    """Save bytes under `key` (no path separators). Returns the storage name recorded in photos.storage."""
    if "/" in key or "\\" in key or key.startswith("."):
        raise ValueError("bad storage key")
    name = backend_name()
    if name == "supabase":
        _s3().put_object(Bucket=BUCKET, Key=key, Body=data, ContentType=content_type,
                         CacheControl="public, max-age=31536000, immutable")
    else:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        (UPLOAD_DIR / key).write_bytes(data)
    return name


def local_path(storage_path: str) -> pathlib.Path:
    path = (UPLOAD_DIR / storage_path).resolve()
    if path.parent != UPLOAD_DIR.resolve():  # no traversal out of UPLOAD_DIR
        raise ValueError("bad storage path")
    return path


def public_url(storage: str, storage_path: str, photo_id: str, request) -> str:
    """Browser-loadable URL for a stored photo."""
    if storage == "supabase":
        return f"{_project()[0]}/storage/v1/object/public/{BUCKET}/{storage_path}"
    return str(request.url_for("get_photo", photo_id=photo_id))
