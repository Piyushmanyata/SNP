from datetime import datetime
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, BackgroundTasks
from pymongo.errors import DuplicateKeyError
from pydantic import ValidationError
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase
from db import get_db
from models import (
    TranscriptionBody, FulfilmentBody, CorrectionBody, OtScheduleBody, SpecsScheduleBody,
    CompletePrescriptionBody, UndoCompletionBody,
)
from catalogue import resolve_medicines, stocked_power
import clinical_operation
from clinical_operation import Operation
from clinical_state import (
    CONTENT_FIELDS, PRESCRIBED_LINE_KEYS, SPECS_EXCLUSION, carry_medicine_outcomes, commit, conflict, draft_conflict,
    extract_content, fixed_power_corrected, generation_of, has_issue_history, insert_revision, normalize_ot_eye,
    keep_removed,
    require_correction_allowed, require_draft_version, require_fresh_review, require_generation,
    require_line_prescribed, require_not_completed, require_printed, require_specs_exclusive,
    require_unchanged, require_undoable, serialize_revision, validate_completion,
)
from helpers import (
    api_error,    now_utc, iso, DIAGNOSIS_OPTIONS, now_ist, ist_local_instant,
    normalize_name, normalize_phone, parse_patient_identifier,
)
from serializers import ser_patient, ser_person
from security import require_clinical, require_admin, require_any
import sms
import tokens

router = APIRouter(prefix="/api/clinical", tags=["clinical"])


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
        "medicine_outcomes": f.get("medicine_outcomes") or [],
        "issued_power_r": f.get("issued_power_r"),
        "issued_power_l": f.get("issued_power_l"),
        "corrected_after_issue": bool(f.get("corrected_after_issue")),
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
        "instructions": s.get("instructions"),
        "superseded": bool(s.get("superseded_by")),
        "replaces": str(s["replaces"]) if s.get("replaces") else None,
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
    return {
        "id": str(d["_id"]),
        "camp_id": str(d["camp_id"]),
        "day_date": d["day_date"],
        "end_date": d.get("end_date") or d["day_date"],
        "venue": d["venue"],
        "venue_sms": d.get("venue_sms"),
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
    db = get_db()
    camp = await db.camps.find_one({"is_active": True})
    value = parse_patient_identifier(body.get("value", ""))
    p = None
    if camp:
        p = await db.patients.find_one({"camp_id": camp["_id"], "patient_qr": value})
        if not p and value.isdecimal() and len(value) <= 12:
            p = await db.patients.find_one({"camp_id": camp["_id"], "reg_no": int(value)})
    if not p:
        raise api_error(404, "NO_MATCHING_REGISTRATION_FOUND", 'No matching registration found')
    require_printed(p)
    bundle = await _fetch_clinical_bundle(db, p)
    rev = None
    if p.get("committed_revision_id"):
        rev = await db.prescription_revisions.find_one({"_id": p["committed_revision_id"]})
    bundle["committed_revision"] = serialize_revision(rev)
    bundle["clinical_generation"] = generation_of(p)
    return bundle


@router.get("/search")
async def clinical_search(q: str, actor: dict = Depends(require_clinical)) -> Dict[str, Any]:
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
    }).sort([("arrived_at", -1), ("reg_no", -1)]).limit(21).to_list(21)
    return {"results": [{
        "id": str(p["_id"]),
        "reg_no": p.get("reg_no"),
        "full_name": p.get("full_name"),
        "age": p.get("age"),
        "gender_label": ser_patient(p)["gender_label"],
        "phone_last4": (normalize_phone(p.get("phone")) or "")[-4:],
    } for p in patients[:20]], "more": len(patients) > 20}


def _content_from_body(body) -> dict:
    content = extract_content(body)
    content["ot_eye"] = normalize_ot_eye(content.get("ot_eye"))
    return content


