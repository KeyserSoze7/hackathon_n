"""Photo uploads for the citizen report form. The image type is sniffed from the bytes, EXIF time/GPS are read
into the photos row, then the image is re-encoded without any metadata before it is stored."""
import io
import uuid
from datetime import datetime

import pillow_heif
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from PIL import Image, ImageOps
from sqlalchemy import text

from backend import photos
from backend import schemas as s
from backend.database import get_engine, one

router = APIRouter(tags=["View 4: Citizen Layer"])
pillow_heif.register_heif_opener()
Image.MAX_IMAGE_PIXELS = 60_000_000
MAX_BYTES = 8 * 1024 * 1024
# detected Pillow format -> (stored format, stored content type, original content type, save options)
FORMATS = {"JPEG": ("JPEG", "image/jpeg", "image/jpeg", {"quality": 88}),
           "PNG": ("PNG", "image/png", "image/png", {}),
           "WEBP": ("WEBP", "image/webp", "image/webp", {"quality": 85}),
           "HEIF": ("JPEG", "image/jpeg", "image/heic", {"quality": 85})}  # browsers can't show HEIC
EXT = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
TOO_MANY_PIXELS = HTTPException(413, "image has too many pixels")
NOT_IMAGE = HTTPException(415, "photo must be a valid JPEG, PNG, WebP or HEIC image")


def _taken_at(exif):
    raw = exif.get_ifd(0x8769).get(36867) or exif.get(306)  # DateTimeOriginal, else DateTime
    try:
        return datetime.strptime(str(raw).strip("\x00 "), "%Y:%m:%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


def _gps(exif):
    g = exif.get_ifd(0x8825)

    def deg(value, ref, neg, limit):
        try:
            d, m, sec = (float(x) for x in value)
        except (TypeError, ValueError, ZeroDivisionError):
            return None
        v = (d + m / 60 + sec / 3600) * (-1 if str(ref).strip("\x00 ").upper() == neg else 1)
        return v if abs(v) <= limit else None  # also rejects nan from 0/0 rationals

    lat, lon = deg(g.get(2), g.get(1), "S", 90), deg(g.get(4), g.get(3), "W", 180)
    return (lat, lon) if lat is not None and lon is not None else (None, None)


def _decode(data: bytes):
    """bytes -> (detected format, upright image, {taken_at, exif_lat, exif_lon}). 415 / 413 on bad input."""
    try:
        img = Image.open(io.BytesIO(data))
        fmt = img.format
        if fmt not in FORMATS:
            raise NOT_IMAGE
        if img.width * img.height > Image.MAX_IMAGE_PIXELS:  # Pillow only warns between 1x and 2x the limit
            raise TOO_MANY_PIXELS
        img.load()
        exif = img.getexif()
        lat, lon = _gps(exif)
        meta = {"taken_at": _taken_at(exif), "exif_lat": lat, "exif_lon": lon}
        return fmt, ImageOps.exif_transpose(img), meta
    except HTTPException:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise TOO_MANY_PIXELS
    except Exception:  # not an image, truncated, corrupt
        raise NOT_IMAGE


def _encode(img, fmt, opts) -> bytes:
    """Re-encode with no metadata at all (EXIF/GPS, ICC, XMP, text chunks)."""
    if fmt == "JPEG" and img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    elif fmt == "WEBP" and img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() or "transparency" in img.info else "RGB")
    elif fmt == "PNG" and img.mode == "P":
        img = img.convert("RGBA")  # palette transparency lives in info, which is dropped below
    img.info = {}
    buf = io.BytesIO()
    img.save(buf, fmt, exif=b"", **opts)
    return buf.getvalue()


@router.post("/api/uploads/photo", status_code=201, response_model=s.PhotoUpload,
             responses={413: {"model": s.Error}, 415: {"model": s.Error}},
             summary="Upload a report photo (JPEG/PNG/WebP/HEIC, max 8 MB; EXIF read, then stripped)")
def upload_photo(request: Request, file: UploadFile = File(...)):
    data = file.file.read(MAX_BYTES + 1)  # hard cap, whatever Content-Length claims
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "photo is larger than 8 MB")
    src, img, meta = _decode(data)
    fmt, content_type, original_type, opts = FORMATS[src]
    out = _encode(img, fmt, opts)
    if len(out) > MAX_BYTES:
        raise HTTPException(413, "photo is larger than 8 MB after re-encoding")
    photo_id = uuid.uuid4().hex
    key = f"{photo_id}.{EXT[fmt]}"
    storage = photos.store(key, out, content_type)
    with get_engine().begin() as c:
        c.execute(text("INSERT INTO photos (photo_id, storage, content_type, original_content_type, size_bytes, "
                       "width, height, taken_at, exif_lat, exif_lon, storage_path) VALUES (:photo_id, :storage, "
                       ":content_type, :original_content_type, :size_bytes, :width, :height, :taken_at, :exif_lat, "
                       ":exif_lon, :storage_path)"),
                  {"photo_id": photo_id, "storage": storage, "content_type": content_type,
                   "original_content_type": original_type, "size_bytes": len(out), "width": img.width,
                   "height": img.height, "storage_path": key, **meta})
    return {"photo_id": photo_id, "photo_url": photos.public_url(storage, key, photo_id, request),
            "width": img.width, "height": img.height, **meta}


@router.get("/api/uploads/photo/{photo_id}", include_in_schema=True,
            responses={**s.NOT_FOUND, 200: {"content": {"image/jpeg": {}, "image/png": {}, "image/webp": {}},
                                            "description": "The photo bytes (local storage)"},
                       307: {"description": "Redirect to the Supabase Storage public URL"}},
            response_class=FileResponse, summary="Serve an uploaded report photo (metadata-free image bytes)")
def get_photo(photo_id: str, request: Request):
    p = one("SELECT storage, storage_path, content_type FROM photos WHERE photo_id = %(photo_id)s",
            "photo", photo_id=photo_id)
    if p["storage"] == "supabase":
        return RedirectResponse(photos.public_url(p["storage"], p["storage_path"], photo_id, request), 307)
    path = photos.local_path(p["storage_path"])
    if not path.is_file():
        raise HTTPException(404, "photo file missing")
    return FileResponse(path, media_type=p["content_type"],
                        headers={"Cache-Control": "public, max-age=31536000, immutable"})
