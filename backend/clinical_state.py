import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from helpers import now_utc

CLINICAL_ROLE = "clinical_desk_operator"
PRESCRIBED_LINE_KEYS = ("medicine", "specs_fixed", "specs_made", "ot")
CONTENT_FIELDS = (
    "diagnosis_options",
    "diagnosis_other",
    "blood_sugar",
    "bp",
    "remarks",
    "prescribed_medicines",
    "specs_measurements",
    "fixed_power_r",
    "fixed_power_l",
    "ot_eye",
    "ot_outcome",
    "ot_notes",
)
HOSPITAL_OUTCOMES = ("iol_surgery", "referral")
SURGERY_EYES = {"r": "R", "right": "R", "l": "L", "left": "L"}
EXCLUSIVE_LINE_LABELS = {
    "specs_fixed": "Fixed-power specs",
    "specs_made": "Spectacles to be made",
    "ot": "IOL surgery",
}


def normalize_ot_eye(value: Any) -> Optional[str]:
    return SURGERY_EYES.get(str(value or "").strip().lower())


def assert_clinical_operator(actor: dict | None) -> dict:
    if not actor or actor.get("role") != CLINICAL_ROLE:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return actor


def payload_hash(kind: str, data: dict) -> str:
    blob = json.dumps({"kind": kind, **data}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def extract_content(body: Any) -> dict:
    out = {}
    for field in CONTENT_FIELDS:
        out[field] = getattr(body, field, None)
    if out["diagnosis_options"] is None:
        out["diagnosis_options"] = []
    if out["prescribed_medicines"] is None:
        out["prescribed_medicines"] = []
    return out


def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list):
        return len(value) == 0
    if isinstance(value, dict):
        return all(_blank(v) for v in value.values())
    return False


def is_blank_content(content: dict) -> bool:
    return all(_blank(content.get(f)) for f in CONTENT_FIELDS)


def prescribed_lines_of(body: Any) -> Tuple[List[str], bool]:
    none = bool(getattr(body, "none_prescribed", False))
    raw = list(getattr(body, "prescribed_lines", None) or [])
    lines = [k for k in raw if k in PRESCRIBED_LINE_KEYS]
    unknown = [k for k in raw if k not in PRESCRIBED_LINE_KEYS]
    if unknown:
        raise HTTPException(status_code=400, detail={
            "code": "incomplete_prescription",
            "fields": {"prescribed_lines": "Unknown prescribed line."},
        })
    return lines, none


def _hospital_errors(content: dict, lines: List[str]) -> Dict[str, str]:
    outcome = content.get("ot_outcome")
    eye = content.get("ot_eye")
    if "ot" not in lines:
        errors: Dict[str, str] = {}
        if not _blank(outcome):
            errors["ot_outcome"] = "Tick the Hospital line or clear the Hospital outcome."
        if not _blank(eye):
            errors["ot_eye"] = "Tick the Hospital line or clear the surgery eye."
        return errors
    if outcome not in HOSPITAL_OUTCOMES:
        return {"ot_outcome": "Record whether the paper says IOL surgery or Hospital referral."}
    if outcome == "iol_surgery" and not normalize_ot_eye(eye):
        return {"ot_eye": "Record the IOL surgery eye as Right or Left."}
    if outcome == "referral" and not _blank(eye):
        return {"ot_eye": "A Hospital referral has no surgery eye."}
    return {}


def validate_completion(body: Any) -> Tuple[dict, List[str], bool]:
    if not getattr(body, "full_transcription_confirmed", False):
        raise HTTPException(status_code=400, detail={
            "code": "incomplete_prescription",
            "fields": {"full_transcription_confirmed": "Confirm that every instruction on the paper has been copied."},
        })
    lines, none = prescribed_lines_of(body)
    content = extract_content(body)
    if "medicine" not in lines:
        content["prescribed_medicines"] = []
    if "specs_fixed" not in lines:
        content["fixed_power_r"] = content["fixed_power_l"] = None
    if "specs_made" not in lines:
        content["specs_measurements"] = None
    if none and lines:
        raise HTTPException(status_code=400, detail={
            "code": "incomplete_prescription",
            "fields": {"prescribed_lines": "Do not select fulfilment lines when recording no fulfilment."},
        })
    if not none and not lines:
        raise HTTPException(status_code=400, detail={
            "code": "incomplete_prescription",
            "fields": {"prescribed_lines": "Select prescribed lines or record that no fulfilment was prescribed."},
        })
    if not none and is_blank_content(content):
        raise HTTPException(status_code=400, detail={
            "code": "incomplete_prescription",
            "fields": {"content": "The prescription is blank."},
        })
    errors: Dict[str, str] = {}
    if "medicine" in lines and _blank(content.get("prescribed_medicines")):
        errors["prescribed_medicines"] = "Select every medicine written on the paper."
    if "specs_fixed" in lines and (
        content.get("fixed_power_r") is None or content.get("fixed_power_l") is None
    ):
        errors["fixed_power"] = "Select the fixed power for both eyes."
    if "specs_made" in lines:
        m = content.get("specs_measurements") or {}
        if not (str(m.get("r_sph") or "").strip() and str(m.get("l_sph") or "").strip()):
            errors["specs_measurements"] = "Record the prescribed power for both eyes."
    errors.update(_hospital_errors(content, lines))
    exclusive: List[str] = [line for line in ("specs_fixed", "specs_made") if line in lines]
    if "ot" in lines and content.get("ot_outcome") == "iol_surgery":
        exclusive.append("ot")
    if len(exclusive) > 1:
        labels = [EXCLUSIVE_LINE_LABELS[line] for line in exclusive]
        errors["prescribed_lines"] = f"{', '.join(labels[:-1])} and {labels[-1]} cannot be on one prescription."
    content["ot_eye"] = normalize_ot_eye(content.get("ot_eye"))
    if errors:
        raise HTTPException(status_code=400, detail={
            "code": "incomplete_prescription",
            "fields": errors,
        })
    return content, lines, none