async def _apply_catalogue(db, body, active_only: bool = True) -> None:
    """The catalogue is the authority: names and powers are resolved server-side, never trusted from the client."""
    body.prescribed_medicines = await resolve_medicines(db, body.prescribed_medicine_ids, active_only=active_only)
    body.fixed_power_r = await stocked_power(db, body.fixed_power_r, active_only=active_only)
    body.fixed_power_l = await stocked_power(db, body.fixed_power_l, active_only=active_only)


async def _require_printed_patient(db, patient_id: str) -> dict:
    p = await db.patients.find_one({"_id": ObjectId(patient_id)})
    if not p:
        raise api_error(404, "REGISTRATION_NOT_FOUND", 'Registration not found')
    require_printed(p)
    return p


def _draft_version_match(version: int) -> Any:
    return {"$in": [None, 0]} if version <= 0 else version


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
            raise draft_conflict()
    query: Dict[str, Any] = {"_id": existing["_id"]}
    if not locked:
        query["locked"] = {"$ne": True}
        if expected_version is not None:
            query["draft_version"] = _draft_version_match(expected_version)
    t = await db.transcriptions.find_one_and_update(
        query, {"$set": fields, "$inc": {"draft_version": 1}}, return_document=True, session=session,
    )
    if not t:
        raise draft_conflict()
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
    db = get_db()
    await _apply_catalogue(db, body, active_only=not await clinical_operation.is_replay(db, body.operation_id))
    content, lines, none = validate_completion(body)
    p = await _require_printed_patient(db, body.patient_id)

    async def apply(patient, session):
        require_printed(patient)
        require_not_completed(patient)
        require_generation(patient, body.expected_generation)
        transcription = await db.transcriptions.find_one({"patient_id": patient["_id"]}, session=session)
        require_draft_version(transcription, body.expected_draft_version)
        revision = await insert_revision(
            db, patient, actor, content, lines, none, body.operation_id, "complete", None, None, session,
        )
        committed = await commit(db, patient, {
            "committed_revision_id": revision["_id"], "queue_status": "seen",
            "seen_at": now_utc(), "seen_by": str(actor["_id"]),
        }, session)
        transcription = await _upsert_transcription(db, committed, actor, content, locked=True, session=session)
        return _clinical_result(committed, revision, transcription), []

    def superseded(patient: dict, result: dict) -> Optional[str]:
        if str(patient.get("committed_revision_id")) != result["revision"]["id"]:
            return "This completion was undone or replaced and cannot be replayed."
        return None

    return await clinical_operation.run(db, Operation(
        "complete", body.operation_id, p["_id"],
        {"patient_id": str(p["_id"]), "content": content, "lines": lines, "none": none},
        apply, superseded,
    ))


@router.post("/transcription/undo")
async def undo_completion(
    body: UndoCompletionBody,
    actor: dict = Depends(require_clinical),
) -> Dict[str, Any]:
    reason = (body.reason or "").strip()
    if not reason:
        raise api_error(400, "UNDO_REQUIRES_A_REASON", 'Undo requires a reason')
    db = get_db()
    p = await db.patients.find_one({"_id": ObjectId(body.patient_id)})
    if not p:
        raise api_error(404, "REGISTRATION_NOT_FOUND", 'Registration not found')

    async def apply(patient, session):
        require_undoable(patient, await has_issue_history(db, patient, session))
        require_generation(patient, body.expected_generation)
        updated = await commit(db, patient, {
            "committed_revision_id": None, "queue_status": "arrived", "seen_at": None, "seen_by": None,
        }, session)
        trans = await db.transcriptions.find_one_and_update(
            {"patient_id": patient["_id"]}, {"$set": {"locked": False}}, return_document=True, session=session,
        )
        return {
            "registration": ser_patient(updated),
            "transcription": ser_trans(trans) if trans else None,
        }, []

    def superseded(patient: dict, result: dict) -> Optional[str]:
        if generation_of(patient) != result["registration"]["clinical_generation"]:
            return "The prescription changed after this undo, which cannot be replayed."
        return None

    return await clinical_operation.run(db, Operation(
        "undo", body.operation_id, p["_id"], {"patient_id": str(p["_id"]), "reason": reason}, apply, superseded,
    ))


