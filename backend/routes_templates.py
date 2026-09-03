import base64
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId
from db import get_db
from helpers import now_utc
from security import require_admin, require_any

router = APIRouter(prefix="/api/templates", tags=["templates"])

MAX_LOGO_BYTES = 2 * 1024 * 1024
ALLOWED_MIME = ("image/png", "image/jpeg", "image/webp")
_RUPA_PNG = Path(__file__).resolve().parent / "assets" / "rupa-sponsor.png"


def default_logos() -> List[Dict[str, Any]]:
    if not _RUPA_PNG.exists():
        return []
    data_url = "data:image/png;base64," + base64.b64encode(_RUPA_PNG.read_bytes()).decode()
    return [
        {"id": "rupa-foundation", "name": "rupa-foundation.png", "data_url": data_url, "order": 0},
    ]


def _validate_logos(logos: Optional[List[dict]]) -> List[Dict[str, Any]]:
    out = []
    for lg in (logos or [])[:6]:
        data_url = lg.get("data_url", "")
        if not data_url.startswith("data:"):
            continue
        try:
            header, b64 = data_url.split(",", 1)
            mime = header.split(";")[0].replace("data:", "")
            if mime not in ALLOWED_MIME:
                raise HTTPException(status_code=400, detail=f"Unsupported image type: {mime}. Use PNG/JPEG/WebP.")
            raw = base64.b64decode(b64, validate=False)
            if len(raw) > MAX_LOGO_BYTES:
                raise HTTPException(status_code=400, detail="Each logo must be 2 MB or smaller.")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid image data.")
        out.append({"id": lg.get("id"), "name": lg.get("name", "logo"), "data_url": data_url, "order": lg.get("order", 0)})
    return out


async def _assert_camp(camp_id: str) -> None:
    db = get_db()
    if not camp_id:
        raise HTTPException(status_code=400, detail="camp_id is required")
    if not await db.camps.find_one({"_id": ObjectId(camp_id)}):
        raise HTTPException(status_code=404, detail="Camp not found")


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
    logos = _validate_logos(body.get("logos"))
    await db.prescription_templates.find_one_and_update(
        {"camp_id": ObjectId(camp_id)},
        {"$set": {"logos": logos, "updated_at": now_utc()}},
        upsert=True,
    )
    return {"logos": logos}
