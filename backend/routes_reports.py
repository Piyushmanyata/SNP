import io
import csv
from typing import Any, Dict, List
from bson import ObjectId
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from db import get_db
from helpers import iso
from security import require_admin, require_staff, require_any

router = APIRouter(prefix="/api", tags=["reports"])


@router.get("/kpis")
async def kpis(actor: dict = Depends(require_any)) -> Dict[str, Any]:
    db = get_db()
    camp = await db.camps.find_one({"is_active": True})
    if not camp:
        return {"active_camp": None, "registered": 0, "seen": 0, "pre_registered": 0}
    registered = await db.patients.count_documents({"camp_id": camp["_id"]})
    seen = await db.patients.count_documents({"camp_id": camp["_id"], "queue_status": "seen"})
    return {
        "active_camp": {"id": str(camp["_id"]), "name": camp["name"]},
        "registered": registered,
        "seen": seen,
        "pending": registered - seen,
    }


@router.get("/leaderboard")
async def leaderboard(actor: dict = Depends(require_staff)) -> Dict[str, Any]:
    db = get_db()
    camp = await db.camps.find_one({"is_active": True})
    if not camp:
        return {"volunteers": [], "team_leads": []}

    # 1 point per registration that reached 'seen', credited to original registrar,
    # manual exceptions excluded
    pipeline = [
        {"$match": {"camp_id": camp["_id"], "queue_status": "seen",
                    "manual_exception": None, "created_by": {"$ne": None}}},
        {"$group": {"_id": "$created_by", "points": {"$sum": 1}}},
    ]
    agg = await db.patients.aggregate(pipeline).to_list(1000)
    points_map = {r["_id"]: r["points"] for r in agg}

    users = await db.users.find({"role": {"$in": ["volunteer", "team_lead"]}}).to_list(1000)
    volunteers, tl_points = [], {}
    for u in users:
        uid = str(u["_id"])
        pts = points_map.get(uid, 0)
        if u["role"] == "volunteer":
            volunteers.append({"name": u["name"], "points": pts, "team_lead_id": u.get("team_lead_id")})
            tl = u.get("team_lead_id")
            if tl:
                tl_points[tl] = tl_points.get(tl, 0) + pts
    team_leads = []
    for u in users:
        if u["role"] == "team_lead":
            uid = str(u["_id"])
            own = points_map.get(uid, 0)
            rollup = tl_points.get(uid, 0)
            team_leads.append({"name": u["name"], "points": own + rollup})

    volunteers.sort(key=lambda x: x["points"], reverse=True)
    team_leads.sort(key=lambda x: x["points"], reverse=True)
    return {"volunteers": volunteers, "team_leads": team_leads}


EXPORT_COLUMNS = [
    "reg_no", "full_name", "age", "gender", "phone", "address", "aadhaar_last4",
    "manual_entry", "camp_day", "registered_at", "arrived_at", "seen_at",
    "diagnosis", "bp", "blood_sugar",
    "r_sph", "r_cyl", "r_axis", "l_sph", "l_cyl", "l_axis", "add",
    "medicine", "fixed_power_specs", "spectacles_to_be_made", "ot",
    "ot_day", "ot_venue", "specs_day", "specs_venue",
]


def _line_statuses(fulfilments: dict) -> List[str]:
    specs = fulfilments.get("specs", {}).get("status")
    return [
        fulfilments.get("medicine", {}).get("status", ""),
        "issued" if specs == "fulfilled" else "",
        "deferred" if specs == "deferred" else "",
        fulfilments.get("ot", {}).get("status", ""),
    ]


def _diagnosis(t: dict) -> str:
    parts = list(t.get("diagnosis_options") or [])
    if t.get("diagnosis_other"):
        parts.append(t["diagnosis_other"])
    return ";".join(parts)


async def _export_row(db: Any, p: dict, day_dates: dict) -> List[Any]:
    t = await db.transcriptions.find_one({"patient_id": p["_id"]}) or {}
    fulfilments = {}
    if t:
        for f in await db.fulfilments.find({"transcription_id": t["_id"]}).to_list(20):
            fulfilments[f["item_type"]] = f
    m = t.get("specs_measurements") or {}
    ot = fulfilments.get("ot", {})
    specs = fulfilments.get("specs", {})
    return [
        p.get("reg_no", ""), p.get("full_name", ""), p.get("age", ""),
        p.get("gender", ""), p.get("phone", ""), p.get("address", ""),
        p.get("aadhaar_last4", ""),
        "yes" if (p.get("manual_entry") or p.get("manual_exception")) else "no",
        day_dates.get(p.get("camp_day_id"), ""),
        iso(p.get("created_at")) or "", iso(p.get("arrived_at")) or "", iso(p.get("seen_at")) or "",
        _diagnosis(t), t.get("bp", "") or "", t.get("blood_sugar", "") or "",
        *[m.get(k, "") or "" for k in ("r_sph", "r_cyl", "r_axis", "l_sph", "l_cyl", "l_axis", "add")],
        *_line_statuses(fulfilments),
        ot.get("collection_date", "") or "", ot.get("collection_venue", "") or "",
        specs.get("collection_date", "") or "" if specs.get("status") == "deferred" else "",
        specs.get("collection_venue", "") or "" if specs.get("status") == "deferred" else "",
    ]


@router.get("/exports/camp-records")
async def export_camp_records(camp_id: str | None = None, actor: dict = Depends(require_admin)) -> StreamingResponse:
    """One wide row per patient in the camp, including no-shows."""
    db = get_db()
    camp = await db.camps.find_one({"_id": ObjectId(camp_id)}) if camp_id else await db.camps.find_one({"is_active": True})
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(EXPORT_COLUMNS)
    if camp:
        days = await db.camp_days.find({"camp_id": camp["_id"]}).to_list(1000)
        day_dates = {d["_id"]: d["day_date"] for d in days}
        pts = await db.patients.find({"camp_id": camp["_id"]}).to_list(100000)
        for p in pts:
            writer.writerow(await _export_row(db, p, day_dates))
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=camp_records.csv"})


@router.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness() -> Dict[str, Any]:
    db = get_db()
    try:
        await db.command("ping")
        n_active = await db.camps.count_documents({"is_active": True})
        if n_active > 1:
            return JSONResponse(status_code=503, content={"ready": False, "reason": "multiple active camps"})
        return {"ready": True, "db": "reachable", "active_camps": n_active}
    except Exception:
        return JSONResponse(status_code=503, content={"ready": False, "reason": "db unreachable"})