def _validate_fulfilment_matrix(item_type: str, status: str) -> None:
    valid = {
        "medicine": {"fulfilled", "not_available", "partially_fulfilled"},
        "specs_fixed": {"fulfilled"},
        "specs_made": {"deferred", "cancelled"},
        "ot": {"deferred", "declined"},
    }
    if item_type not in valid or status not in valid[item_type]:
        raise api_error(400, "INVALID_FULFILMENT_ITEM_STATUS", 'Invalid fulfilment item/status')


def match_medicine_outcomes(revision: dict, outcomes) -> list[dict]:
    """Every prescribed medicine is accounted for exactly once, and names come from the revision."""
    prescribed = {m["medicine_id"]: m["name"] for m in (revision.get("prescribed_medicines") or [])}
    supplied = {o.medicine_id: bool(o.given) for o in (outcomes or [])}
    if not prescribed or len(supplied) != len(outcomes or []) or set(supplied) != set(prescribed):
        raise api_error(400, "MEDICINE_OUTCOMES_MISMATCH", 'Record given or not available for every prescribed medicine.')
    return [{"medicine_id": mid, "name": name, "given": supplied[mid]} for mid, name in prescribed.items()]


def derive_medicine_status(outcomes: list[dict]) -> str:
    given = sum(1 for o in outcomes if o["given"])
    if given == 0:
        return "not_available"
    if given == len(outcomes):
        return "fulfilled"
    return "partially_fulfilled"


async def resolve_issued_powers(db, revision: dict, body: FulfilmentBody) -> tuple[float, float]:
    """A power that ran out is substituted at the desk; the prescribed power on the revision never moves."""
    right = body.issued_power_r if body.issued_power_r is not None else revision.get("fixed_power_r")
    left = body.issued_power_l if body.issued_power_l is not None else revision.get("fixed_power_l")
    if right is None or left is None:
        raise api_error(400, "FIXED_POWER_REQUIRED", 'Select the fixed power for both eyes before issuing.')
    return await stocked_power(db, right, active_only=True), await stocked_power(db, left, active_only=True)


def _assert_specs_prescription(item_type: str, transcription: dict) -> None:
    """Made specs are ground from the grid; fixed specs are picked from the camp's stocked powers."""
    if item_type == "specs_made":
        m = transcription.get("specs_measurements") or {}
        if not (str(m.get("r_sph") or "").strip() and str(m.get("l_sph") or "").strip()):
            raise api_error(400, "SPECS_MEASUREMENTS_REQUIRED", 'Record the prescribed power for both eyes before recording a spectacles line.')
    elif item_type == "specs_fixed":
        if transcription.get("fixed_power_r") is None or transcription.get("fixed_power_l") is None:
            raise api_error(400, "FIXED_POWER_REQUIRED", 'Select the fixed power for both eyes before recording a spectacles line.')


async def persist_fulfilment(db: AsyncDatabase, prior: dict | None, doc: dict, session) -> dict:
    if prior:
        await db.fulfilments.update_one({"_id": prior["_id"]}, {"$set": doc}, session=session)
        doc["_id"] = prior["_id"]
        return doc
    res = await db.fulfilments.insert_one(doc, session=session)
    doc["_id"] = res.inserted_id
    return doc


def _day_requested(body: FulfilmentBody) -> Optional[str]:
    return body.ot_schedule_day_id if body.item_type == "ot" else body.specs_collection_day_id


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
        "ot_schedule_day_id": (slip or {}).get("ot_schedule_day_id"),
        "specs_collection_day_id": (slip or {}).get("specs_collection_day_id"),
        "created_by": actor_id,
        "created_at": now_utc(),
    }


