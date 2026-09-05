import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

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
    "ot_procedure",
    "ot_notes",
)


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


def validate_completion(body: Any) -> Tuple[dict, List[str], bool]:
    if not getattr(body, "full_transcription_confirmed", False):
        raise HTTPException(status_code=400, detail={
            "code": "incomplete_prescription",
            "fields": {"full_transcription_confirmed": "Confirm that every instruction on the paper has been copied."},
        })
    lines, none = prescribed_lines_of(body)
    content = extract_content(body)
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
    if "ot" in lines:
        if _blank(content.get("ot_eye")) or _blank(content.get("ot_procedure")):
            errors["ot"] = "Record the OT eye and procedure from the paper."
    if errors:
        raise HTTPException(status_code=400, detail={
            "code": "incomplete_prescription",
            "fields": errors,
        })
    return content, lines, none


def generation_of(patient: dict) -> int:
    value = patient.get("clinical_generation")
    return int(value) if value is not None else 0


def _generation_clause(expected: int) -> dict:
    if expected == 0:
        return {"$or": [{"clinical_generation": 0}, {"clinical_generation": None}]}
    return {"clinical_generation": expected}


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


async def load_operation(db, operation_id: str) -> Optional[dict]:
    if not operation_id:
        raise HTTPException(status_code=400, detail="operation_id is required")
    return await db.clinical_operations.find_one({"operation_id": operation_id})


async def recover_operation(db, operation_id: str, kind: str, digest: str) -> Optional[dict]:
    existing = await load_operation(db, operation_id)
    if existing is None:
        return None
    if existing.get("kind") != kind or existing.get("payload_hash") != digest:
        raise conflict("operation_conflict", "This operation id was used for a different request.")
    return existing


async def save_operation(db, doc: dict) -> dict:
    existing = await db.clinical_operations.find_one({"operation_id": doc["operation_id"]})
    if existing:
        await db.clinical_operations.update_one(
            {"_id": existing["_id"]},
            {"$set": {k: v for k, v in doc.items() if k != "operation_id"}},
        )
        existing.update(doc)
        return existing
    try:
        res = await db.clinical_operations.insert_one(doc)
        doc["_id"] = res.inserted_id
        return doc
    except DuplicateKeyError:
        found = await db.clinical_operations.find_one({"operation_id": doc["operation_id"]})
        if not found:
            raise
        return found


async def prepare_revision(
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
) -> dict:
    existing = await db.prescription_revisions.find_one({"operation_id": operation_id})
    if existing:
        return existing
    doc = {
        "patient_id": patient["_id"],
        "camp_id": patient.get("camp_id"),
        "operation_id": operation_id,
        "kind": kind,
        "predecessor_id": predecessor_id,
        "author_id": str(actor["_id"]),
        "reason": reason,
        "prescribed_lines": prescribed_lines,
        "none_prescribed": none_prescribed,
        "created_at": now_utc(),
        **content,
    }
    try:
        res = await db.prescription_revisions.insert_one(doc)
        doc["_id"] = res.inserted_id
        return doc
    except DuplicateKeyError:
        found = await db.prescription_revisions.find_one({"operation_id": operation_id})
        if not found:
            raise
        return found


def _commit_filter(patient_id, expected: int, *, empty_commit: bool, require_commit: bool) -> dict:
    query = {
        "_id": patient_id,
        "issue_auth_op": None,
        "arrived_at": {"$ne": None},
        "printed_at": {"$ne": None},
    }
    query.update(_generation_clause(expected))
    if empty_commit:
        query["committed_revision_id"] = None
    if require_commit:
        query["committed_revision_id"] = {"$ne": None}
    return query


async def commit_completion(db, patient: dict, revision: dict, actor: dict, expected: int) -> Optional[dict]:
    now = now_utc()
    return await db.patients.find_one_and_update(
        _commit_filter(patient["_id"], expected, empty_commit=True, require_commit=False),
        {"$set": {
            "committed_revision_id": revision["_id"],
            "queue_status": "seen",
            "seen_at": now,
            "seen_by": str(actor["_id"]),
            "clinical_generation": expected + 1,
        }},
        return_document=True,
    )


async def commit_correction(db, patient: dict, revision: dict, actor: dict, expected: int) -> Optional[dict]:
    now = now_utc()
    return await db.patients.find_one_and_update(
        _commit_filter(patient["_id"], expected, empty_commit=False, require_commit=True),
        {"$set": {
            "committed_revision_id": revision["_id"],
            "queue_status": "seen",
            "seen_at": patient.get("seen_at") or now,
            "seen_by": patient.get("seen_by") or str(actor["_id"]),
            "clinical_generation": expected + 1,
            "line_review": None,
        }},
        return_document=True,
    )


async def has_issue_history(db, patient: dict) -> bool:
    if patient.get("issue_auth_op") or patient.get("issue_authorization"):
        return True
    trans = await db.transcriptions.find_one({"patient_id": patient["_id"]})
    if trans and await db.fulfilments.find_one({"transcription_id": trans["_id"]}):
        return True
    return False


async def commit_undo(db, patient: dict, expected: int) -> Optional[dict]:
    return await db.patients.find_one_and_update(
        _commit_filter(patient["_id"], expected, empty_commit=False, require_commit=True),
        {"$set": {
            "committed_revision_id": None,
            "queue_status": "arrived",
            "seen_at": None,
            "seen_by": None,
            "clinical_generation": expected + 1,
            "issue_authorization": None,
            "issue_auth_op": None,
        }},
        return_document=True,
    )


async def begin_issue_authorization(
    db,
    patient: dict,
    actor: dict,
    line: str,
    revision_id,
    generation: int,
    operation_id: str,
) -> dict:
    pending = {
        "operation_id": operation_id,
        "line": line,
        "revision_id": revision_id,
        "generation": generation,
        "reviewer_id": str(actor["_id"]),
        "status": "pending",
        "started_at": now_utc(),
    }
    if patient.get("issue_auth_op") == operation_id:
        return patient
    if patient.get("issue_auth_op"):
        raise conflict("issue_pending", "Another issue is already in progress for this patient.")
    updated = await db.patients.find_one_and_update(
        {
            "_id": patient["_id"],
            "committed_revision_id": revision_id,
            "clinical_generation": generation,
            "issue_auth_op": None,
            "queue_status": "seen",
        },
        {"$set": {"issue_authorization": pending, "issue_auth_op": operation_id}},
        return_document=True,
    )
    if not updated:
        raise conflict("stale_review", "The reviewed prescription is no longer current. Review the paper again.")
    return updated


async def release_issue_authorization(db, patient_id, operation_id: str) -> None:
    await db.patients.update_one(
        {"_id": patient_id, "issue_auth_op": operation_id},
        {"$set": {"issue_authorization": None, "issue_auth_op": None}},
    )


def serialize_revision(rev: dict | None) -> Optional[dict]:
    if not rev:
        return None
    return {
        "id": str(rev["_id"]),
        "patient_id": str(rev["patient_id"]),
        "operation_id": rev.get("operation_id"),
        "kind": rev.get("kind"),
        "prescribed_lines": rev.get("prescribed_lines") or [],
        "none_prescribed": bool(rev.get("none_prescribed")),
        "reason": rev.get("reason"),
        "author_id": rev.get("author_id"),
        "created_at": rev.get("created_at").isoformat() if rev.get("created_at") else None,
        **{field: rev.get(field) for field in CONTENT_FIELDS},
    }
