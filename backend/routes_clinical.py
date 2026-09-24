from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, NoReturn, Optional, Tuple
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pymongo.errors import DuplicateKeyError
from pydantic import ValidationError
from bson import ObjectId
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase
from db import get_db, in_transaction
from models import (
    TranscriptionBody, FulfilmentBody, CorrectionBody, OtScheduleBody, SpecsScheduleBody,
    CompletePrescriptionBody, UndoCompletionBody,
)
from catalogue import resolve_medicines, stocked_power
from clinical_state import (
    CONTENT_FIELDS,
    PRESCRIBED_LINE_KEYS, assert_clinical_operator, arrival_ready, commit_completion,
    commit_correction, commit_undo, conflict, extract_content, normalize_ot_eye,
    generation_of, has_issue_history, insert_revision, payload_hash, record_operation, recover_operation,
    serialize_revision, validate_completion,
)
from helpers import (
    now_utc, iso, DIAGNOSIS_OPTIONS, now_ist, ist_local_instant,
    normalize_name, normalize_phone, parse_patient_identifier,
)
from bson.errors import InvalidId
from serializers import ser_patient, ser_person
from security import require_clinical, require_admin, require_any
import sms

router = APIRouter(prefix="/api/clinical", tags=["clinical"])


Write = Callable[[Any], Awaitable[Tuple[Dict[str, Any], Optional[ObjectId]]]]


async def _claim_patient(db: AsyncDatabase, patient_id: ObjectId, session) -> dict:
    """Every clinical write bumps the patient's clinical_seq first, so two writers on one patient conflict and retry."""
    patient = await db.patients.find_one_and_update(
        {"_id": patient_id}, {"$inc": {"clinical_seq": 1}}, return_document=True, session=session,
    )
    if not patient:
        raise HTTPException(status_code=404, detail="Registration not found")
    return patient


async def _run_operation(db: AsyncDatabase, operation_id: str, kind: str, digest: str, write: Write) -> Tuple[Dict[str, Any], Optional[ObjectId]]:
    try:
        return await in_transaction(write)
    except DuplicateKeyError:
        done = await recover_operation(db, operation_id, kind, digest)
        if not done:
            raise
        return done["result"], None


def ser_trans(t: dict) -> Dict[str, Any]:
    return {
        "id": str(t["_id"]),
        "patient_id": str(t["patient_id"]),
        "person_id": str(t["person_id"]) if t.get("person_id") else None,
        "camp_id": str(t["camp_id"]) if t.get("camp_id") else None,
        "diagnosis_options": t.get("diagnosis_options", []),
        "diagnosis_other": t.get("diagnosis_other"),
        "blood_sugar": t.get("blood_sugar"),
        "bp": t.get("bp"),
        "remarks": t.get("remarks"),
        "specs_measurements": t.get("specs_measurements"),
        "ot_eye": t.get("ot_eye"),
        "ot_outcome": t.get("ot_outcome"),
        "ot_notes": t.get("ot_notes"),
        "prescribed_medicines": t.get("prescribed_medicines") or [],
        "fixed_power_r": t.get("fixed_power_r"),
        "fixed_power_l": t.get("fixed_power_l"),
        "locked": t.get("locked", False),
        "draft_version": t.get("draft_version") or 0,
        "created_at": iso(t.get("created_at")),
    }


def ser_fulfil(f: dict) -> Dict[str, Any]:
    return {
        "id": str(f["_id"]),
        "transcription_id": str(f["transcription_id"]),
        "item_type": f["item_type"],
        "status": f["status"],
        "collection_date": f.get("collection_date"),
        "collection_venue": f.get("collection_venue"),
        "ot_schedule_day_id": str(f["ot_schedule_day_id"]) if f.get("ot_schedule_day_id") else None,
        "specs_collection_day_id": str(f["specs_collection_day_id"]) if f.get("specs_collection_day_id") else None,
        "collection_start_time": f.get("collection_start_time"),
        "collection_end_time": f.get("collection_end_time"),
        "medicine_outcomes": f.get("medicine_outcomes") or [],
        "issued_power_r": f.get("issued_power_r"),
        "issued_power_l": f.get("issued_power_l"),
        "created_at": iso(f.get("created_at")),
    }


def ser_slip(s: dict) -> Dict[str, Any]:
    return {
        "id": str(s["_id"]),
        "transcription_id": str(s["transcription_id"]),
        "item_type": s["item_type"],
        "version": s["version"],
        "active": s.get("active", True),
        "cancelled": s.get("cancelled", False),
        "collection_date": s.get("collection_date"),
        "collection_venue": s.get("collection_venue"),
        "collection_end_date": s.get("collection_end_date"),
        "collection_start_time": s.get("collection_start_time"),
        "collection_end_time": s.get("collection_end_time"),
        "instructions": s.get("instructions"),
        "created_at": iso(s.get("created_at")),
    }


def ser_ot_day(d: dict) -> Dict[str, Any]:
    return {
        "id": str(d["_id"]),
        "camp_id": str(d["camp_id"]),
        "day_date": d["day_date"],
        "venue": d["venue"],
        "venue_sms": d.get("venue_sms"),
        "seat_limit": d["seat_limit"],
        "seats_taken": d.get("seats_taken", 0),
        "seats_free": d["seat_limit"] - d.get("seats_taken", 0),
    }


def ser_specs_day(d: dict) -> Dict[str, Any]:
    start = d.get("start_time")
    end = d.get("end_time")
    complete = sms.specs_pickup_hours_match(start, end)
    return {
        "id": str(d["_id"]),
        "camp_id": str(d["camp_id"]),
        "day_date": d["day_date"],
        "end_date": d.get("end_date") or d["day_date"],
        "venue": d["venue"],
        "venue_sms": d.get("venue_sms"),
        "start_time": start,
        "end_time": end,
        "window_required": not complete,
    }


@router.get("/diagnosis-options")
async def diagnosis_options(actor: dict = Depends(require_any)) -> Dict[str, Any]:
    return {"options": DIAGNOSIS_OPTIONS}