@router.post("/fulfilment")
async def record_fulfilment(
    body: FulfilmentBody,
    background_tasks: BackgroundTasks,
    actor: dict = Depends(require_clinical),
) -> Dict[str, Any]:
    db = get_db()
    t = await db.transcriptions.find_one({"_id": ObjectId(body.transcription_id)})
    if not t:
        raise api_error(404, "TRANSCRIPTION_NOT_FOUND", 'Transcription not found')
    patient = await db.patients.find_one({"_id": t["patient_id"]}) if t.get("patient_id") else None
    if not patient:
        raise api_error(404, "REGISTRATION_NOT_FOUND", 'Registration not found')
    committed_id = patient.get("committed_revision_id")
    revision = await db.prescription_revisions.find_one({"_id": committed_id}) if committed_id else None
    revision = require_fresh_review(
        patient, revision, body.paper_reviewed, body.reviewed_revision_id, body.reviewed_generation,
    )
    if body.item_type not in PRESCRIBED_LINE_KEYS:
        raise api_error(400, "INVALID_FULFILMENT_ITEM_STATUS", 'Invalid fulfilment item/status')
    require_line_prescribed(revision, body.item_type)
    medicine_outcomes = None
    issued_powers = None
    if body.item_type == "medicine":
        medicine_outcomes = match_medicine_outcomes(revision, body.medicine_outcomes)
        body.status = derive_medicine_status(medicine_outcomes)
    elif body.item_type == "specs_fixed":
        issued_powers = await resolve_issued_powers(db, revision, body)
    _validate_fulfilment_matrix(body.item_type, body.status)

    async def apply(current, session):
        committed = current.get("committed_revision_id")
        claimed = await db.prescription_revisions.find_one({"_id": committed}, session=session) if committed else None
        require_line_prescribed(require_fresh_review(
            current, claimed, body.paper_reviewed, body.reviewed_revision_id, body.reviewed_generation,
        ), body.item_type)
        trans = await db.transcriptions.find_one({"_id": t["_id"]}, session=session)
        if not trans:
            raise api_error(404, "TRANSCRIPTION_NOT_FOUND", 'Transcription not found')
        if body.item_type in SPECS_EXCLUSION:
            require_specs_exclusive(body.item_type, await db.fulfilments.find_one({
                "transcription_id": t["_id"], "item_type": SPECS_EXCLUSION[body.item_type][0],
                "status": {"$ne": "cancelled"},
            }, session=session))
        _assert_specs_prescription(body.item_type, trans)
        prior = await db.fulfilments.find_one({"transcription_id": t["_id"], "item_type": body.item_type}, session=session)
        slip, queued = await tokens.defer(
            db, body.item_type, current, trans, prior, _day_requested(body), session,
        ) if body.status == "deferred" else (None, [])
        doc = _build_fulfilment_doc(body, t["_id"], slip, str(actor["_id"]), medicine_outcomes, issued_powers)
        if medicine_outcomes and prior:
            corrected = bool(prior.get("corrected_after_issue"))
            doc["medicine_outcomes"] = keep_removed(
                prior.get("medicine_outcomes") or [], medicine_outcomes, corrected=corrected,
            )
            doc["status"] = derive_medicine_status(doc["medicine_outcomes"])
        if prior and prior.get("corrected_after_issue"):
            doc["corrected_after_issue"] = prior["corrected_after_issue"]
            if body.item_type == "specs_fixed" and prior.get("issued_power_r") is not None:
                doc["issued_power_r"], doc["issued_power_l"] = prior["issued_power_r"], prior["issued_power_l"]
        doc.update({
            "operation_id": body.operation_id,
            "reviewed_revision_id": current["committed_revision_id"],
            "reviewed_generation": generation_of(current),
            "slip_id": slip["_id"] if slip else None,
            "camp_id": current.get("camp_id"),
            "patient_seen_at": current.get("seen_at"),
        })
        doc = await persist_fulfilment(db, prior, doc, session)
        if doc["status"] != "deferred":
            await tokens.close(db, doc["item_type"], t["_id"], prior, session)
        return {"fulfilment": ser_fulfil(doc), "slip": ser_slip(slip) if slip else None}, queued

    return await clinical_operation.run(db, Operation(
        "issue", body.operation_id, patient["_id"], body.model_dump(exclude={"operation_id"}), apply,
    ), background_tasks)


