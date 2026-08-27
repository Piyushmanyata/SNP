import io
import csv
from bson import ObjectId
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from db import get_db
from helpers import iso
from security import require_admin, require_staff, require_any

router = APIRouter(prefix="/api", tags=["reports"])


@router.get("/kpis")
async def kpis(actor: dict = Depends(require_any)):
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
async def leaderboard(actor: dict = Depends(require_staff)):
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


@router.get("/exports/camp-records")
async def export_camp_records(actor: dict = Depends(require_admin)):
    db = get_db()
    camp = await db.camps.find_one({"is_active": True})
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["reg_no", "full_name", "gender", "age", "phone", "address", "seen_at"])
    if camp:
        pts = await db.patients.find({"camp_id": camp["_id"], "queue_status": "seen"}).to_list(100000)
        for p in pts:
            writer.writerow([p["reg_no"], p["full_name"], p.get("gender", ""), p.get("age", ""),
                             p.get("phone", ""), p.get("address", ""), iso(p.get("seen_at"))])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=camp_records.csv"})


@router.get("/exports/clinical-audit")
async def export_clinical_audit(actor: dict = Depends(require_admin)):
    db = get_db()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["event", "transcription_id", "reg_no", "detail", "at"])
    async for t in db.transcriptions.find():
        p = await db.patients.find_one({"_id": t["patient_id"]})
        reg = p["reg_no"] if p else ""
        writer.writerow(["transcription", str(t["_id"]), reg,
                         ";".join(t.get("diagnosis_options", [])), iso(t.get("created_at"))])
    async for c in db.corrections.find():
        writer.writerow(["correction", str(c["transcription_id"]), "", c.get("reason", ""), iso(c.get("created_at"))])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=clinical_audit.csv"})


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness():
    db = get_db()
    try:
        await db.command("ping")
        n_active = await db.camps.count_documents({"is_active": True})
        if n_active > 1:
            return JSONResponse(status_code=503, content={"ready": False, "reason": "multiple active camps"})
        return {"ready": True, "db": "reachable", "active_camps": n_active}
    except Exception as e:
        return JSONResponse(status_code=503, content={"ready": False, "reason": "db unreachable"})
