import hmac
import os


from fastapi import APIRouter, HTTPException, Request

from db import get_db
import helpers
import msg91

router = APIRouter(prefix="/api", tags=["cron"])

CAMP_REMINDER = "कल SNP नेत्र शिविर है। स्थान: {venue}। कृपया समय पर पहुँचें।"
OT_REMINDER = "कल SNP ऑपरेशन के लिए {venue} पहुँचें। अपना टोकन साथ लाएँ।"
SPECS_REMINDER = "कल SNP से चश्मा लेने {venue} पहुँचें। अपना टोकन साथ लाएँ।"
REMINDER_COPY = {"camp": CAMP_REMINDER, "ot": OT_REMINDER, "specs": SPECS_REMINDER}


def _require_cron_secret(request: Request):
    expected = os.environ.get("CRON_SECRET") or ""
    got = request.headers.get("X-Cron-Secret") or ""
    if not expected or not hmac.compare_digest(expected, got):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _valid_phone(raw) -> str | None:
    n = helpers.normalize_phone(raw)
    if not n or helpers.is_dummy_phone(n):
        return None
    return n


async def _ledger_claim(db, number, reminder_type, event_date, send_date, venue, copy):
    existing = await db.reminder_ledger.find_one({
        "number": number,
        "reminder_type": reminder_type,
        "event_date": event_date,
        "send_date": send_date,
    })
    if existing:
        return None
    doc = {
        "number": number,
        "reminder_type": reminder_type,
        "event_date": event_date,
        "send_date": send_date,
        "venue": venue,
        "copy": copy,
        "status": "pending",
        "provider_id": None,
        "created_at": helpers.now_utc(),
    }
    res = await db.reminder_ledger.insert_one(doc)
    doc["_id"] = res.inserted_id
    return doc


async def _send_unique(db, reminder_type, pairs, event_date, send_date):
    sent = 0
    copy_tpl = REMINDER_COPY[reminder_type]
    for number, venue in pairs:
        copy = copy_tpl.format(venue=venue)
        row = await _ledger_claim(db, number, reminder_type, event_date, send_date, venue, copy)
        if not row:
            continue
        try:
            pid = msg91.send_dlt_sms(reminder_type, number, venue)
            await db.reminder_ledger.update_one(
                {"_id": row["_id"]},
                {"$set": {"status": "sent", "provider_id": pid}},
            )
            sent += 1
        except Exception as exc:
            await db.reminder_ledger.update_one(
                {"_id": row["_id"]},
                {"$set": {"status": "failed", "error": str(exc)[:200]}},
            )
    return sent


async def _send_camp(db, event_date, send_date):
    days = await db.camp_days.find({"day_date": event_date}).to_list(2000)
    unique = {}
    for day in days:
        camp = await db.camps.find_one({"_id": day["camp_id"]})
        venue = camp["venue"] if camp else ""
        patients = await db.patients.find({"camp_day_id": day["_id"]}).to_list(10000)
        for p in patients:
            n = _valid_phone(p.get("phone_normalized") or p.get("phone"))
            if n and n not in unique:
                unique[n] = venue
    return await _send_unique(db, "camp", unique.items(), event_date, send_date)


async def _send_token_type(db, item_type, event_date, send_date):
    reminder_type = "ot" if item_type == "ot" else "specs"
    slips = await db.deferred_slips.find({
        "item_type": item_type,
        "active": True,
        "collection_date": event_date,
    }).to_list(10000)
    unique = {}
    for s in slips:
        if s.get("cancelled"):
            continue
        p = await db.patients.find_one({"_id": s["patient_id"]})
        if not p:
            continue
        n = _valid_phone(p.get("phone_normalized") or p.get("phone"))
        if not n:
            continue
        venue = s.get("collection_venue") or ""
        if item_type == "ot" and s.get("ot_schedule_day_id"):
            day = await db.ot_schedule_days.find_one({"_id": s["ot_schedule_day_id"]})
            if day:
                venue = day["venue"]
        if item_type == "specs" and s.get("specs_collection_day_id"):
            day = await db.specs_collection_days.find_one({"_id": s["specs_collection_day_id"]})
            if day:
                venue = day["venue"]
        if n not in unique:
            unique[n] = venue
    return await _send_unique(db, reminder_type, unique.items(), event_date, send_date)


async def send_d1_reminders():
    if not msg91.configured():
        return {"ok": True, "sent": 0, "reason": "msg91_unconfigured"}
    today = helpers.today_ist_str()
    tomorrow = helpers.tomorrow_ist_str()
    db = get_db()
    sent = 0
    sent += await _send_camp(db, tomorrow, today)
    sent += await _send_token_type(db, "ot", tomorrow, today)
    sent += await _send_token_type(db, "specs", tomorrow, today)
    return {"ok": True, "sent": sent, "event_date": tomorrow, "send_date": today}


@router.post("/cron/reminders")
async def cron_reminders(request: Request):
    _require_cron_secret(request)
    return await send_d1_reminders()
