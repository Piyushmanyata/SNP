from typing import Any, Dict
from fastapi import APIRouter, Depends, BackgroundTasks
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from db import get_db, in_transaction
from models import CampBody, CampDayBody, DoorManualBody, PrintWindowBody
from helpers import IST, as_utc, iso, next_ist_midnight, now_utc, today_ist_str, api_error
from security import require_admin, require_any
import sms

router = APIRouter(prefix="/api/camps", tags=["camps"])


def door_manual_open(camp: dict | None, today: str | None = None) -> bool:
    """An admin opens manual entry at the door for one camp day; it lapses on its own."""
    return (camp or {}).get("door_manual_date") == (today or today_ist_str())


def ser_camp(c: dict) -> Dict[str, Any]:
    return {
        "id": str(c["_id"]),
        "name": c["name"],
        "venue": c["venue"],
        "venue_sms": c.get("venue_sms"),
        "camp_date": c["camp_date"],
        "camp_number": c.get("camp_number"),
        "is_active": c.get("is_active", False),
        "door_manual_entry": door_manual_open(c),
        "created_at": iso(c.get("created_at")),
    }


def ser_day(d: dict, *, printing_open: bool | None = None, today: str | None = None) -> Dict[str, Any]:
    today = today or today_ist_str()
    open_ = bool(printing_open) if printing_open is not None else bool(d.get("printing_open", False))
    booked = d.get("booked", 0)
    return {
        "id": str(d["_id"]),
        "camp_id": str(d["camp_id"]),
        "day_date": d["day_date"],
        "seat_limit": d.get("seat_limit", 0),
        "booked": booked,
        "over_capacity": booked > d.get("seat_limit", 0),
        "printing_open": open_,
        "is_today": d["day_date"] == today,
        "can_edit": d["day_date"] >= today,
    }


def effective_printing(camp: dict | None, days, now=None) -> Dict[str, Any]:
    now = as_utc(now or now_utc())
    today = now.astimezone(IST).strftime("%Y-%m-%d")
    days = list(days or [])
    override = (camp or {}).get("print_override") or {}
    expires = override.get("expires_at")
    if expires and as_utc(expires) <= now:
        override = {}
    mode = override.get("mode")
    selected = override.get("day_id")
    operating = None
    if mode == "disable":
        printing_open = False
    elif mode == "enable" and selected is not None:
        operating = next((d for d in days if str(d["_id"]) == str(selected)), None)
        printing_open = operating is not None
    else:
        operating = next((d for d in days if d.get("day_date") == today), None)
        printing_open = operating is not None
        mode = "automatic"
    return {
        "printing_open": printing_open,
        "operating_day_id": str(operating["_id"]) if operating else None,
        "operating_day_date": operating.get("day_date") if operating else None,
        "mode": mode or "automatic",
        "override_expires_at": iso(override.get("expires_at")) if override.get("mode") else None,
        "server_time": iso(now),
    }


def _days_projection(camp: dict, days) -> tuple[list, dict]:
    state = effective_printing(camp, days)
    out = [
        ser_day(
            d,
            printing_open=bool(state["printing_open"] and str(d["_id"]) == state["operating_day_id"]),
        )
        for d in days
    ]
    return out, state