@router.get("/slip/{slip_id}")
async def get_slip(slip_id: str, actor: dict = Depends(require_clinical)) -> Dict[str, Any]:
    db = get_db()
    s = await db.deferred_slips.find_one({"_id": ObjectId(slip_id)})
    if not s:
        raise api_error(404, "SLIP_NOT_FOUND", 'Slip not found')
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


async def _carry_forward(db, transcription_id, before: dict, after: dict, actor: dict, session) -> None:
    """Issued lines follow a correction: goods that left stay recorded, and a changed line is marked (ADR 0097)."""
    mark = {"revision_id": after["_id"], "at": now_utc(), "by": str(actor["_id"])}
    issued = await db.fulfilments.find(
        {"transcription_id": transcription_id, "item_type": {"$in": ["medicine", "specs_fixed"]}}, session=session,
    ).to_list(None)
    for line in issued:
        update: Dict[str, Any] = {"corrected_after_issue": mark}
        if line["item_type"] == "medicine":
            outcomes, changed = carry_medicine_outcomes(
                line.get("medicine_outcomes") or [], after.get("prescribed_medicines") or [],
            )
            if not changed:
                continue
            update.update(medicine_outcomes=outcomes, status=derive_medicine_status(outcomes))
        elif not fixed_power_corrected(line, before, after):
            continue
        await db.fulfilments.update_one({"_id": line["_id"]}, {"$set": update}, session=session)


@router.post("/correction")
async def add_correction(
    body: CorrectionBody,
    actor: dict = Depends(require_clinical),
) -> Dict[str, Any]:
    reason = (body.reason or "").strip()
    if not reason:
        raise api_error(400, "CORRECTION_REQUIRES_A_REASON", 'Correction requires a reason')
    db = get_db()
    t = None
    if body.transcription_id:
        t = await db.transcriptions.find_one({"_id": ObjectId(body.transcription_id)})
        if not t:
            raise api_error(404, "TRANSCRIPTION_NOT_FOUND", 'Transcription not found')
    p = None
    if body.patient_id:
        p = await db.patients.find_one({"_id": ObjectId(body.patient_id)})
    elif t:
        p = await db.patients.find_one({"_id": t["patient_id"]})
    if not p:
        raise api_error(404, "REGISTRATION_NOT_FOUND", 'Registration not found')
    if t and t.get("patient_id") != p["_id"]:
        raise api_error(404, "TRANSCRIPTION_NOT_FOUND", 'Transcription not found')
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
            **merged, "patient_id": str(p["_id"]), "operation_id": body.operation_id or "",
            "full_transcription_confirmed": confirmed, "prescribed_lines": lines, "none_prescribed": none,
        })
    except ValidationError:
        raise api_error(400, "INVALID_PRESCRIPTION_CORRECTION", 'Invalid prescription correction')
    view.prescribed_medicines = await resolve_medicines(
        db, [m.get("medicine_id") for m in view.prescribed_medicines], active_only=False,
    )
    view.fixed_power_r = await stocked_power(db, view.fixed_power_r, active_only=False)
    view.fixed_power_l = await stocked_power(db, view.fixed_power_l, active_only=False)
    content, lines, none = validate_completion(view)
    still_iol = "ot" in lines and content.get("ot_outcome") == "iol_surgery"
    same_specs = "specs_made" in lines and content.get("specs_measurements") == current.get("specs_measurements")

    async def apply(patient, session):
        require_unchanged(patient, body.expected_generation, base_id)
        trans = await db.transcriptions.find_one({"patient_id": patient["_id"]}, session=session)
        require_correction_allowed(
            bool(trans and not still_iol and await db.fulfilments.find_one(
                {"transcription_id": trans["_id"], "item_type": "ot", "status": "deferred"}, session=session,
            )),
            bool(trans and not same_specs and await db.deferred_slips.find_one(
                {"transcription_id": trans["_id"], "item_type": "specs_made", "active": True}, session=session,
            )),
        )
        revision = await insert_revision(
            db, patient, actor, content, lines, none, body.operation_id or "", "correct", reason, base_id, session,
        )
        committed = await commit(db, patient, {"committed_revision_id": revision["_id"]}, session)
        if trans:
            await _carry_forward(db, trans["_id"], current, revision, actor, session)
        trans = await _upsert_transcription(db, committed, actor, content, locked=True, session=session)
        return _clinical_result(committed, revision, trans), []

    return await clinical_operation.run(db, Operation(
        "correct", body.operation_id, p["_id"],
        {"patient_id": str(p["_id"]), "content": content, "reason": body.reason, "lines": lines, "none": none},
        apply,
    ))


