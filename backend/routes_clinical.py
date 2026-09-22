from contextlib import asynccontextmanager, nullcontext
from datetime import datetime, timedelta
from typing import Any, Dict, NoReturn, Optional
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pymongo.errors import DuplicateKeyError
from pydantic import ValidationError
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from db import get_db
from models import (
    TranscriptionBody, FulfilmentBody, CorrectionBody, OtScheduleBody, SpecsScheduleBody,
    CompletePrescriptionBody, UndoCompletionBody,
)
from catalogue import resolve_medicines, stocked_power
from clinical_state import (
    CONTENT_FIELDS,
    PRESCRIBED_LINE_KEYS, assert_clinical_operator, arrival_ready, begin_issue_authorization, commit_completion,
    commit_correction, commit_undo, conflict, extract_content, normalize_ot_eye,
    generation_of, has_issue_history, payload_hash, prepare_revision, recover_operation,
    release_issue_authorization, save_operation, serialize_revision, validate_completion,
)
from helpers import (
    now_utc, iso, DIAGNOSIS_OPTIONS, now_ist, parse_hhmm, ist_local_instant,
    normalize_name, normalize_phone, parse_patient_identifier,
)
from bson.errors import InvalidId
from serializers import ser_patient, ser_person
from security import require_clinical, require_admin, require_any
import sms

router = APIRouter(prefix="/api/clinical", tags=["clinical"])


@asynccontextmanager
async def _clinical_write(db: AsyncIOMotorDatabase, transcription_id: str):
    token = str(ObjectId())
    claimed = await db.transcriptions.find_one_and_update(
        {"_id": ObjectId(transcription_id), "$or": [
            {"clinical_write_token": None}, {"clinical_write_until": {"$lte": now_utc()}},
        ]},
        {"$set": {"clinical_write_token": token, "clinical_write_until": now_utc() + timedelta(minutes=2)}},
        return_document=True,
    )
    if not claimed:
        exists = await db.transcriptions.find_one({"_id": ObjectId(transcription_id)})
        raise HTTPException(status_code=409 if exists else 404,
                            detail="Another operator is saving this prescription; reload and retry" if exists else "Transcription not found")
    try:
        yield
    finally:
        await db.transcriptions.update_one(
            {"_id": ObjectId(transcription_id), "clinical_write_token": token},
            {"$set": {"clinical_write_token": None, "clinical_write_until": None}},
        )


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
    complete = bool(start and end)
    return {
        "id": str(d["_id"]),
        "camp_id": str(d["camp_id"]),
        "day_date": d["day_date"],
        "venue": d["venue"],
        "start_time": start,
        "end_time": end,
        "window_required": not complete,
    }


@router.get("/diagnosis-options")
async def diagnosis_options(actor: dict = Depends(require_any)) -> Dict[str, Any]:
    return {"options": DIAGNOSIS_OPTIONS}


