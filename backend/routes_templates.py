import asyncio
import base64
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends
from bson import ObjectId
from PIL import Image, ImageOps
from db import get_db
from helpers import now_utc, api_error
from security import require_admin, require_any

router = APIRouter(prefix="/api/templates", tags=["templates"])

MAX_LOGOS = 6
MAX_LOGO_BYTES = 2 * 1024 * 1024
STORED_LOGO_EDGE = 600
STORED_LOGO_BYTES = 150 * 1024
JPEG_QUALITIES = (85, 80, 75, 70, 65, 60)
ALLOWED_MIME = ("image/png", "image/jpeg", "image/webp")
INVALID_IMAGE = "Invalid image data."
_RUPA_PNG = Path(__file__).resolve().parent / "assets" / "rupa-sponsor.png"


def default_logos() -> List[Dict[str, Any]]:
    if not _RUPA_PNG.exists():
        return []
    data_url = "data:image/png;base64," + base64.b64encode(_RUPA_PNG.read_bytes()).decode()
    return [
        {"id": "rupa-foundation", "name": "rupa-foundation.png", "data_url": data_url, "order": 0},
    ]


def _encoded(image: Image.Image, fmt: str, **options: Any) -> bytes:
    buffer = BytesIO()
    image.save(buffer, fmt, **options)
    return buffer.getvalue()


def _stored_logo(raw: bytes) -> str:
    try:
        source = Image.open(BytesIO(raw))
        source.load()
    except Exception:
        raise api_error(400, "INVALID_IMAGE", INVALID_IMAGE)
    source_format = source.format
    if len(raw) <= STORED_LOGO_BYTES and max(source.size) <= STORED_LOGO_EDGE and source_format in ("PNG", "JPEG"):
        return f"data:image/{source_format.lower()};base64," + base64.b64encode(raw).decode()
    image = ImageOps.exif_transpose(source)
    image.thumbnail((STORED_LOGO_EDGE, STORED_LOGO_EDGE))
    rgba = image.convert("RGBA")
    flat = Image.new("RGB", rgba.size, "white")
    flat.paste(rgba, mask=rgba.getchannel("A"))
    jpeg = b""
    for quality in JPEG_QUALITIES:
        jpeg = _encoded(flat, "JPEG", quality=quality, optimize=True)
        if len(jpeg) <= STORED_LOGO_BYTES:
            break
    best, mime = jpeg, "image/jpeg"
    if source_format == "PNG":
        png = _encoded(rgba, "PNG", optimize=True)
        if len(png) < len(jpeg):
            best, mime = png, "image/png"
    if len(best) > STORED_LOGO_BYTES:
        raise api_error(400, "THIS_LOGO_IS_TOO_DETAILED_TO_STORE_AT_150_KB_USE_A_SIMPLER_I", 'This logo is too detailed to store at 150 KB. Use a simpler image.')
    return f"data:{mime};base64," + base64.b64encode(best).decode()


def _validate_logos(logos: Optional[List[dict]]) -> List[Dict[str, Any]]:
    if logos is not None and not isinstance(logos, list):
        raise api_error(400, "LOGOS_MUST_BE_A_LIST", 'Logos must be a list.')
    if len(logos or []) > MAX_LOGOS:
        raise api_error(400, "AT_MOST_SPONSOR_LOGOS", f'At most {MAX_LOGOS} sponsor logos.')
    out = []
    for lg in logos or []:
        data_url = lg.get("data_url") if isinstance(lg, dict) else None
        if not isinstance(data_url, str) or not data_url.startswith("data:") or "," not in data_url:
            raise api_error(400, "INVALID_IMAGE", INVALID_IMAGE)
        header, b64 = data_url.split(",", 1)
        mime = header.split(";")[0].replace("data:", "")
        if mime not in ALLOWED_MIME:
            raise api_error(400, "UNSUPPORTED_IMAGE_TYPE_USE_PNG_JPEG_WEBP", f'Unsupported image type: {mime}. Use PNG/JPEG/WebP.')
        try:
            raw = base64.b64decode(b64, validate=True)
        except Exception:
            raise api_error(400, "INVALID_IMAGE", INVALID_IMAGE)
        if len(raw) > MAX_LOGO_BYTES:
            raise api_error(400, "EACH_LOGO_MUST_BE_2_MB_OR_SMALLER", 'Each logo must be 2 MB or smaller.')
        out.append({"id": lg.get("id"), "name": lg.get("name", "logo"), "data_url": _stored_logo(raw), "order": lg.get("order", 0)})
    return out


async def _assert_camp(camp_id: str | None) -> None:
    db = get_db()
    if not camp_id:
        raise api_error(400, "CAMP_ID_IS_REQUIRED", 'camp_id is required')
    if not await db.camps.find_one({"_id": ObjectId(camp_id)}):
        raise api_error(404, "CAMP_NOT_FOUND", 'Camp not found')


@router.get("/logos")
async def get_logos(camp_id: str, actor: dict = Depends(require_any)) -> Dict[str, Any]:
    db = get_db()
    await _assert_camp(camp_id)
    record = await db.prescription_templates.find_one({"camp_id": ObjectId(camp_id)})
    return {"logos": record["logos"] if record else default_logos()}


@router.put("/logos")
async def save_logos(body: dict, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    """Sponsor logos are the only editable part of the prescription. Saving is live."""
    db = get_db()
    camp_id = body.get("camp_id")
    await _assert_camp(camp_id)
    logos = await asyncio.to_thread(_validate_logos, body.get("logos"))
    await db.prescription_templates.find_one_and_update(
        {"camp_id": ObjectId(camp_id)},
        {"$set": {"logos": logos, "updated_at": now_utc()}},
        upsert=True,
    )
    return {"logos": logos}