@router.get("/history/{person_id}")
async def clinical_history(person_id: str, actor: dict = Depends(require_clinical)) -> Dict[str, Any]:
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


# ---- OT and Specs schedules ----
@router.post("/ot-days")
async def create_ot_day(body: OtScheduleBody, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    camp_id = tokens.oid_or_400(body.camp_id)
    try:
        day_date = datetime.strptime(body.day_date, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise api_error(400, "INVALID_DAY_DATE", 'Invalid day_date')
    if day_date.isoformat() != body.day_date or day_date < now_ist().date():
        raise api_error(400, "SURGERY_DATE_MUST_BE_TODAY_OR_LATER", 'Surgery date must be today or later')
    if body.seat_limit <= 0:
        raise api_error(400, "SEAT_LIMIT_MUST_BE_POSITIVE", 'Seat limit must be positive')
    venue = (body.venue or "").strip()
    if not venue:
        raise api_error(400, "VENUE_IS_REQUIRED", 'Venue is required')
    if not await db.camps.find_one({"_id": camp_id, "is_active": True}):
        raise api_error(400, "CAMP_IS_NOT_ACTIVE", 'Camp is not active')
    d = {
        "camp_id": camp_id, "day_date": body.day_date,
        "venue": venue, "venue_sms": body.venue_sms, "seat_limit": body.seat_limit, "seats_taken": 0,
        "created_at": now_utc(),
    }
    try:
        d["_id"] = (await db.ot_schedule_days.insert_one(d)).inserted_id
    except DuplicateKeyError:
        raise tokens.day_exists()
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
    camp_id = tokens.oid_or_400(body.camp_id)
    oid = tokens.oid_or_400(day_id)
    day = await db.ot_schedule_days.find_one({"_id": oid, "camp_id": camp_id})
    if not day:
        raise api_error(404, "DAY_NOT_FOUND", 'OT day not found')
    try:
        date = datetime.strptime(body.day_date, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise api_error(400, "INVALID_DAY_DATE", 'Invalid day_date')
    if date.isoformat() != body.day_date or date < now_ist().date() or day["day_date"] < now_ist().date().isoformat():
        raise api_error(409, "PAST_OT_DAYS_CANNOT_BE_EDITED", 'Past OT days cannot be edited')
    if body.seat_limit <= 0:
        raise api_error(400, "SEAT_LIMIT_MUST_BE_POSITIVE", 'Seat limit must be positive')
    venue = (body.venue or "").strip()
    if not venue:
        raise api_error(400, "VENUE_IS_REQUIRED", 'Venue is required')
    changed = await tokens.edit_day(
        db, "ot", day,
        {"day_date": body.day_date, "seat_limit": body.seat_limit, "venue": venue, "venue_sms": body.venue_sms},
        background_tasks,
    )
    return {"ot_day": ser_ot_day(changed)}


def _validated_specs_window(body: SpecsScheduleBody) -> tuple[ObjectId, str, str, str]:
    venue = (body.venue or "").strip()
    if not venue:
        raise api_error(400, "VENUE_IS_REQUIRED", 'Venue is required')
    camp_oid = tokens.oid_or_400(body.camp_id)
    end_date = body.end_date or body.day_date
    try:
        first_day = datetime.strptime(body.day_date, "%Y-%m-%d")
    except (TypeError, ValueError):
        raise api_error(400, "INVALID_DAY_DATE", 'Invalid day_date')
    try:
        last_day = datetime.strptime(end_date, "%Y-%m-%d")
    except (TypeError, ValueError):
        raise api_error(400, "INVALID_END_DATE", 'Invalid end_date')
    if last_day < first_day:
        raise api_error(400, "END_DATE_MUST_NOT_BE_BEFORE_DAY_DATE", 'end_date must not be before day_date')
    if ist_local_instant(end_date, sms.SPECS_PICKUP_END_TIME) <= now_ist():
        raise api_error(400, "WINDOW_END_MUST_BE_AFTER_NOW", 'Window end must be after now')
    return camp_oid, body.day_date, end_date, venue


@router.post("/specs-days")
async def create_specs_day(body: SpecsScheduleBody, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    camp_oid, day_date, end_date, venue = _validated_specs_window(body)
    if not await db.camps.find_one({"_id": camp_oid, "is_active": True}):
        raise api_error(400, "CAMP_IS_NOT_ACTIVE", 'Camp is not active')
    d = {"camp_id": camp_oid, "day_date": day_date, "end_date": end_date, "venue": venue,
         "venue_sms": body.venue_sms, "created_at": now_utc()}
    try:
        d["_id"] = (await db.specs_collection_days.insert_one(d)).inserted_id
    except DuplicateKeyError:
        raise tokens.day_exists()
    return {"specs_day": ser_specs_day(d)}


@router.patch("/specs-days/{day_id}")
async def update_specs_day(day_id: str, body: SpecsScheduleBody, background_tasks: BackgroundTasks,
                           actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    camp_oid, day_date, end_date, venue = _validated_specs_window(body)
    day = await db.specs_collection_days.find_one({"_id": tokens.oid_or_400(day_id), "camp_id": camp_oid})
    if not day:
        raise api_error(404, "DAY_NOT_FOUND", 'Specs collection day not found')
    if not tokens.specs_window_open(day):
        raise api_error(409, "PAST_SPECS_COLLECTION_DAYS_CANNOT_BE_EDITED", 'Past specs collection days cannot be edited')
    changed = await tokens.edit_day(
        db, "specs", day, {"day_date": day_date, "end_date": end_date, "venue": venue, "venue_sms": body.venue_sms},
        background_tasks,
    )
    return {"specs_day": ser_specs_day(changed)}


@router.get("/specs-days")
async def list_specs_days(actor: dict = Depends(require_any)) -> Dict[str, Any]:
    db = get_db()
    camp = await db.camps.find_one({"is_active": True})
    if not camp:
        return {"specs_days": []}
    days = await db.specs_collection_days.find({"camp_id": camp["_id"]}).sort("day_date", 1).to_list(100)
    return {"specs_days": [ser_specs_day(d) for d in days]}


@router.get("/schedule-notices")
async def list_schedule_notices(actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    """Patients whose replaced Token has no SMS on its way: the desk phones them."""
    return {"notices": await tokens.patients_to_phone(get_db(), now_utc())}


@router.post("/schedule-notices/{slip_id}/contacted")
async def mark_notice_contacted(slip_id: str, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    await tokens.mark_contacted(get_db(), tokens.oid_or_400(slip_id), str(actor["_id"]), now_utc())
    return {"ok": True}