@router.post("")
async def create_camp(body: CampBody, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    camp_date = body.camp_date
    if not camp_date and body.days:
        camp_date = min(d.day_date for d in body.days)
    if not camp_date:
        raise api_error(400, "CAMP_DATE_OR_DAYS_IS_REQUIRED", 'camp_date or days is required')
    existing = None
    if body.setup_request_id:
        existing = await db.camps.find_one({"setup_request_id": body.setup_request_id})
    if existing:
        c = existing
    else:
        doc = {
            "name": body.name, "venue": body.venue, "venue_sms": body.venue_sms, "camp_date": camp_date,
            "camp_number": body.camp_number,
            "is_active": False, "print_override": None,
            "created_at": now_utc(),
        }
        if body.setup_request_id:
            doc["setup_request_id"] = body.setup_request_id
        try:
            res = await db.camps.insert_one(doc)
        except DuplicateKeyError:
            raise api_error(409, "CAMP_EXISTS", 'This camp was just created. Refresh the list.')
        c = await db.camps.find_one({"_id": res.inserted_id})
    if body.days:
        try:
            for day in body.days:
                found = await db.camp_days.find_one({"camp_id": c["_id"], "day_date": day.day_date})
                if found:
                    await db.camp_days.update_one({"_id": found["_id"]}, {"$set": {"seat_limit": day.seat_limit}})
                else:
                    await db.camp_days.insert_one({
                        "camp_id": c["_id"], "day_date": day.day_date,
                        "seat_limit": day.seat_limit, "booked": 0, "created_at": now_utc(),
                    })
        except Exception:
            raise api_error(409, "CAMP_SETUP_INCOMPLETE", 'Camp days could not all be saved. Retry the same setup.', camp_id=str(c['_id']))
    return {"camp": ser_camp(c)}


@router.get("")
async def list_camps(actor: dict = Depends(require_any)) -> Dict[str, Any]:
    db = get_db()
    camps = await db.camps.find().sort("created_at", -1).to_list(500)
    return {"camps": [ser_camp(c) for c in camps]}


@router.get("/active")
async def active_camp(actor: dict = Depends(require_any)) -> Dict[str, Any]:
    db = get_db()
    c = await db.camps.find_one({"is_active": True})
    if not c:
        return {"camp": None, "days": []}
    days = await db.camp_days.find({"camp_id": c["_id"]}).sort("day_date", 1).to_list(100)
    days_out, state = _days_projection(c, days)
    return {"camp": ser_camp(c), "days": days_out, **{k: state[k] for k in (
        "printing_open", "operating_day_id", "operating_day_date", "mode",
        "override_expires_at", "server_time",
    )}}


@router.post("/door-manual")
async def set_door_manual(body: DoorManualBody, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    """Opens manual entry at the door for today only. It shuts itself when the day ends."""
    db = get_db()
    c = await db.camps.find_one({"is_active": True})
    if not c:
        raise api_error(400, "NO_ACTIVE_CAMP", 'No active camp')
    await db.camps.update_one(
        {"_id": c["_id"]},
        {"$set": {"door_manual_date": today_ist_str() if body.enabled else None}},
    )
    updated = await db.camps.find_one({"_id": c["_id"]})
    if not updated:
        raise api_error(404, "CAMP_NOT_FOUND", 'Camp not found')
    return {"camp": ser_camp(updated)}


@router.get("/active/public")
async def active_camp_public() -> Dict[str, Any]:
    """Public (no auth) projection for patient self-registration. No PHI."""
    db = get_db()
    c = await db.camps.find_one({"is_active": True})
    if not c:
        return {"camp": None, "days": []}
    days = await db.camp_days.find({"camp_id": c["_id"]}).sort("day_date", 1).to_list(100)
    today = today_ist_str()
    out = []
    total_seats = 0
    for d in days:
        n = d.get("booked", 0)
        limit = d.get("seat_limit") or 0
        total_seats += limit
        out.append({
            "id": str(d["_id"]),
            "day_date": d["day_date"],
            "is_today": d["day_date"] == today,
            "is_past": d["day_date"] < today,
            "registered": n,
            "seat_limit": limit,
            "remaining": max(0, limit - n),
        })
    return {
        "camp": {"id": str(c["_id"]), "name": c["name"], "venue": c["venue"]},
        "total_seats": total_seats,
        "total_registered": sum(d.get("booked", 0) for d in days),
        "days": out,
    }


@router.patch("/{camp_id}")
async def update_camp(camp_id: str, body: CampBody, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    await db.camps.update_one({"_id": ObjectId(camp_id)}, {"$set": body.model_dump(
        exclude_unset=True, include={"name", "venue", "venue_sms", "camp_date", "camp_number"})})
    c = await db.camps.find_one({"_id": ObjectId(camp_id)})
    if not c:
        raise api_error(404, "CAMP_NOT_FOUND", 'Camp not found')
    return {"camp": ser_camp(c)}


@router.post("/{camp_id}/activate")
async def activate_camp(camp_id: str, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    oid = ObjectId(camp_id)
    if not await db.camps.find_one({"_id": oid}):
        raise api_error(404, "CAMP_NOT_FOUND", 'Camp not found')
    # exactly one active: deactivate others first (partial unique index guards)
    await db.camps.update_many({"is_active": True}, {"$set": {"is_active": False, "print_override": None}})
    try:
        await db.camps.update_one({"_id": oid}, {"$set": {"is_active": True, "print_override": None}})
    except DuplicateKeyError:
        raise api_error(409, "CAMP_ACTIVATION_CONFLICT", 'Another camp was activated at the same time. Refresh and try again.')
    return {"ok": True}


@router.post("/{camp_id}/deactivate")
async def deactivate_camp(camp_id: str, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    await db.camps.update_one({"_id": ObjectId(camp_id)}, {"$set": {"is_active": False, "print_override": None}})
    return {"ok": True}


@router.delete("/{camp_id}")
async def delete_camp(camp_id: str, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    oid = ObjectId(camp_id)
    if await db.patients.find_one({"camp_id": oid}):
        raise api_error(409, "CAMP_HAS_REGISTRATIONS_CANNOT_DELETE", 'Camp has registrations; cannot delete')
    await db.camp_days.delete_many({"camp_id": oid})
    await db.camps.delete_one({"_id": oid})
    return {"ok": True}


@router.post("/days")
async def upsert_camp_day(body: CampDayBody, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    camp_oid = ObjectId(body.camp_id)
    if not await db.camps.find_one({"_id": camp_oid}):
        raise api_error(404, "CAMP_NOT_FOUND", 'Camp not found')
    existing = await db.camp_days.find_one({"camp_id": camp_oid, "day_date": body.day_date})
    if existing:
        if existing["day_date"] < today_ist_str():
            raise api_error(409, "PAST_CAMP_DAYS_CANNOT_BE_EDITED", 'Past camp days cannot be edited')
        await db.camp_days.update_one({"_id": existing["_id"]},
                                      {"$set": {"seat_limit": body.seat_limit}})
        d = await db.camp_days.find_one({"_id": existing["_id"]})
    else:
        try:
            res = await db.camp_days.insert_one({
                "camp_id": camp_oid, "day_date": body.day_date,
                "seat_limit": body.seat_limit, "booked": 0,
                "created_at": now_utc(),
            })
        except DuplicateKeyError:
            raise api_error(409, "DAY_EXISTS", 'This camp day was just added. Refresh and edit it.')
        d = await db.camp_days.find_one({"_id": res.inserted_id})
    if not d:
        raise api_error(404, "DAY_NOT_FOUND", 'Day not found')
    camp = await db.camps.find_one({"_id": camp_oid})
    days = await db.camp_days.find({"camp_id": camp_oid}).to_list(100)
    state = effective_printing(camp, days)
    return {"day": ser_day(d, printing_open=bool(
        state["printing_open"] and state["operating_day_id"] == str(d["_id"])
    ))}


@router.get("/{camp_id}/days")
async def list_days(camp_id: str, actor: dict = Depends(require_any)) -> Dict[str, Any]:
    db = get_db()
    camp = await db.camps.find_one({"_id": ObjectId(camp_id)})
    days = await db.camp_days.find({"camp_id": ObjectId(camp_id)}).sort("day_date", 1).to_list(100)
    days_out, _state = _days_projection(camp or {}, days)
    return {"days": days_out}


NOTICE_FIELDS = {"phone": 1, "phone_normalized": 1, "reg_no": 1, "created_by": 1, "camp_id": 1}


@router.patch("/days/{day_id}")
async def update_camp_day(day_id: str, body: CampDayBody, background_tasks: BackgroundTasks,
                          actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    if not ObjectId.is_valid(day_id) or not ObjectId.is_valid(body.camp_id):
        raise api_error(400, "INVALID_CAMP_OR_DAY_ID", 'Invalid camp or day ID')
    camp_oid = ObjectId(body.camp_id)
    day = await db.camp_days.find_one({"_id": ObjectId(day_id), "camp_id": camp_oid})
    camp = await db.camps.find_one({"_id": camp_oid})
    if not day or not camp:
        raise api_error(404, "DAY_NOT_FOUND", 'Day not found')
    if day["day_date"] < today_ist_str() or body.day_date < today_ist_str():
        raise api_error(409, "PAST_CAMP_DAYS_CANNOT_BE_EDITED", 'Past camp days cannot be edited')
    date_changed = body.day_date != day["day_date"]
    on_day = {"camp_id": camp_oid, "$or": [{"booked_camp_day_id": day["_id"]}, {"camp_day_id": day["_id"]}]}
    if date_changed:
        if await db.patients.find_one({"$and": [on_day, {"$or": [
            {"arrived_at": {"$ne": None}}, {"printed_at": {"$ne": None}}, {"queue_status": {"$ne": "registered"}},
        ]}]}, {"_id": 1}):
            raise api_error(409, "DAY_HAS_ARRIVED_OR_CLINICAL_PATIENTS_ITS_DATE_CANNOT_CHANGE", 'Day has arrived or clinical patients; its date cannot change')
        if await db.camp_days.find_one({"camp_id": camp_oid, "day_date": body.day_date}):
            raise api_error(409, "ANOTHER_CAMP_DAY_ALREADY_USES_THAT_DATE", 'Another camp day already uses that date')
    updates = {"day_date": body.day_date, "seat_limit": body.seat_limit}
    if date_changed:
        updates["edit_revision"] = str(ObjectId())
    booked_here = {"camp_id": camp_oid, "$or": [
        {"booked_camp_day_id": day["_id"]}, {"camp_day_id": day["_id"], "booked_camp_day_id": None},
    ]}

    async def write(session):
        changed = await db.camp_days.find_one_and_update(
            {"_id": day["_id"], "day_date": day["day_date"]}, {"$set": updates},
            return_document=True, session=session,
        )
        if not changed:
            raise api_error(409, "DAY_CHANGED_RELOAD_AND_TRY_AGAIN", 'Day changed; reload and try again')
        days = await db.camp_days.find({"camp_id": camp_oid}, session=session).to_list(None)
        await db.camps.update_one(
            {"_id": camp_oid}, {"$set": {"camp_date": min(d["day_date"] for d in days)}}, session=session,
        )
        if not date_changed:
            return changed, days, []
        booked = await db.patients.find(booked_here, NOTICE_FIELDS, session=session).to_list(None)
        queued = await sms.queue_sms(
            db, booked, "registration", body.day_date, camp.get("venue_sms") or camp["venue"],
            event_key=f"edit:{updates['edit_revision']}", session=session,
        )
        return changed, days, queued

    try:
        changed, days, queued = await in_transaction(write)
    except DuplicateKeyError:
        raise api_error(409, "ANOTHER_CAMP_DAY_ALREADY_USES_THAT_DATE", 'Another camp day already uses that date')
    await sms.dispatch(background_tasks, db, queued)
    state = effective_printing(camp, days)
    return {"day": ser_day(changed, printing_open=bool(
        state["printing_open"] and state["operating_day_id"] == str(changed["_id"])
    ))}


@router.patch("/days/{day_id}/print-window")
async def toggle_print_window(day_id: str, body: PrintWindowBody, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    d = await db.camp_days.find_one({"_id": ObjectId(day_id)})
    if not d:
        raise api_error(404, "DAY_NOT_FOUND", 'Day not found')
    camp = await db.camps.find_one({"_id": d["camp_id"]})
    if not camp:
        raise api_error(404, "CAMP_NOT_FOUND", 'Camp not found')
    mode = body.mode
    if not mode:
        mode = "enable" if body.printing_open else "disable"
    if mode == "automatic":
        await db.camps.update_one({"_id": camp["_id"]}, {"$set": {"print_override": None}})
    elif mode == "disable":
        await db.camps.update_one({"_id": camp["_id"]}, {"$set": {"print_override": {
            "mode": "disable",
            "day_id": None,
            "set_at": now_utc(),
            "expires_at": next_ist_midnight(),
        }}})
    elif mode == "enable":
        target_id = body.day_id or day_id
        target = await db.camp_days.find_one({"_id": ObjectId(target_id), "camp_id": camp["_id"]})
        if not target:
            raise api_error(409, "INVALID_DAY", 'The selected day does not belong to this camp.')
        await db.camps.update_one({"_id": camp["_id"]}, {"$set": {"print_override": {
            "mode": "enable",
            "day_id": target["_id"],
            "set_at": now_utc(),
            "expires_at": next_ist_midnight(),
        }}})
    else:
        raise api_error(400, "MODE_MUST_BE_ENABLE_DISABLE_OR_AUTOMATIC", 'mode must be enable, disable, or automatic')
    camp = await db.camps.find_one({"_id": camp["_id"]})
    d = await db.camp_days.find_one({"_id": d["_id"]})
    if not d:
        raise api_error(404, "DAY_NOT_FOUND", 'Day not found')
    state = effective_printing(camp, [d])
    return {"day": ser_day(d, printing_open=bool(state["printing_open"] and state["operating_day_id"] == str(d["_id"])))}


@router.delete("/days/{day_id}")
async def delete_day(day_id: str, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    oid = ObjectId(day_id)
    if await db.patients.find_one({"$or": [{"booked_camp_day_id": oid}, {"camp_day_id": oid}]}):
        raise api_error(409, "DAY_HAS_REGISTRATIONS_CANNOT_DELETE", 'Day has registrations; cannot delete')
    await db.camp_days.delete_one({"_id": oid})
    return {"ok": True}