def generation_of(patient: dict) -> int:
    value = patient.get("clinical_generation")
    return int(value) if value is not None else 0


def arrival_ready(patient: dict) -> Optional[str]:
    if not patient.get("arrived_at"):
        return "not_arrived"
    if not patient.get("printed_at"):
        return "never_printed"
    return None


def conflict(code: str, message: str, **extra: Any) -> HTTPException:
    detail: Dict[str, Any] = {"code": code, "message": message}
    detail.update(extra)
    return HTTPException(status_code=409, detail=detail)


async def recover_operation(db, operation_id: str, kind: str, digest: str, session=None) -> Optional[dict]:
    if not operation_id:
        raise HTTPException(status_code=400, detail="operation_id is required")
    existing = await db.clinical_operations.find_one({"operation_id": operation_id}, session=session)
    if existing is None:
        return None
    if existing.get("kind") != kind or existing.get("payload_hash") != digest:
        raise conflict("operation_conflict", "This operation id was used for a different request.")
    return existing


async def record_operation(db, operation_id: str, kind: str, digest: str, patient_id, result: dict, session) -> None:
    await db.clinical_operations.insert_one({
        "operation_id": operation_id, "kind": kind, "payload_hash": digest, "patient_id": patient_id,
        "result": result, "created_at": now_utc(),
    }, session=session)


async def insert_revision(
    db,
    patient: dict,
    actor: dict,
    content: dict,
    prescribed_lines: List[str],
    none_prescribed: bool,
    operation_id: str,
    kind: str,
    reason: Optional[str],
    predecessor_id,
    session,
) -> dict:
    doc = {
        "patient_id": patient["_id"],
        "camp_id": patient.get("camp_id"),
        "kind": kind,
        "predecessor_id": predecessor_id,
        "reason": reason,
        "prescribed_lines": prescribed_lines,
        "none_prescribed": none_prescribed,
        **content,
        "operation_id": operation_id,
        "author_id": str(actor["_id"]),
        "created_at": now_utc(),
    }
    res = await db.prescription_revisions.insert_one(doc, session=session)
    doc["_id"] = res.inserted_id
    return doc


async def _commit(db, patient: dict, fields: dict, session) -> dict:
    return await db.patients.find_one_and_update(
        {"_id": patient["_id"]},
        {"$set": {**fields, "clinical_generation": generation_of(patient) + 1}},
        return_document=True,
        session=session,
    )


async def commit_completion(db, patient: dict, revision: dict, actor: dict, session) -> dict:
    return await _commit(db, patient, {
        "committed_revision_id": revision["_id"],
        "queue_status": "seen",
        "seen_at": now_utc(),
        "seen_by": str(actor["_id"]),
    }, session)


async def commit_correction(db, patient: dict, revision: dict, session) -> dict:
    return await _commit(db, patient, {"committed_revision_id": revision["_id"]}, session)


async def commit_undo(db, patient: dict, session) -> dict:
    return await _commit(db, patient, {
        "committed_revision_id": None,
        "queue_status": "arrived",
        "seen_at": None,
        "seen_by": None,
    }, session)


async def has_issue_history(db, patient: dict, session) -> bool:
    trans = await db.transcriptions.find_one({"patient_id": patient["_id"]}, session=session)
    return bool(trans and await db.fulfilments.find_one({"transcription_id": trans["_id"]}, session=session))


def serialize_revision(rev: dict | None) -> Optional[dict]:
    if not rev:
        return None
    created_at = rev.get("created_at")
    return {
        "id": str(rev["_id"]),
        "patient_id": str(rev["patient_id"]),
        "operation_id": rev.get("operation_id"),
        "kind": rev.get("kind"),
        "prescribed_lines": rev.get("prescribed_lines") or [],
        "none_prescribed": bool(rev.get("none_prescribed")),
        "reason": rev.get("reason"),
        "author_id": rev.get("author_id"),
        "created_at": created_at.isoformat() if created_at else None,
        **{field: rev.get(field) for field in CONTENT_FIELDS},
    }
