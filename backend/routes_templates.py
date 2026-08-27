import base64
from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId
from db import get_db
from helpers import now_utc, iso
from security import require_admin, require_any

router = APIRouter(prefix="/api/templates", tags=["templates"])

DEFAULT_BLOCKS = [
    {"id": "identity", "label": "Patient Identity", "type": "identity", "visible": True, "height": 0},
    {"id": "diagnosis", "label": "Diagnosis", "type": "lines", "visible": True, "height": 24},
    {"id": "vision", "label": "Vision (R / L)", "type": "lines", "visible": True, "height": 24},
    {"id": "prescription", "label": "Prescription (Rx)", "type": "lines", "visible": True, "height": 48},
    {"id": "vitals", "label": "BP / Blood Sugar", "type": "lines", "visible": True, "height": 18},
    {"id": "advice", "label": "Advice", "type": "lines", "visible": True, "height": 24},
    {"id": "signature", "label": "Doctor's Signature", "type": "signature", "visible": True, "height": 0},
]

MAX_LOGO_BYTES = 2 * 1024 * 1024
ALLOWED_MIME = ("image/png", "image/jpeg", "image/webp")


def default_template(camp):
    return {
        "camp_id": str(camp["_id"]),
        "header_title": camp["name"],
        "header_subtitle": camp.get("venue", ""),
        "footer_note": "Paper prescription is the source of truth.",
        "blocks": [dict(b) for b in DEFAULT_BLOCKS],
        "logos": [],
        "status": "defaults",
        "version": 0,
    }


def ser_tpl(t):
    if not t:
        return None
    return {
        "id": str(t["_id"]) if t.get("_id") else None,
        "camp_id": str(t["camp_id"]),
        "header_title": t.get("header_title", ""),
        "header_subtitle": t.get("header_subtitle", ""),
        "footer_note": t.get("footer_note", ""),
        "blocks": t.get("blocks", []),
        "logos": t.get("logos", []),
        "status": t.get("status"),
        "version": t.get("version", 0),
        "published_at": iso(t.get("published_at")),
        "updated_at": iso(t.get("updated_at")),
    }


def _validate_logos(logos):
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


async def _get_camp(camp_id):
    db = get_db()
    camp = await db.camps.find_one({"_id": ObjectId(camp_id)})
    if not camp:
        raise HTTPException(status_code=404, detail="Camp not found")
    return camp


@router.get("")
async def get_templates(camp_id: str, actor: dict = Depends(require_admin)):
    db = get_db()
    camp = await _get_camp(camp_id)
    draft = await db.prescription_templates.find_one({"camp_id": ObjectId(camp_id), "status": "draft"})
    published = await db.prescription_templates.find(
        {"camp_id": ObjectId(camp_id), "status": "published"}
    ).sort("version", -1).limit(1).to_list(1)
    return {
        "defaults": default_template(camp),
        "draft": ser_tpl(draft),
        "published": ser_tpl(published[0]) if published else None,
    }


@router.post("/draft")
async def save_draft(body: dict, actor: dict = Depends(require_admin)):
    db = get_db()
    camp_id = body.get("camp_id")
    await _get_camp(camp_id)
    logos = _validate_logos(body.get("logos"))
    doc = {
        "camp_id": ObjectId(camp_id),
        "header_title": body.get("header_title", ""),
        "header_subtitle": body.get("header_subtitle", ""),
        "footer_note": body.get("footer_note", ""),
        "blocks": body.get("blocks", DEFAULT_BLOCKS),
        "logos": logos,
        "status": "draft",
        "updated_at": now_utc(),
    }
    existing = await db.prescription_templates.find_one({"camp_id": ObjectId(camp_id), "status": "draft"})
    if existing:
        await db.prescription_templates.update_one({"_id": existing["_id"]}, {"$set": doc})
        t = await db.prescription_templates.find_one({"_id": existing["_id"]})
    else:
        res = await db.prescription_templates.insert_one(doc)
        t = await db.prescription_templates.find_one({"_id": res.inserted_id})
    return {"draft": ser_tpl(t)}


@router.post("/publish")
async def publish(body: dict, actor: dict = Depends(require_admin)):
    db = get_db()
    camp_id = body.get("camp_id")
    await _get_camp(camp_id)
    draft = await db.prescription_templates.find_one({"camp_id": ObjectId(camp_id), "status": "draft"})
    if not draft:
        raise HTTPException(status_code=400, detail="Save a draft before publishing.")
    # single-page guard: total block height must fit an A4 writing area (~230mm)
    total_h = sum(b.get("height", 0) for b in draft.get("blocks", []) if b.get("visible"))
    if total_h > 230:
        raise HTTPException(status_code=400, detail="Template exceeds one A4 page. Reduce block heights.")
    last = await db.prescription_templates.find(
        {"camp_id": ObjectId(camp_id), "status": "published"}
    ).sort("version", -1).limit(1).to_list(1)
    version = (last[0]["version"] + 1) if last else 1
    pub = {k: draft[k] for k in ["camp_id", "header_title", "header_subtitle", "footer_note", "blocks", "logos"]}
    pub.update({"status": "published", "version": version, "published_at": now_utc()})
    res = await db.prescription_templates.insert_one(pub)
    t = await db.prescription_templates.find_one({"_id": res.inserted_id})
    return {"published": ser_tpl(t)}


@router.post("/restore-defaults")
async def restore_defaults(body: dict, actor: dict = Depends(require_admin)):
    db = get_db()
    camp_id = body.get("camp_id")
    camp = await _get_camp(camp_id)
    d = default_template(camp)
    doc = {**d, "camp_id": ObjectId(camp_id), "status": "draft", "updated_at": now_utc()}
    existing = await db.prescription_templates.find_one({"camp_id": ObjectId(camp_id), "status": "draft"})
    if existing:
        await db.prescription_templates.update_one({"_id": existing["_id"]}, {"$set": doc})
        t = await db.prescription_templates.find_one({"_id": existing["_id"]})
    else:
        res = await db.prescription_templates.insert_one(doc)
        t = await db.prescription_templates.find_one({"_id": res.inserted_id})
    return {"draft": ser_tpl(t)}


@router.get("/active")
async def active_template(camp_id: str, actor: dict = Depends(require_any)):
    db = get_db()
    camp = await _get_camp(camp_id)
    published = await db.prescription_templates.find(
        {"camp_id": ObjectId(camp_id), "status": "published"}
    ).sort("version", -1).limit(1).to_list(1)
    return {"template": ser_tpl(published[0]) if published else default_template(camp)}
