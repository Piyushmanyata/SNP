from datetime import date, datetime, timedelta, timezone
from itertools import count
from xml.etree.ElementTree import Element, tostring

import httpx
from bson import ObjectId

import msg91
import security
import server
import sms
from conftest import FROZEN_IST, freeze_clock, run_db
from helpers import IST
from models import FulfilmentBody, RegisterBody
from routes_registration import desk_register

TODAY = FROZEN_IST[:10]
NOW = datetime.fromisoformat(FROZEN_IST).replace(tzinfo=IST).astimezone(timezone.utc)
_numbers = count(1000)


def day(offset):
    return (date.fromisoformat(TODAY) + timedelta(days=offset)).isoformat()


def patient_doc(**fields):
    number = next(_numbers)
    return {"reg_no": number, "patient_qr": f"qr-{number}", **fields}


def user_doc(name, role="volunteer", **fields):
    return {"name": name, "name_normalized": name.casefold(), "role": role, "disabled_at": None, **fields}


TOMORROW = day(1)
OTHER_DAY = day(2)
ADMIN = {"_id": ObjectId(), "role": "admin"}
ACTOR = {"_id": ObjectId(), "role": "volunteer"}
CLINICAL = {"_id": ObjectId(), "role": "clinical_desk_operator"}
CARD = '<PrintLetterBarcodeData name="Sunita Devi" gender="F" dob="1975-06-14" uid="123456781234" street="12 Station Road Sikar"/>'
OTHER_CARD = '<PrintLetterBarcodeData name="Ram Prasad" gender="M" dob="1968-01-09" uid="999988887777" street="4 Mill Lane Sikar"/>'
RX = {"r_sph": "-1.00", "l_sph": "-1.25", "add": "+2.00"}
MEDICINE = {"medicine_id": str(ObjectId()), "name": "Moxifloxacin"}
MEDICINE_ALT = {"medicine_id": str(ObjectId()), "name": "Chloramphenicol"}
FIXED_POWER = 2.0


class Request:
    client = None


def run_camp(monkeypatch, body, ist=FROZEN_IST, listener=None):
    freeze_clock(monkeypatch, ist)

    async def seeded(database):
        await database.medicines.insert_many([
            {"_id": ObjectId(m["medicine_id"]), "name": m["name"], "name_key": m["name"].casefold(), "active": True}
            for m in (MEDICINE, MEDICINE_ALT)
        ])
        await database.fixed_powers.insert_many([{"value": value, "active": True} for value in (-1.5, 2.0, 2.25)])
        return await body(database)

    return run_db(seeded, listener)


def asgi_client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://testserver")


def http(monkeypatch, body):
    async def with_client(database):
        async with asgi_client() as client:
            return await body(database, client)

    return run_camp(monkeypatch, with_client)


def bearer(user_id, name="", role=""):
    return {"Authorization": f"Bearer {security.create_access_token(str(user_id), name, role)}"}


async def seed_camp(database, days=(TODAY,), **camp):
    camp_id = ObjectId()
    await database.camps.insert_one({
        "_id": camp_id, "name": "Sikar Camp", "venue": "Sikar Bhawan", "is_active": True, "camp_number": 162,
        **camp,
    })
    day_ids = []
    for day_date in days:
        result = await database.camp_days.insert_one({
            "camp_id": camp_id, "day_date": day_date, "seat_limit": 50, "booked": 0, "printing_open": True,
        })
        day_ids.append(result.inserted_id)
    return camp_id, day_ids


async def register(day_id, actor=ACTOR, background_tasks=None, **fields):
    body = RegisterBody(
        full_name=fields.pop("full_name", "Sunita Devi"),
        age=fields.pop("age", 51),
        phone=fields.pop("phone", "9876500001"),
        camp_day_id=str(day_id),
        **fields,
    )
    if body.aadhaar_scanned and not body.qr_payload:
        body.qr_payload = tostring(Element(
            "PrintLetterBarcodeData", name=body.full_name, gender=body.gender or "",
            dob=body.dob or "", uid=body.aadhaar_last4 or "", street=body.address or "",
        ), encoding="unicode")
    if not body.aadhaar_scanned and not body.manual_reason:
        body.failed_scan_attempts = 3
        body.manual_reason = "scanner unavailable"
    result = await desk_register(body, Request(), actor=actor, background_tasks=background_tasks)
    return result["registration"]


def recorder(monkeypatch):
    sent = []
    for name in msg91.TEMPLATE_ENV.values():
        monkeypatch.setenv(name, "test-flow")

    def fake_send(message_type, mobile, variables):
        sent.append({"type": message_type, "mobile": mobile, **variables})
        return f"id-{len(sent)}"

    monkeypatch.setattr(msg91, "send_dlt_sms", fake_send)
    monkeypatch.setattr(sms.msg91, "send_dlt_sms", fake_send)
    monkeypatch.setattr(sms.msg91, "configured", lambda: True)
    return sent


def fulfil(trans_id, rev_id, **kw):
    kw.setdefault("paper_reviewed", True)
    kw.setdefault("reviewed_revision_id", str(rev_id))
    kw.setdefault("reviewed_generation", 1)
    kw.setdefault("operation_id", str(ObjectId()))
    if kw.get("item_type") == "medicine" and "medicine_outcomes" not in kw:
        kw["medicine_outcomes"] = [{"medicine_id": MEDICINE["medicine_id"], "given": kw.get("status") != "not_available"}]
    return FulfilmentBody(transcription_id=str(trans_id), **kw)


async def seen_patient(database, camp_id=None, measurements=RX, fixed_power=FIXED_POWER, **patient):
    import helpers
    camp_id = camp_id or ObjectId()
    patient_id, trans_id, rev_id = ObjectId(), ObjectId(), ObjectId()
    now = helpers.now_utc()
    await database.patients.insert_one(patient_doc(
        _id=patient_id, camp_id=camp_id, camp_day_id=ObjectId(), full_name="Sunita Devi",
        phone="9876500001", phone_normalized="9876500001",
        queue_status="seen", arrived_at=now, printed_at=now, seen_at=now,
        committed_revision_id=rev_id, clinical_generation=1, issue_auth_op=None,
        **patient,
    ))
    await database.prescription_revisions.insert_one({
        "_id": rev_id, "patient_id": patient_id, "camp_id": camp_id, "operation_id": str(ObjectId()),
        "prescribed_lines": ["medicine", "specs_fixed", "specs_made", "ot"],
        "none_prescribed": False, "specs_measurements": measurements,
        "prescribed_medicines": [MEDICINE], "ot_eye": "R", "ot_outcome": "iol_surgery",
        "fixed_power_r": fixed_power, "fixed_power_l": fixed_power,
    })
    await database.transcriptions.insert_one({
        "_id": trans_id, "patient_id": patient_id, "camp_id": camp_id,
        "locked": True, "specs_measurements": measurements, "prescribed_medicines": [MEDICINE],
        "fixed_power_r": fixed_power, "fixed_power_l": fixed_power,
    })
    return {"camp_id": camp_id, "patient_id": patient_id, "trans_id": trans_id, "rev_id": rev_id}