async def _fetch_clinical_bundle(db: AsyncDatabase, patient: dict) -> Dict[str, Any]:
    person = await db.persons.find_one({"_id": patient["person_id"]}) if patient.get("person_id") else None
    trans = await db.transcriptions.find_one({"patient_id": patient["_id"]})
    fulfilments = await db.fulfilments.find({"transcription_id": trans["_id"]}).to_list(20) if trans else []
    slips = await db.deferred_slips.find({"transcription_id": trans["_id"], "active": True}).to_list(20) if trans else []
    return {
        "registration": ser_patient(patient),
        "person": ser_person(person) if person else None,
        "transcription": ser_trans(trans) if trans else None,
        "fulfilments": [ser_fulfil(f) for f in fulfilments],
        "slips": [ser_slip(s) for s in slips],
    }


@router.post("/lookup")
async def clinical_lookup(body: dict, actor: dict = Depends(require_clinical)) -> Dict[str, Any]:
    assert_clinical_operator(actor)
    db = get_db()
    camp = await db.camps.find_one({"is_active": True})
    value = parse_patient_identifier(body.get("value", ""))
    p = None
    if camp:
        p = await db.patients.find_one({"camp_id": camp["_id"], "patient_qr": value})
        if not p and value.isdecimal() and len(value) <= 12:
            p = await db.patients.find_one({"camp_id": camp["_id"], "reg_no": int(value)})
    if not p:
        raise HTTPException(status_code=404, detail="No matching registration found")
    gate = arrival_ready(p)
    if gate == "not_arrived":
        raise HTTPException(status_code=409, detail={
            "code": "not_arrived",
            "message": "This patient has not arrived at the door yet.",
        })
    if gate == "never_printed":
        raise HTTPException(status_code=409, detail={
            "code": "never_printed",
            "message": "This patient's prescription was never printed.",
        })
    bundle = await _fetch_clinical_bundle(db, p)
    rev = None
    if p.get("committed_revision_id"):
        rev = await db.prescription_revisions.find_one({"_id": p["committed_revision_id"]})
    bundle["committed_revision"] = serialize_revision(rev)
    bundle["clinical_generation"] = generation_of(p)
    return bundle


@router.get("/search")
async def clinical_search(q: str, actor: dict = Depends(require_clinical)) -> Dict[str, Any]:
    assert_clinical_operator(actor)
    db = get_db()
    camp = await db.camps.find_one({"is_active": True})
    norm = normalize_name(q)
    if not camp or not norm:
        return {"results": []}
    patients = await db.patients.find({
        "camp_id": camp["_id"],
        "full_name_normalized": {"$regex": "^" + norm},
        "arrived_at": {"$ne": None},
        "printed_at": {"$ne": None},
    }).sort("reg_no", 1).limit(20).to_list(20)
    return {"results": [{
        "id": str(p["_id"]),
        "reg_no": p.get("reg_no"),
        "full_name": p.get("full_name"),
        "age": p.get("age"),
        "gender_label": ser_patient(p)["gender_label"],
        "phone_last4": (normalize_phone(p.get("phone")) or "")[-4:],
    } for p in patients]}


def _content_from_body(body) -> dict:
    content = extract_content(body)
    content["ot_eye"] = normalize_ot_eye(content.get("ot_eye"))
    return content


async def _apply_catalogue(db, body, active_only: bool = True) -> None:
    """The catalogue is the authority: names and powers are resolved server-side, never trusted from the client."""
    body.prescribed_medicines = await resolve_medicines(db, body.prescribed_medicine_ids, active_only=active_only)
    body.fixed_power_r = await stocked_power(db, body.fixed_power_r, active_only=active_only)
    body.fixed_power_l = await stocked_power(db, body.fixed_power_l, active_only=active_only)


def _require_printed(p: dict) -> dict:
    gate = arrival_ready(p)
    if gate == "not_arrived":
        raise conflict("not_arrived", "This patient has not arrived at the door yet.")
    if gate == "never_printed":
        raise conflict("never_printed", "This patient's prescription was never printed.")
    return p


async def _require_printed_patient(db, patient_id: str) -> dict:
    p = await db.patients.find_one({"_id": ObjectId(patient_id)})
    if not p:
        raise HTTPException(status_code=404, detail="Registration not found")
    return _require_printed(p)


def _draft_version_match(version: int) -> Any:
    return {"$in": [None, 0]} if version <= 0 else version


def _draft_conflict() -> HTTPException:
    return conflict(
        "draft_version_conflict",
        "Another operator saved this prescription; reload before saving.",
    )


async def _upsert_transcription(
    db, patient: dict, actor: dict, content: dict, *, locked: bool,
    expected_version: Optional[int] = None, session=None,
) -> dict:
    existing = await db.transcriptions.find_one({"patient_id": patient["_id"]}, session=session)
    fields = {
        **content,
        "locked": locked,
        "updated_at": now_utc(),
    }
    if not existing:
        doc = {
            "patient_id": patient["_id"],
            "person_id": patient.get("person_id"),
            "camp_id": patient["camp_id"],
            "created_by": str(actor["_id"]),
            "created_at": now_utc(),
            "draft_version": 1,
            **fields,
        }
        try:
            res = await db.transcriptions.insert_one(doc, session=session)
            doc["_id"] = res.inserted_id
            return doc
        except DuplicateKeyError:
            raise _draft_conflict()
    query: Dict[str, Any] = {"_id": existing["_id"]}
    if not locked:
        query["locked"] = {"$ne": True}
        if expected_version is not None:
            query["draft_version"] = _draft_version_match(expected_version)
    t = await db.transcriptions.find_one_and_update(
        query, {"$set": fields, "$inc": {"draft_version": 1}}, return_document=True, session=session,
    )
    if not t:
        raise _draft_conflict()
    return t


def _clinical_result(patient: dict, revision: dict, transcription: dict | None) -> dict:
    return {
        "registration": ser_patient(patient),
        "revision": serialize_revision(revision),
        "transcription": ser_trans(transcription) if transcription else None,
    }