async def _fetch_clinical_bundle(db: AsyncIOMotorDatabase, patient: dict) -> Dict[str, Any]:
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
        if not p and value.isdigit() and int(value) < 2 ** 63:
            p = await db.patients.find_one({"camp_id": camp["_id"], "reg_no": int(value)})
    if not p:
        raise HTTPException(status_code=404, detail="No matching registration found")
    gate = arrival_ready(p)
    if gate == "not_arrived":
        raise HTTPException(status_code=409, detail={
            "code": "not_arrived",
            "message": "This registration has not been checked in.",
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


async def _apply_catalogue(db, body) -> None:
    """The catalogue is the authority: names and powers are resolved server-side, never trusted from the client."""
    body.prescribed_medicines = await resolve_medicines(db, body.prescribed_medicine_ids)
    body.fixed_power_r = await stocked_power(db, body.fixed_power_r)
    body.fixed_power_l = await stocked_power(db, body.fixed_power_l)


async def _require_printed_patient(db, patient_id: str) -> dict:
    p = await db.patients.find_one({"_id": ObjectId(patient_id)})
    if not p:
        raise HTTPException(status_code=404, detail="Registration not found")
    gate = arrival_ready(p)
    if gate == "not_arrived":
        raise conflict("not_arrived", "This registration has not been checked in.")
    if gate == "never_printed":
        raise conflict("never_printed", "This patient's prescription was never printed.")
    return p


def _draft_version_match(version: int) -> Any:
    return {"$in": [None, 0]} if version <= 0 else version


def _draft_conflict() -> HTTPException:
    return conflict(
        "draft_version_conflict",
        "Another operator saved this prescription; reload before saving.",
    )


async def _upsert_transcription(
    db, patient: dict, actor: dict, content: dict, *, locked: bool,
    expected_version: Optional[int] = None,
) -> dict:
    existing = await db.transcriptions.find_one({"patient_id": patient["_id"]})
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
            res = await db.transcriptions.insert_one(doc)
            doc["_id"] = res.inserted_id
            return doc
        except DuplicateKeyError:
            raise _draft_conflict()
    query: Dict[str, Any] = {"_id": existing["_id"]}
    if not locked:
        query.update({
            "locked": {"$ne": True},
            "$or": [
                {"clinical_write_token": None}, {"clinical_write_until": {"$lte": now_utc()}},
            ],
        })
        if expected_version is not None:
            query["draft_version"] = _draft_version_match(expected_version)
    t = await db.transcriptions.find_one_and_update(
        query, {"$set": fields, "$inc": {"draft_version": 1}}, return_document=True,
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
    await _apply_catalogue(db, body)
    content, lines, none = validate_completion(body)
    p = await _require_printed_patient(db, body.patient_id)
    digest = payload_hash("complete", {
        "patient_id": str(p["_id"]), "content": content, "lines": lines, "none": none,
    })
    existing_op = await recover_operation(db, body.operation_id, "complete", digest)
    if existing_op and existing_op.get("status") == "committed" and existing_op.get("result"):
        return existing_op["result"]
    if existing_op and existing_op.get("status") == "superseded":
        raise conflict("operation_superseded", "This completion was undone and cannot be replayed.")
    if p.get("committed_revision_id"):
        current = await db.prescription_revisions.find_one({"_id": p["committed_revision_id"]})
        if not current or current.get("operation_id") != body.operation_id:
            raise conflict("already_completed", "This patient already has a completed prescription.")
    revision = await prepare_revision(
        db, p, actor, content, lines, none, body.operation_id, "complete", None, None,
    )
    transcription = await db.transcriptions.find_one({"patient_id": p["_id"]})
    drafted_here = transcription is None
    if not transcription:
        transcription = await _upsert_transcription(
            db, p, actor, content, locked=False, expected_version=body.expected_draft_version,
        )
    async with _clinical_write(db, str(transcription["_id"])):
        current_patient = await _require_printed_patient(db, body.patient_id)
        committed: dict | None
        if current_patient.get("committed_revision_id") == revision["_id"]:
            if generation_of(current_patient) != body.expected_generation + 1:
                raise conflict("stale_generation", "The prescription changed; reload and retry.")
            committed = current_patient
        else:
            if not drafted_here and body.expected_draft_version is not None and not await db.transcriptions.find_one_and_update(
                {
                    "_id": transcription["_id"],
                    "draft_version": _draft_version_match(body.expected_draft_version),
                },
                {"$set": {"updated_at": now_utc()}},
            ):
                raise _draft_conflict()
            committed = await commit_completion(db, current_patient, revision, actor, body.expected_generation)
        if not committed:
            raise conflict("already_completed", "This patient already has a completed prescription.")
        transcription = await _upsert_transcription(db, committed, actor, content, locked=True)
        result = _clinical_result(committed, revision, transcription)
        await save_operation(db, {
            "operation_id": body.operation_id,
            "kind": "complete",
            "payload_hash": digest,
            "patient_id": p["_id"],
            "status": "committed",
            "result": result,
            "created_at": now_utc(),
        })
        return result


@router.post("/transcription/undo")
async def undo_completion(
    body: UndoCompletionBody,
    actor: dict = Depends(require_clinical),
) -> Dict[str, Any]:
    assert_clinical_operator(actor)
    if not (body.reason or "").strip():
        raise HTTPException(status_code=400, detail="Undo requires a reason")
    db = get_db()
    p = await db.patients.find_one({"_id": ObjectId(body.patient_id)})
    if not p:
        raise HTTPException(status_code=404, detail="Registration not found")
    trans = await db.transcriptions.find_one({"patient_id": p["_id"]})
    async with _clinical_write(db, str(trans["_id"])) if trans else nullcontext():
        if await has_issue_history(db, p):
            raise conflict("undo_after_issue", "Completion cannot be undone after an issue or pending issue.")
        p = await db.patients.find_one({"_id": p["_id"]})
        if not p:
            raise HTTPException(status_code=404, detail="Registration not found")
        digest = payload_hash("undo", {"patient_id": str(p["_id"]), "reason": body.reason.strip()})
        existing_op = await recover_operation(db, body.operation_id, "undo", digest)
        if existing_op and existing_op.get("status") == "committed" and existing_op.get("result"):
            return existing_op["result"]
        expected = body.expected_generation
        applied = (
            p.get("last_undo_operation_id") == body.operation_id
            and generation_of(p) == expected + 1
            and not p.get("committed_revision_id")
        )
        if applied:
            updated = p
            prior_id = (existing_op or {}).get("predecessor_revision_id")
        else:
            if not p.get("committed_revision_id"):
                raise conflict("not_completed", "There is no current completion to undo.")
            prior_id = p["committed_revision_id"]
            await save_operation(db, {
                "operation_id": body.operation_id,
                "kind": "undo",
                "payload_hash": digest,
                "patient_id": p["_id"],
                "status": "pending",
                "predecessor_revision_id": prior_id,
                "created_at": now_utc(),
            })
            updated = await commit_undo(db, p, expected, body.operation_id)
            if not updated:
                raise conflict("stale_generation", "The prescription changed; reload and retry.")
        if prior_id:
            prior_rev = await db.prescription_revisions.find_one({"_id": prior_id})
            if prior_rev and prior_rev.get("operation_id"):
                await db.clinical_operations.update_one(
                    {"operation_id": prior_rev["operation_id"]},
                    {"$set": {"status": "superseded"}},
                )
        trans = await db.transcriptions.find_one_and_update(
            {"patient_id": p["_id"]},
            {"$set": {"locked": False}},
            return_document=True,
        )
        result = {
            "registration": ser_patient(updated),
            "transcription": ser_trans(trans) if trans else None,
        }
        await save_operation(db, {
            "operation_id": body.operation_id,
            "kind": "undo",
            "payload_hash": digest,
            "patient_id": p["_id"],
            "status": "committed",
            "result": result,
            "predecessor_revision_id": prior_id,
            "created_at": now_utc(),
        })
        return result


def _validate_fulfilment_matrix(item_type: str, status: str) -> None:
    valid = {
        "medicine": {"fulfilled", "not_available", "partially_fulfilled"},
        "specs_fixed": {"fulfilled"},
        "specs_made": {"deferred"},
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
    return await stocked_power(db, right), await stocked_power(db, left)


async def _consume_seat(collection: AsyncIOMotorCollection, day_id: str) -> Optional[dict]:
    return await collection.find_one_and_update(
        {"_id": ObjectId(day_id),
         "$expr": {"$lt": ["$seats_taken", "$seat_limit"]}},
        {"$inc": {"seats_taken": 1}},
        return_document=True,
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


async def _refuse_full(collection: AsyncIOMotorCollection, day: dict, cfg: dict) -> NoReturn:
    """A single full day is a retry; every day of the type full is an admin problem."""
    free = await collection.count_documents({
        "camp_id": day.get("camp_id"),
        "$expr": {"$lt": ["$seats_taken", "$seat_limit"]},
    })
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
    if not start or not end:
        return False
    try:
        return ist_local_instant(day["day_date"], end) > now_ist()
    except (ValueError, TypeError):
        return False


async def _load_deferral_day(
    db: AsyncIOMotorDatabase, t: dict, body: FulfilmentBody, cfg: dict, prior: dict | None,
) -> dict:
    target_day_id = getattr(body, cfg["id_field"])
    if not target_day_id:
        raise HTTPException(status_code=400, detail=cfg["missing_err"])
    oid = _oid_or_400(target_day_id)
    collection = getattr(db, cfg["collection_attr"])
    patient = await db.patients.find_one({"_id": t["patient_id"]}) if t.get("patient_id") else None
    held = bool(
        prior
        and prior.get("status") == "deferred"
        and str(prior.get(cfg["id_field"])) == target_day_id
    )
    if body.item_type == "specs_made":
        day = await collection.find_one({"_id": oid})
        if not day:
            raise HTTPException(status_code=400, detail=cfg["full_err"])
        if patient and patient.get("camp_id") and day.get("camp_id") != patient["camp_id"]:
            raise HTTPException(status_code=400, detail="Specs collection day belongs to another camp")
        if not _specs_window_selectable(day):
            raise HTTPException(status_code=400, detail="Specs collection window is not selectable")
        return day
    target = await collection.find_one({"_id": oid})
    if not target:
        raise HTTPException(status_code=409, detail=cfg["full_err"])
    if target.get("day_date", "") < now_ist().date().isoformat():
        raise HTTPException(status_code=400, detail="Surgery date has passed; choose today or a later day")
    if patient and patient.get("camp_id") and target.get("camp_id") != patient["camp_id"]:
        raise HTTPException(status_code=400, detail="Schedule day belongs to another camp")
    if held:
        return target
    day = await _consume_seat(collection, target_day_id)
    if not day:
        await _refuse_full(collection, target, cfg)
    return day


async def _process_deferral(db: AsyncIOMotorDatabase, t: dict, body: FulfilmentBody, prior: dict | None = None) -> Optional[dict]:
    if body.status != "deferred" or body.item_type not in DEFERRAL_CONFIG:
        return None
    cfg = DEFERRAL_CONFIG[body.item_type]
    day = await _load_deferral_day(db, t, body, cfg, prior)
    slip_kwargs = {cfg["slip_kwarg"]: day["_id"]}
    start = day.get("start_time") if body.item_type == "specs_made" else None
    end = day.get("end_time") if body.item_type == "specs_made" else None
    try:
        return await _make_slip(
            t, body.item_type, day["day_date"], day["venue"], cfg["instructions"],
            venue_sms=day.get("venue_sms"),
            start_time=start, end_time=end, **slip_kwargs,
        )
    except Exception:
        if body.item_type == "ot" and (not prior or prior.get("ot_schedule_day_id") != day["_id"]):
            await db.ot_schedule_days.update_one(
                {"_id": day["_id"], "seats_taken": {"$gt": 0}}, {"$inc": {"seats_taken": -1}},
            )
        raise


async def persist_fulfilment(db: AsyncIOMotorDatabase, prior: dict | None, doc: dict) -> dict:
    if prior:
        await db.fulfilments.update_one({"_id": prior["_id"]}, {"$set": doc})
        doc["_id"] = prior["_id"]
        return doc
    res = await db.fulfilments.insert_one(doc)
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
        "collection_date": (slip or {}).get("collection_date") or body.collection_date,
        "collection_venue": (slip or {}).get("collection_venue") or body.collection_venue,
        "ot_schedule_day_id": _deferred_day_id(body, "ot"),
        "specs_collection_day_id": _deferred_day_id(body, "specs_made"),
        "collection_start_time": (slip or {}).get("collection_start_time"),
        "collection_end_time": (slip or {}).get("collection_end_time"),
        "created_by": actor_id,
        "created_at": now_utc(),
    }


async def _ensure_transcription_locked(db: AsyncIOMotorDatabase, transcription: dict) -> None:
    if not transcription.get("locked"):
        await db.transcriptions.update_one({"_id": transcription["_id"]}, {"$set": {"locked": True}})


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
    if str(patient["committed_revision_id"]) != str(body.reviewed_revision_id):
        raise conflict("stale_review", "The reviewed prescription is no longer current. Review the paper again.")
    if generation_of(patient) != body.reviewed_generation:
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
    digest = payload_hash("issue", body.model_dump(exclude={"operation_id"}))
    op_id = body.operation_id or str(ObjectId())
    body.operation_id = op_id
    operation = await save_operation(db, {
        "operation_id": op_id, "kind": "issue", "payload_hash": digest,
        "patient_id": patient["_id"], "status": "pending", "created_at": now_utc(),
    })
    if operation.get("status") == "committed" and operation.get("result"):
        if patient.get("issue_auth_op") == op_id:
            async with _clinical_write(db, body.transcription_id):
                await release_issue_authorization(db, patient["_id"], op_id)
        return operation["result"]
    async with _clinical_write(db, body.transcription_id):
        current_patient = await db.patients.find_one({"_id": patient["_id"]})
        if not current_patient:
            raise HTTPException(status_code=404, detail="Registration not found")
        if current_patient.get("issue_auth_op") != op_id:
            await begin_issue_authorization(
                db, current_patient, actor, body.item_type,
                patient["committed_revision_id"], generation_of(patient), op_id,
            )
        try:
            recovered = await recover_operation(db, op_id, "issue", digest)
            if recovered and recovered.get("status") == "committed" and recovered.get("result"):
                result = recovered["result"]
            else:
                prior_op = await db.fulfilments.find_one({"operation_id": op_id})
                if prior_op:
                    if (
                        prior_op.get("transcription_id") != t["_id"]
                        or prior_op.get("item_type") != body.item_type
                        or prior_op.get("payload_hash") != digest
                    ):
                        raise conflict("operation_conflict", "This operation id was used for a different request.")
                    slip = await db.deferred_slips.find_one({"_id": prior_op["slip_id"]}) if prior_op.get("slip_id") else None
                    result = await _finish_fulfilment(db, t, patient, prior_op, slip, background_tasks)
                else:
                    result = await _record_fulfilment(
                        body, actor, background_tasks, medicine_outcomes, issued_powers,
                    )
            await release_issue_authorization(db, patient["_id"], op_id)
            return result
        except Exception:
            exists = await db.fulfilments.find_one({"operation_id": op_id})
            if not exists:
                await release_issue_authorization(db, patient["_id"], op_id)
            raise


async def _record_fulfilment(
    body: FulfilmentBody,
    actor: dict,
    background_tasks: BackgroundTasks | None,
    medicine_outcomes: list[dict] | None = None,
    issued_powers: tuple[float, float] | None = None,
) -> Dict[str, Any]:
    db = get_db()
    t = await db.transcriptions.find_one({"_id": ObjectId(body.transcription_id)})
    if not t:
        raise HTTPException(status_code=404, detail="Transcription not found")
    patient = await db.patients.find_one({"_id": t["patient_id"]}) if t.get("patient_id") else None
    if not patient or not patient.get("committed_revision_id") or patient.get("queue_status") != "seen":
        raise HTTPException(status_code=409, detail={
            "code": "not_completed",
            "message": "Issue requires a completed prescription.",
        })

    _validate_fulfilment_matrix(body.item_type, body.status)
    _assert_specs_prescription(body.item_type, t)
    other = SPECS_EXCLUSION.get(body.item_type)
    if other:
        other_type, other_label = other
        clash = await db.fulfilments.find_one({"transcription_id": t["_id"], "item_type": other_type})
        if clash:
            raise HTTPException(status_code=409, detail={
                "code": "SPECS_LINE_EXCLUSIVE",
                "message": f"This patient already has a {other_label} record.",
            })
    prior = await db.fulfilments.find_one({"transcription_id": t["_id"], "item_type": body.item_type})
    prior_slips = await db.deferred_slips.find(
        {"transcription_id": t["_id"], "item_type": body.item_type, "active": True},
    ).to_list(20)
    slip = await _process_deferral(db, t, body, prior)

    doc = _build_fulfilment_doc(
        body, t["_id"], slip, str(actor["_id"]), medicine_outcomes, issued_powers,
    )
    doc["current"] = True
    doc.update({
        "operation_id": body.operation_id,
        "payload_hash": payload_hash("issue", body.model_dump(exclude={"operation_id"})),
        "reviewed_revision_id": patient["committed_revision_id"],
        "reviewed_generation": generation_of(patient),
    })
    old_ot = prior.get("ot_schedule_day_id") if prior and prior.get("status") == "deferred" else None
    new_ot = doc.get("ot_schedule_day_id")
    doc["previous_ot_schedule_day_id"] = old_ot
    doc["slip_id"] = slip["_id"] if slip else None
    try:
        doc = await persist_fulfilment(db, prior, doc)
    except Exception:
        if slip:
            await db.deferred_slips.update_one(
                {"_id": slip["_id"]}, {"$set": {"active": False, "cancelled": True}},
            )
        for prior_slip in prior_slips:
            await db.deferred_slips.update_one(
                {"_id": prior_slip["_id"]}, {"$set": {"active": True, "cancelled": False}},
            )
        held = old_ot == new_ot
        if body.item_type == "ot" and new_ot and not held:
            await db.ot_schedule_days.update_one(
                {"_id": new_ot, "seats_taken": {"$gt": 0}},
                {"$inc": {"seats_taken": -1}},
            )
        raise
    return await _finish_fulfilment(db, t, patient, doc, slip, background_tasks)


async def _finish_fulfilment(db, t: dict, patient: dict, doc: dict, slip: dict | None, background_tasks) -> dict:
    if doc["status"] != "deferred":
        await db.deferred_slips.update_many(
            {"transcription_id": t["_id"], "item_type": doc["item_type"], "active": True},
            {"$set": {"active": False, "cancelled": True, "cancelled_at": now_utc()}},
        )
    old_ot = doc.get("previous_ot_schedule_day_id")
    new_ot = doc.get("ot_schedule_day_id")
    if doc["item_type"] == "ot" and old_ot and old_ot != new_ot:
        release_key = "released_issues." + payload_hash("release", {"operation_id": doc["operation_id"]})
        await db.ot_schedule_days.update_one(
            {"_id": old_ot, "seats_taken": {"$gt": 0}, release_key: {"$ne": True}},
            {"$inc": {"seats_taken": -1}, "$set": {release_key: True}},
        )

    await _ensure_transcription_locked(db, t)
    if slip:
        args = (
            db, patient, DEFERRAL_CONFIG[doc["item_type"]]["message_type"],
            slip["collection_date"], slip.get("collection_venue_sms") or slip["collection_venue"],
            slip.get("collection_start_time"), slip.get("collection_end_time"),
        )
        if background_tasks is not None:
            background_tasks.add_task(sms.send_patient_sms, *args)
        else:
            await sms.send_patient_sms(*args)
    result = {"fulfilment": ser_fulfil(doc), "slip": ser_slip(slip) if slip else None}
    await save_operation(db, {
        "operation_id": doc["operation_id"], "kind": "issue", "payload_hash": doc["payload_hash"],
        "patient_id": patient["_id"], "status": "committed", "result": result,
    })
    return result


async def _make_slip(
    t: dict,
    item_type: str,
    coll_date: str,
    venue: str,
    instructions: str,
    venue_sms: Optional[str] = None,
    ot_schedule_day_id: Optional[ObjectId | str] = None,
    specs_collection_day_id: Optional[ObjectId | str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> dict:
    db = get_db()
    count = await db.deferred_slips.count_documents({"transcription_id": t["_id"], "item_type": item_type})
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
        "collection_start_time": start_time,
        "collection_end_time": end_time,
        "ot_schedule_day_id": ot_schedule_day_id,
        "specs_collection_day_id": specs_collection_day_id,
        "instructions": instructions,
        "created_at": now_utc(),
    }
    res = await db.deferred_slips.insert_one(doc)
    doc["_id"] = res.inserted_id
    await db.deferred_slips.update_many(
        {"transcription_id": t["_id"], "item_type": item_type, "active": True, "version": {"$lt": doc["version"]}},
        {"$set": {"active": False, "cancelled": True, "cancelled_at": now_utc()}},
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
    if not (body.reason or "").strip():
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
    if not t:
        t = await db.transcriptions.find_one({"patient_id": p["_id"]})
    if p.get("issue_auth_op"):
        raise conflict("issue_pending", "Another issue is already in progress for this patient.")
    op_id = body.operation_id or str(ObjectId())
    existing_revision = await db.prescription_revisions.find_one({"operation_id": op_id})
    if not p.get("committed_revision_id") and not existing_revision:
        raise conflict("not_completed", "There is no current completion to correct.")
    base_id = existing_revision.get("predecessor_id") if existing_revision else p.get("committed_revision_id")
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
    view.prescribed_medicines = await resolve_medicines(db, [m.get("medicine_id") for m in view.prescribed_medicines])
    view.fixed_power_r = await stocked_power(db, view.fixed_power_r)
    view.fixed_power_l = await stocked_power(db, view.fixed_power_l)
    content, lines, none = validate_completion(view)
    digest = payload_hash("correct", {
        "patient_id": str(p["_id"]), "content": content, "reason": body.reason,
        "lines": lines, "none": none,
    })
    existing_op = await recover_operation(db, op_id, "correct", digest)
    if existing_op and existing_op.get("status") == "committed" and existing_op.get("result"):
        return existing_op["result"]
    still_iol = "ot" in lines and content.get("ot_outcome") == "iol_surgery"
    if t and not still_iol and await db.fulfilments.find_one(
        {"transcription_id": t["_id"], "item_type": "ot", "status": "deferred"},
    ):
        raise conflict("surgery_scheduled", "Record Surgery declined at the Hospital station before changing a scheduled IOL surgery.")
    revision = await prepare_revision(
        db, p, actor, content, lines, none, op_id, "correct", body.reason.strip(),
        base_id,
    )
    async with _clinical_write(db, str(t["_id"])) if t else nullcontext():
        current_patient = await db.patients.find_one({"_id": p["_id"]})
        if not current_patient:
            raise HTTPException(status_code=404, detail="Registration not found")
        if current_patient.get("committed_revision_id") == revision["_id"]:
            if generation_of(current_patient) != body.expected_generation + 1:
                raise conflict("stale_generation", "The prescription changed; reload and retry.")
            committed = current_patient
        else:
            committed = await commit_correction(db, current_patient, revision, actor, body.expected_generation)
            if not committed:
                raise conflict("stale_generation", "The prescription changed; reload and retry.")
        trans = await _upsert_transcription(db, committed, actor, content, locked=True)
    if not await db.corrections.find_one({"revision_id": revision["_id"]}):
        await db.corrections.insert_one({
            "transcription_id": trans["_id"],
            "patient_id": p["_id"],
            "reason": body.reason,
            "changes": body.changes,
            "revision_id": revision["_id"],
            "created_by": str(actor["_id"]),
            "created_at": now_utc(),
        })
    result = _clinical_result(committed, revision, trans)
    result["correction_id"] = str(revision["_id"])
    await save_operation(db, {
        "operation_id": op_id,
        "kind": "correct",
        "payload_hash": digest,
        "patient_id": p["_id"],
        "status": "committed",
        "result": result,
        "created_at": now_utc(),
    })
    return result


@router.get("/corrections/{transcription_id}")
async def list_corrections(transcription_id: str, actor: dict = Depends(require_clinical)) -> Dict[str, Any]:
    assert_clinical_operator(actor)
    db = get_db()
    items = await db.corrections.find({"transcription_id": ObjectId(transcription_id)}).sort("created_at", 1).to_list(100)
    return {"corrections": [{
        "id": str(c["_id"]), "reason": c["reason"], "changes": c["changes"],
        "created_at": iso(c["created_at"]),
    } for c in items]}


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
    venue_sms = (body.venue_sms or "").strip() or None
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
        res = await db.ot_schedule_days.insert_one({
            "camp_id": camp_id, "day_date": body.day_date,
            "venue": venue, "venue_sms": venue_sms, "seat_limit": body.seat_limit, "seats_taken": 0,
            "created_at": now_utc(),
        })
        d = await db.ot_schedule_days.find_one({"_id": res.inserted_id})
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


def _validated_specs_window(body: SpecsScheduleBody) -> tuple[ObjectId, str, str, str, str]:
    venue = (body.venue or "").strip()
    if not venue:
        raise HTTPException(status_code=400, detail="Venue is required")
    try:
        camp_oid = ObjectId(body.camp_id)
    except (InvalidId, TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid camp id")
    try:
        datetime.strptime(body.day_date, "%Y-%m-%d")
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid day_date")
    try:
        start = parse_hhmm(body.start_time)
        end = parse_hhmm(body.end_time)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if start >= end:
        raise HTTPException(status_code=400, detail="start_time must be before end_time")
    if ist_local_instant(body.day_date, end) <= now_ist():
        raise HTTPException(status_code=400, detail="Window end must be after now")
    return camp_oid, body.day_date, venue, start, end


@router.post("/specs-days")
async def create_specs_day(body: SpecsScheduleBody, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    camp_oid, day_date, venue, start, end = _validated_specs_window(body)
    camp = await db.camps.find_one({"_id": camp_oid, "is_active": True})
    if not camp:
        raise HTTPException(status_code=400, detail="Camp is not active")
    existing = await db.specs_collection_days.find_one({"camp_id": camp_oid, "day_date": day_date})
    fields = {"venue": venue, "start_time": start, "end_time": end}
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