@router.post("/transcription")
async def create_transcription(
    body: TranscriptionBody,
    actor: dict = Depends(require_clinical),
) -> Dict[str, Any]:
    assert_clinical_operator(actor)
    db = get_db()
    p = await _require_printed_patient(db, body.patient_id)
    if p.get("committed_revision_id"):
        raise conflict("already_completed", "Use a correction to change a completed prescription.")
    await _apply_catalogue(db, body)
    content = _content_from_body(body)
    t = await _upsert_transcription(
        db, p, actor, content, locked=False, expected_version=body.expected_draft_version,
    )
    return {"transcription": ser_trans(t)}


@router.post("/transcription/complete")
async def complete_prescription(
    body: CompletePrescriptionBody,
    actor: dict = Depends(require_clinical),
) -> Dict[str, Any]:
    assert_clinical_operator(actor)
    db = get_db()
    replaying = await db.clinical_operations.find_one({"operation_id": body.operation_id}, {"_id": 1})
    await _apply_catalogue(db, body, active_only=not replaying)
    content, lines, none = validate_completion(body)
    p = await _require_printed_patient(db, body.patient_id)
    digest = payload_hash("complete", {
        "patient_id": str(p["_id"]), "content": content, "lines": lines, "none": none,
    })
    done = await recover_operation(db, body.operation_id, "complete", digest)
    if done:
        if str(p.get("committed_revision_id")) != done["result"]["revision"]["id"]:
            raise conflict("OPERATION_SUPERSEDED", "This completion was undone or replaced and cannot be replayed.")
        return done["result"]

    async def write(session):
        patient = await _claim_patient(db, p["_id"], session)
        replay = await recover_operation(db, body.operation_id, "complete", digest, session)
        if replay:
            return replay["result"], None
        _require_printed(patient)
        if patient.get("committed_revision_id"):
            raise conflict("already_completed", "This patient already has a completed prescription.")
        if generation_of(patient) != body.expected_generation:
            raise conflict("stale_generation", "The prescription changed; reload and retry.")
        transcription = await db.transcriptions.find_one({"patient_id": patient["_id"]}, session=session)
        if (
            transcription and body.expected_draft_version is not None
            and (transcription.get("draft_version") or 0) != max(body.expected_draft_version, 0)
        ):
            raise _draft_conflict()
        revision = await insert_revision(
            db, patient, actor, content, lines, none, body.operation_id, "complete", None, None, session,
        )
        committed = await commit_completion(db, patient, revision, actor, session)
        transcription = await _upsert_transcription(db, committed, actor, content, locked=True, session=session)
        result = _clinical_result(committed, revision, transcription)
        await record_operation(db, body.operation_id, "complete", digest, patient["_id"], result, session)
        return result, None

    result, _ = await _run_operation(db, body.operation_id, "complete", digest, write)
    return result


@router.post("/transcription/undo")
async def undo_completion(
    body: UndoCompletionBody,
    actor: dict = Depends(require_clinical),
) -> Dict[str, Any]:
    assert_clinical_operator(actor)
    reason = (body.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Undo requires a reason")
    db = get_db()
    p = await db.patients.find_one({"_id": ObjectId(body.patient_id)})
    if not p:
        raise HTTPException(status_code=404, detail="Registration not found")
    digest = payload_hash("undo", {"patient_id": str(p["_id"]), "reason": reason})
    done = await recover_operation(db, body.operation_id, "undo", digest)
    if done:
        if generation_of(p) != done["result"]["registration"]["clinical_generation"]:
            raise conflict("OPERATION_SUPERSEDED", "The prescription changed after this undo, which cannot be replayed.")
        return done["result"]

    async def write(session):
        patient = await _claim_patient(db, p["_id"], session)
        replay = await recover_operation(db, body.operation_id, "undo", digest, session)
        if replay:
            return replay["result"], None
        if await has_issue_history(db, patient, session):
            raise conflict("undo_after_issue", "Completion cannot be undone after an issue or pending issue.")
        if not patient.get("committed_revision_id"):
            raise conflict("not_completed", "There is no current completion to undo.")
        if generation_of(patient) != body.expected_generation:
            raise conflict("stale_generation", "The prescription changed; reload and retry.")
        updated = await commit_undo(db, patient, session)
        trans = await db.transcriptions.find_one_and_update(
            {"patient_id": patient["_id"]}, {"$set": {"locked": False}}, return_document=True, session=session,
        )
        result = {
            "registration": ser_patient(updated),
            "transcription": ser_trans(trans) if trans else None,
        }
        await record_operation(db, body.operation_id, "undo", digest, patient["_id"], result, session)
        return result, None

    result, _ = await _run_operation(db, body.operation_id, "undo", digest, write)
    return result


def _validate_fulfilment_matrix(item_type: str, status: str) -> None:
    valid = {
        "medicine": {"fulfilled", "not_available", "partially_fulfilled"},
        "specs_fixed": {"fulfilled"},
        "specs_made": {"deferred", "cancelled"},
        "ot": {"deferred", "declined"},
    }
    if item_type not in valid or status not in valid[item_type]:
        raise HTTPException(status_code=400, detail="Invalid fulfilment item/status")


def match_medicine_outcomes(revision: dict, outcomes) -> list[dict]:
    """Every prescribed medicine is accounted for exactly once, and names come from the revision."""
    prescribed = {m["medicine_id"]: m["name"] for m in (revision.get("prescribed_medicines") or [])}
    supplied = {o.medicine_id: bool(o.given) for o in (outcomes or [])}
    if not prescribed or len(supplied) != len(outcomes or []) or set(supplied) != set(prescribed):
        raise HTTPException(status_code=400, detail={
            "code": "MEDICINE_OUTCOMES_MISMATCH",
            "message": "Record given or not available for every prescribed medicine.",
        })
    return [{"medicine_id": mid, "name": name, "given": supplied[mid]} for mid, name in prescribed.items()]


def derive_medicine_status(outcomes: list[dict]) -> str:
    given = sum(1 for o in outcomes if o["given"])
    if given == len(outcomes):
        return "fulfilled"
    if given == 0:
        return "not_available"
    return "partially_fulfilled"


async def resolve_issued_powers(db, revision: dict, body: FulfilmentBody) -> tuple[float, float]:
    """A power that ran out is substituted at the desk; the prescribed power on the revision never moves."""
    right = body.issued_power_r if body.issued_power_r is not None else revision.get("fixed_power_r")
    left = body.issued_power_l if body.issued_power_l is not None else revision.get("fixed_power_l")
    if right is None or left is None:
        raise HTTPException(status_code=400, detail={
            "code": "FIXED_POWER_REQUIRED",
            "message": "Select the fixed power for both eyes before issuing.",
        })
    return await stocked_power(db, right, active_only=True), await stocked_power(db, left, active_only=True)


async def _consume_seat(collection: AsyncCollection, day_id: ObjectId, session) -> Optional[dict]:
    return await collection.find_one_and_update(
        {"_id": day_id,
         "$expr": {"$lt": ["$seats_taken", "$seat_limit"]}},
        {"$inc": {"seats_taken": 1}},
        return_document=True,
        session=session,
    )


SPECS_EXCLUSION = {
    "specs_fixed": ("specs_made", "Spectacles to be made"),
    "specs_made": ("specs_fixed", "Fixed-power specs"),
}

DEFERRAL_CONFIG = {
    "specs_made": {
        "id_field": "specs_collection_day_id",
        "collection_attr": "specs_collection_days",
        "missing_err": "Spectacles to be made deferral needs a Specs collection day",
        "full_err": "Specs collection day is not available",
        "none_free_err": "No Specs collection day is scheduled.",
        "instructions": "Collect spectacles on the scheduled date.",
        "slip_kwarg": "specs_collection_day_id",
        "message_type": "specs_token",
    },
    "ot": {
        "id_field": "ot_schedule_day_id",
        "collection_attr": "ot_schedule_days",
        "missing_err": "OT deferral needs a scheduled day",
        "full_err": "OT day is full or not found",
        "none_free_err": "Every OT Schedule Day is full. Call the admin to add an OT Schedule Day.",
        "instructions": "पर्चा, यह टोकन, आधार कार्ड, राशन कार्ड और मोबाइल फ़ोन साथ लाएँ। सहायता: 9835317006",
        "slip_kwarg": "ot_schedule_day_id",
        "message_type": "ot_token",
    },
}


async def _refuse_full(collection: AsyncCollection, day: dict, cfg: dict, session) -> NoReturn:
    """A single full day is a retry; every day of the type from today on full is an admin problem."""
    free = await collection.count_documents({
        "camp_id": day.get("camp_id"),
        "day_date": {"$gte": now_ist().date().isoformat()},
        "$expr": {"$lt": ["$seats_taken", "$seat_limit"]},
    }, session=session)
    if free == 0:
        raise HTTPException(status_code=409, detail={
            "code": "NO_CLINICAL_DAY_AVAILABLE",
            "message": cfg["none_free_err"],
        })
    raise HTTPException(status_code=409, detail=cfg["full_err"])


def _assert_specs_prescription(item_type: str, transcription: dict) -> None:
    """Made specs are ground from the grid; fixed specs are picked from the camp's stocked powers."""
    if item_type == "specs_made":
        m = transcription.get("specs_measurements") or {}
        if not (str(m.get("r_sph") or "").strip() and str(m.get("l_sph") or "").strip()):
            raise HTTPException(status_code=400, detail={
                "code": "SPECS_MEASUREMENTS_REQUIRED",
                "message": "Record the prescribed power for both eyes before recording a spectacles line.",
            })
    elif item_type == "specs_fixed":
        if transcription.get("fixed_power_r") is None or transcription.get("fixed_power_l") is None:
            raise HTTPException(status_code=400, detail={
                "code": "FIXED_POWER_REQUIRED",
                "message": "Select the fixed power for both eyes before recording a spectacles line.",
            })


def _oid_or_400(raw: str) -> ObjectId:
    try:
        return ObjectId(raw)
    except (InvalidId, TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid schedule day")


def _specs_window_selectable(day: dict) -> bool:
    start = day.get("start_time")
    end = day.get("end_time")
    if not sms.specs_pickup_hours_match(start, end):
        return False
    try:
        return ist_local_instant(day.get("end_date") or day["day_date"], sms.SPECS_PICKUP_END_TIME) > now_ist()
    except (ValueError, TypeError):
        return False


async def _load_deferral_day(
    db: AsyncDatabase, patient: dict, body: FulfilmentBody, cfg: dict, prior: dict | None, session,
) -> dict:
    target_day_id = getattr(body, cfg["id_field"])
    if not target_day_id:
        raise HTTPException(status_code=400, detail=cfg["missing_err"])
    oid = _oid_or_400(target_day_id)
    collection = getattr(db, cfg["collection_attr"])
    target = await collection.find_one({"_id": oid}, session=session)
    if body.item_type == "specs_made":
        if not target:
            raise HTTPException(status_code=400, detail=cfg["full_err"])
        if target.get("camp_id") != patient.get("camp_id"):
            raise HTTPException(status_code=400, detail="Specs collection day belongs to another camp")
        if not _specs_window_selectable(target):
            raise HTTPException(status_code=400, detail="Specs collection window is not selectable")
        return target
    if not target:
        raise HTTPException(status_code=409, detail=cfg["full_err"])
    if target.get("day_date", "") < now_ist().date().isoformat():
        raise HTTPException(status_code=400, detail="Surgery date has passed; choose today or a later day")
    if target.get("camp_id") != patient.get("camp_id"):
        raise HTTPException(status_code=400, detail="Schedule day belongs to another camp")
    if prior and prior.get("status") == "deferred" and prior.get(cfg["id_field"]) == oid:
        return target
    day = await _consume_seat(collection, oid, session)
    if not day:
        await _refuse_full(collection, target, cfg, session)
    return day


async def _process_deferral(
    db: AsyncDatabase, patient: dict, t: dict, body: FulfilmentBody, prior: dict | None, session,
) -> Optional[dict]:
    if body.status != "deferred" or body.item_type not in DEFERRAL_CONFIG:
        return None
    cfg = DEFERRAL_CONFIG[body.item_type]
    day = await _load_deferral_day(db, patient, body, cfg, prior, session)
    specs = body.item_type == "specs_made"
    return await _make_slip(
        db, t, body.item_type, day["day_date"], day["venue"], cfg["instructions"], session,
        venue_sms=day.get("venue_sms"),
        end_date=(day.get("end_date") or day["day_date"]) if specs else None,
        start_time=day.get("start_time") if specs else None,
        end_time=day.get("end_time") if specs else None,
        **{cfg["slip_kwarg"]: day["_id"]},
    )


async def persist_fulfilment(db: AsyncDatabase, prior: dict | None, doc: dict, session) -> dict:
    if prior:
        await db.fulfilments.update_one({"_id": prior["_id"]}, {"$set": doc}, session=session)
        doc["_id"] = prior["_id"]
        return doc
    res = await db.fulfilments.insert_one(doc, session=session)
    doc["_id"] = res.inserted_id
    return doc


def _deferred_day_id(body: FulfilmentBody, item_type: str) -> Optional[ObjectId]:
    """A day is only booked for the line that owns it: a specs_made line never holds an OT seat."""
    if body.status != "deferred" or body.item_type != item_type:
        return None
    raw = getattr(body, DEFERRAL_CONFIG[item_type]["id_field"])
    return ObjectId(raw) if raw else None


def _build_fulfilment_doc(
    body: FulfilmentBody,
    transcription_id: ObjectId | str,
    slip: dict | None,
    actor_id: str,
    medicine_outcomes: list[dict] | None = None,
    issued_powers: tuple[float, float] | None = None,
) -> dict:
    return {
        "transcription_id": transcription_id,
        "item_type": body.item_type,
        "status": body.status,
        "medicine_outcomes": medicine_outcomes,
        "issued_power_r": issued_powers[0] if issued_powers else None,
        "issued_power_l": issued_powers[1] if issued_powers else None,
        "collection_date": (slip or {}).get("collection_date"),
        "collection_venue": (slip or {}).get("collection_venue"),
        "ot_schedule_day_id": _deferred_day_id(body, "ot"),
        "specs_collection_day_id": _deferred_day_id(body, "specs_made"),
        "collection_start_time": (slip or {}).get("collection_start_time"),
        "collection_end_time": (slip or {}).get("collection_end_time"),
        "created_by": actor_id,
        "created_at": now_utc(),
    }


@router.post("/fulfilment")
async def record_fulfilment(
    body: FulfilmentBody,
    background_tasks: BackgroundTasks,
    actor: dict = Depends(require_clinical),
) -> Dict[str, Any]:
    assert_clinical_operator(actor)
    db = get_db()
    t = await db.transcriptions.find_one({"_id": ObjectId(body.transcription_id)})
    if not t:
        raise HTTPException(status_code=404, detail="Transcription not found")
    patient = await db.patients.find_one({"_id": t["patient_id"]}) if t.get("patient_id") else None
    if not patient:
        raise HTTPException(status_code=404, detail="Registration not found")
    if not patient.get("committed_revision_id") or patient.get("queue_status") != "seen":
        raise conflict("not_completed", "Issue requires a completed prescription.")
    if not body.paper_reviewed or not body.reviewed_revision_id or body.reviewed_generation is None:
        raise conflict("review_required", "Confirm the paper against the saved prescription before issuing.")
    if str(patient["committed_revision_id"]) != body.reviewed_revision_id or generation_of(patient) != body.reviewed_generation:
        raise conflict("stale_review", "The reviewed prescription is no longer current. Review the paper again.")
    revision = await db.prescription_revisions.find_one({"_id": patient["committed_revision_id"]})
    if not revision:
        raise conflict("not_completed", "Issue requires a completed prescription.")
    if str(revision.get("patient_id")) != str(patient["_id"]):
        raise HTTPException(status_code=404, detail="Transcription not found")
    if body.item_type not in PRESCRIBED_LINE_KEYS:
        raise HTTPException(status_code=400, detail="Invalid fulfilment item/status")
    if revision.get("none_prescribed") or body.item_type not in (revision.get("prescribed_lines") or []):
        raise conflict("line_not_prescribed", "This line is not prescribed on the completed prescription.")
    if body.item_type == "ot" and revision.get("ot_outcome") != "iol_surgery":
        raise conflict("hospital_referral", "A Hospital referral is complete once the prescription is saved; nothing is recorded at the Hospital station.")
    medicine_outcomes = None
    issued_powers = None
    if body.item_type == "medicine":
        medicine_outcomes = match_medicine_outcomes(revision, body.medicine_outcomes)
        body.status = derive_medicine_status(medicine_outcomes)
    elif body.item_type == "specs_fixed":
        issued_powers = await resolve_issued_powers(db, revision, body)
    _validate_fulfilment_matrix(body.item_type, body.status)
    digest = payload_hash("issue", body.model_dump(exclude={"operation_id"}))
    op_id = body.operation_id or str(ObjectId())
    done = await recover_operation(db, op_id, "issue", digest)
    if done:
        return done["result"]

    async def write(session):
        current = await _claim_patient(db, patient["_id"], session)
        replay = await recover_operation(db, op_id, "issue", digest, session)
        if replay:
            return replay["result"], None
        if not current.get("committed_revision_id") or current.get("queue_status") != "seen":
            raise conflict("not_completed", "Issue requires a completed prescription.")
        if str(current["committed_revision_id"]) != body.reviewed_revision_id or generation_of(current) != body.reviewed_generation:
            raise conflict("stale_review", "The reviewed prescription is no longer current. Review the paper again.")
        trans = await db.transcriptions.find_one({"_id": t["_id"]}, session=session)
        if not trans:
            raise HTTPException(status_code=404, detail="Transcription not found")
        other = SPECS_EXCLUSION.get(body.item_type)
        if other and await db.fulfilments.find_one(
            {"transcription_id": t["_id"], "item_type": other[0], "status": {"$ne": "cancelled"}}, session=session,
        ):
            raise HTTPException(status_code=409, detail={
                "code": "SPECS_LINE_EXCLUSIVE",
                "message": f"This patient already has a {other[1]} record.",
            })
        _assert_specs_prescription(body.item_type, trans)
        prior = await db.fulfilments.find_one({"transcription_id": t["_id"], "item_type": body.item_type}, session=session)
        slip = await _process_deferral(db, current, trans, body, prior, session)
        doc = _build_fulfilment_doc(body, t["_id"], slip, str(actor["_id"]), medicine_outcomes, issued_powers)
        doc.update({
            "operation_id": op_id,
            "reviewed_revision_id": current["committed_revision_id"],
            "reviewed_generation": generation_of(current),
            "slip_id": slip["_id"] if slip else None,
        })
        doc = await persist_fulfilment(db, prior, doc, session)
        if doc["status"] != "deferred":
            await db.deferred_slips.update_many(
                {"transcription_id": t["_id"], "item_type": doc["item_type"], "active": True},
                {"$set": {"active": False, "cancelled": True, "cancelled_at": now_utc()}},
                session=session,
            )
        old_ot = prior.get("ot_schedule_day_id") if prior and prior.get("status") == "deferred" else None
        if doc["item_type"] == "ot" and old_ot and old_ot != doc.get("ot_schedule_day_id"):
            await db.ot_schedule_days.update_one(
                {"_id": old_ot, "seats_taken": {"$gt": 0}}, {"$inc": {"seats_taken": -1}}, session=session,
            )
        sms_row = await sms.queue_patient_sms(
            db, current, DEFERRAL_CONFIG[doc["item_type"]]["message_type"],
            slip["collection_date"], slip.get("collection_venue_sms") or slip["collection_venue"],
            slip.get("collection_start_time"), slip.get("collection_end_time"), slip.get("collection_end_date"),
            event_key=str(slip["_id"]), session=session,
        ) if slip else None
        result = {"fulfilment": ser_fulfil(doc), "slip": ser_slip(slip) if slip else None}
        await record_operation(db, op_id, "issue", digest, patient["_id"], result, session)
        return result, sms_row

    result, sms_row = await _run_operation(db, op_id, "issue", digest, write)
    if sms_row:
        if background_tasks is not None:
            background_tasks.add_task(sms.send_queued, db, sms_row)
        else:
            await sms.send_queued(db, sms_row)
    return result


async def _make_slip(
    db: AsyncDatabase,
    t: dict,
    item_type: str,
    coll_date: str,
    venue: str,
    instructions: str,
    session,
    venue_sms: Optional[str] = None,
    ot_schedule_day_id: Optional[ObjectId | str] = None,
    specs_collection_day_id: Optional[ObjectId | str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict:
    count = await db.deferred_slips.count_documents({"transcription_id": t["_id"], "item_type": item_type}, session=session)
    doc = {
        "transcription_id": t["_id"],
        "patient_id": t["patient_id"],
        "item_type": item_type,
        "version": count + 1,
        "active": True,
        "cancelled": False,
        "collection_date": coll_date,
        "collection_venue": venue,
        "collection_venue_sms": venue_sms,
        "collection_end_date": end_date,
        "collection_start_time": start_time,
        "collection_end_time": end_time,
        "ot_schedule_day_id": ot_schedule_day_id,
        "specs_collection_day_id": specs_collection_day_id,
        "instructions": instructions,
        "created_at": now_utc(),
    }
    res = await db.deferred_slips.insert_one(doc, session=session)
    doc["_id"] = res.inserted_id
    await db.deferred_slips.update_many(
        {"transcription_id": t["_id"], "item_type": item_type, "active": True, "version": {"$lt": doc["version"]}},
        {"$set": {"active": False, "cancelled": True, "cancelled_at": now_utc()}},
        session=session,
    )
    return doc


@router.get("/slip/{slip_id}")
async def get_slip(slip_id: str, actor: dict = Depends(require_clinical)) -> Dict[str, Any]:
    assert_clinical_operator(actor)
    db = get_db()
    s = await db.deferred_slips.find_one({"_id": ObjectId(slip_id)})
    if not s:
        raise HTTPException(status_code=404, detail="Slip not found")
    p = await db.patients.find_one({"_id": s["patient_id"]})
    camp = await db.camps.find_one({"_id": p["camp_id"]}) if p and p.get("camp_id") else None
    surgery: dict = {}
    if s["item_type"] == "ot" and p and p.get("committed_revision_id"):
        surgery = await db.prescription_revisions.find_one({"_id": p["committed_revision_id"]}) or {}
    return {
        "slip": {**ser_slip(s), **{field: surgery.get(field) for field in ("ot_eye", "bp", "blood_sugar")}},
        "registration": ser_patient(p) if p else None,
        "camp_name": camp["name"] if camp else None,
    }


@router.post("/correction")
async def add_correction(
    body: CorrectionBody,
    actor: dict = Depends(require_clinical),
) -> Dict[str, Any]:
    assert_clinical_operator(actor)
    reason = (body.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Correction requires a reason")
    db = get_db()
    t = None
    if body.transcription_id:
        t = await db.transcriptions.find_one({"_id": ObjectId(body.transcription_id)})
        if not t:
            raise HTTPException(status_code=404, detail="Transcription not found")
    p = None
    if body.patient_id:
        p = await db.patients.find_one({"_id": ObjectId(body.patient_id)})
    elif t:
        p = await db.patients.find_one({"_id": t["patient_id"]})
    if not p:
        raise HTTPException(status_code=404, detail="Registration not found")
    if t and t.get("patient_id") != p["_id"]:
        raise HTTPException(status_code=404, detail="Transcription not found")
    op_id = body.operation_id or str(ObjectId())
    base_id = p.get("committed_revision_id")
    if not base_id:
        raise conflict("not_completed", "There is no current completion to correct.")
    current = await db.prescription_revisions.find_one({"_id": base_id}) or {}
    merged = {field: current.get(field) for field in CONTENT_FIELDS}
    for field in ("diagnosis_options", "prescribed_medicines"):
        if merged[field] is None:
            merged[field] = []
    for key, value in (body.changes or {}).items():
        if key in merged:
            merged[key] = value
    for field in merged:
        if field in body.model_fields_set:
            merged[field] = getattr(body, field)
    if "prescribed_medicine_ids" in body.model_fields_set:
        merged["prescribed_medicines"] = [{"medicine_id": mid} for mid in body.prescribed_medicine_ids]
    lines = list(body.prescribed_lines if "prescribed_lines" in body.model_fields_set else current.get("prescribed_lines") or [])
    none = body.none_prescribed if "none_prescribed" in body.model_fields_set else bool(current.get("none_prescribed") and not lines)
    confirmed = body.full_transcription_confirmed or bool(body.changes)
    try:
        view = CompletePrescriptionBody.model_validate({
            **merged, "patient_id": str(p["_id"]), "operation_id": op_id,
            "full_transcription_confirmed": confirmed, "prescribed_lines": lines, "none_prescribed": none,
        })
    except ValidationError:
        raise HTTPException(status_code=400, detail="Invalid prescription correction")
    view.prescribed_medicines = await resolve_medicines(
        db, [m.get("medicine_id") for m in view.prescribed_medicines], active_only=False,
    )
    view.fixed_power_r = await stocked_power(db, view.fixed_power_r, active_only=False)
    view.fixed_power_l = await stocked_power(db, view.fixed_power_l, active_only=False)
    content, lines, none = validate_completion(view)
    digest = payload_hash("correct", {
        "patient_id": str(p["_id"]), "content": content, "reason": body.reason,
        "lines": lines, "none": none,
    })
    done = await recover_operation(db, op_id, "correct", digest)
    if done:
        return done["result"]
    still_iol = "ot" in lines and content.get("ot_outcome") == "iol_surgery"
    same_specs = "specs_made" in lines and content.get("specs_measurements") == current.get("specs_measurements")

    async def write(session):
        patient = await _claim_patient(db, p["_id"], session)
        replay = await recover_operation(db, op_id, "correct", digest, session)
        if replay:
            return replay["result"], None
        if generation_of(patient) != body.expected_generation or patient.get("committed_revision_id") != base_id:
            raise conflict("stale_generation", "The prescription changed; reload and retry.")
        trans = await db.transcriptions.find_one({"patient_id": patient["_id"]}, session=session)
        if trans and not still_iol and await db.fulfilments.find_one(
            {"transcription_id": trans["_id"], "item_type": "ot", "status": "deferred"}, session=session,
        ):
            raise conflict("surgery_scheduled", "Record Surgery declined at the Hospital station before changing a scheduled IOL surgery.")
        if trans and not same_specs and await db.deferred_slips.find_one(
            {"transcription_id": trans["_id"], "item_type": "specs_made", "active": True}, session=session,
        ):
            raise conflict("SPECS_SCHEDULED", "Cancel the Spectacles to be made order at the Spectacles station before changing it.")
        revision = await insert_revision(db, patient, actor, content, lines, none, op_id, "correct", reason, base_id, session)
        committed = await commit_correction(db, patient, revision, session)
        trans = await _upsert_transcription(db, committed, actor, content, locked=True, session=session)
        result = _clinical_result(committed, revision, trans)
        await record_operation(db, op_id, "correct", digest, patient["_id"], result, session)
        return result, None

    result, _ = await _run_operation(db, op_id, "correct", digest, write)
    return result


@router.get("/history/{person_id}")
async def clinical_history(person_id: str, actor: dict = Depends(require_clinical)) -> Dict[str, Any]:
    assert_clinical_operator(actor)
    db = get_db()
    items = await db.transcriptions.find({"person_id": ObjectId(person_id)}).sort("created_at", -1).to_list(100)
    patients = await db.patients.find({"_id": {"$in": list({t["patient_id"] for t in items})}}).to_list(100)
    camps = await db.camps.find({"_id": {"$in": list({t["camp_id"] for t in items if t.get("camp_id")})}}).to_list(100)
    patient_by_id = {p["_id"]: p for p in patients}
    camp_by_id = {c["_id"]: c for c in camps}
    out = []
    for t in items:
        p = patient_by_id.get(t["patient_id"])
        camp = camp_by_id.get(t.get("camp_id"))
        out.append({
            "transcription": ser_trans(t),
            "camp_name": camp["name"] if camp else None,
            "reg_no": p["reg_no"] if p else None,
        })
    return {"history": out}


# ---- OT schedule ----
@router.post("/ot-days")
async def create_ot_day(body: OtScheduleBody, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    camp_id = _oid_or_400(body.camp_id)
    try:
        day_date = datetime.strptime(body.day_date, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid day_date")
    if day_date.isoformat() != body.day_date or day_date < now_ist().date():
        raise HTTPException(status_code=400, detail="Surgery date must be today or later")
    if body.seat_limit <= 0:
        raise HTTPException(status_code=400, detail="Seat limit must be positive")
    venue = (body.venue or "").strip()
    if not venue:
        raise HTTPException(status_code=400, detail="Venue is required")
    venue_sms = body.venue_sms
    if not await db.camps.find_one({"_id": camp_id, "is_active": True}):
        raise HTTPException(status_code=400, detail="Camp is not active")
    existing = await db.ot_schedule_days.find_one({"camp_id": camp_id, "day_date": body.day_date})
    if existing:
        assigned = existing.get("seats_taken", 0)
        if body.seat_limit < assigned:
            raise HTTPException(status_code=409, detail={
                "code": "SEAT_LIMIT_BELOW_ASSIGNED",
                "message": f"Cannot set below {assigned} already-assigned seats",
            })
        d = await db.ot_schedule_days.find_one_and_update(
            {"_id": existing["_id"], "seats_taken": {"$lte": body.seat_limit}},
            {"$set": {"seat_limit": body.seat_limit, "venue": venue, "venue_sms": venue_sms}},
            return_document=True,
        )
        if not d:
            raise HTTPException(status_code=409, detail="Seats changed; reload before reducing capacity")
    else:
        d = {
            "camp_id": camp_id, "day_date": body.day_date,
            "venue": venue, "venue_sms": venue_sms, "seat_limit": body.seat_limit, "seats_taken": 0,
            "created_at": now_utc(),
        }
        d["_id"] = (await db.ot_schedule_days.insert_one(d)).inserted_id
    return {"ot_day": ser_ot_day(d)}


@router.get("/ot-days")
async def list_ot_days(actor: dict = Depends(require_any)) -> Dict[str, Any]:
    db = get_db()
    camp = await db.camps.find_one({"is_active": True})
    if not camp:
        return {"ot_days": []}
    days = await db.ot_schedule_days.find({
        "camp_id": camp["_id"], "day_date": {"$gte": now_ist().date().isoformat()},
    }).sort("day_date", 1).to_list(100)
    return {"ot_days": [ser_ot_day(d) for d in days]}


@router.patch("/ot-days/{day_id}")
async def update_ot_day(day_id: str, body: OtScheduleBody, background_tasks: BackgroundTasks,
                        actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    camp_id = _oid_or_400(body.camp_id)
    oid = _oid_or_400(day_id)
    day = await db.ot_schedule_days.find_one({"_id": oid, "camp_id": camp_id})
    if not day:
        raise HTTPException(status_code=404, detail="OT day not found")
    try:
        date = datetime.strptime(body.day_date, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid day_date")
    if date.isoformat() != body.day_date or date < now_ist().date() or day["day_date"] < now_ist().date().isoformat():
        raise HTTPException(status_code=409, detail="Past OT days cannot be edited")
    if body.seat_limit <= 0:
        raise HTTPException(status_code=400, detail="Seat limit must be positive")
    venue = (body.venue or "").strip()
    if not venue:
        raise HTTPException(status_code=400, detail="Venue is required")
    if body.seat_limit < day.get("seats_taken", 0):
        raise HTTPException(status_code=409, detail={
            "code": "SEAT_LIMIT_BELOW_ASSIGNED",
            "message": f"Cannot set below {day.get('seats_taken', 0)} already-assigned seats",
        })
    date_changed = body.day_date != day["day_date"]
    if date_changed:
        if await db.ot_schedule_days.find_one({"camp_id": camp_id, "day_date": body.day_date}):
            raise HTTPException(status_code=409, detail="Another OT day already uses that date")
    revision = str(ObjectId()) if date_changed else day.get("edit_revision")
    updates = {"day_date": body.day_date, "seat_limit": body.seat_limit,
               "venue": venue, "venue_sms": body.venue_sms}
    if date_changed:
        updates["edit_revision"] = revision
    try:
        changed = await db.ot_schedule_days.find_one_and_update(
            {"_id": oid, "day_date": day["day_date"], "seats_taken": {"$lte": body.seat_limit}},
            {"$set": updates},
            return_document=True,
        )
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Another OT day already uses that date")
    if not changed:
        raise HTTPException(status_code=409, detail="Seats or date changed; reload and try again")
    if changed.get("edit_revision") or venue != day["venue"] or body.venue_sms != day.get("venue_sms"):
        slips = await db.deferred_slips.find({"ot_schedule_day_id": oid, "active": True}).to_list(None)
        fields = {"collection_date": body.day_date, "collection_venue": venue,
                  "collection_venue_sms": body.venue_sms}
        await db.deferred_slips.update_many({"ot_schedule_day_id": oid, "active": True}, {"$set": fields})
        await db.fulfilments.update_many({"ot_schedule_day_id": oid, "status": "deferred"}, {"$set": fields})
        if changed.get("edit_revision"):
            event_key = f"ot_day:{day_id}:{changed['edit_revision']}"
            for patient_id in {slip["patient_id"] for slip in slips}:
                patient = await db.patients.find_one({"_id": patient_id})
                if patient:
                    args = (db, patient, "ot_token", body.day_date, body.venue_sms or venue)
                    if background_tasks is not None:
                        background_tasks.add_task(sms.send_patient_sms, *args, event_key=event_key)
                    else:
                        await sms.send_patient_sms(*args, event_key=event_key)
    return {"ot_day": ser_ot_day(changed)}


def _validated_specs_window(body: SpecsScheduleBody) -> tuple[ObjectId, str, str, str, str, str]:
    venue = (body.venue or "").strip()
    if not venue:
        raise HTTPException(status_code=400, detail="Venue is required")
    try:
        camp_oid = ObjectId(body.camp_id)
    except (InvalidId, TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid camp id")
    end_date = body.end_date or body.day_date
    try:
        first_day = datetime.strptime(body.day_date, "%Y-%m-%d")
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid day_date")
    try:
        last_day = datetime.strptime(end_date, "%Y-%m-%d")
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid end_date")
    if last_day < first_day:
        raise HTTPException(status_code=400, detail="end_date must not be before day_date")
    start = sms.SPECS_PICKUP_START_TIME
    end = sms.SPECS_PICKUP_END_TIME
    if body.start_time not in (None, start) or body.end_time not in (None, end):
        raise HTTPException(status_code=400, detail="Specs collection hours are fixed at 10:00–17:00")
    if ist_local_instant(end_date, end) <= now_ist():
        raise HTTPException(status_code=400, detail="Window end must be after now")
    return camp_oid, body.day_date, end_date, venue, start, end


@router.post("/specs-days")
async def create_specs_day(body: SpecsScheduleBody, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    camp_oid, day_date, end_date, venue, start, end = _validated_specs_window(body)
    camp = await db.camps.find_one({"_id": camp_oid, "is_active": True})
    if not camp:
        raise HTTPException(status_code=400, detail="Camp is not active")
    existing = await db.specs_collection_days.find_one({"camp_id": camp_oid, "day_date": day_date})
    fields = {"end_date": end_date, "venue": venue, "venue_sms": body.venue_sms, "start_time": start, "end_time": end}
    if existing:
        await db.specs_collection_days.update_one({"_id": existing["_id"]}, {"$set": fields})
        d = await db.specs_collection_days.find_one({"_id": existing["_id"]})
    else:
        res = await db.specs_collection_days.insert_one({
            "camp_id": camp_oid, "day_date": day_date, **fields, "created_at": now_utc(),
        })
        d = await db.specs_collection_days.find_one({"_id": res.inserted_id})
    if not d:
        raise HTTPException(status_code=404, detail="Specs collection day not found")
    return {"specs_day": ser_specs_day(d)}


@router.get("/specs-days")
async def list_specs_days(actor: dict = Depends(require_any)) -> Dict[str, Any]:
    db = get_db()
    camp = await db.camps.find_one({"is_active": True})
    if not camp:
        return {"specs_days": []}
    days = await db.specs_collection_days.find({"camp_id": camp["_id"]}).sort("day_date", 1).to_list(100)
    return {"specs_days": [ser_specs_day(d) for d in days]}
