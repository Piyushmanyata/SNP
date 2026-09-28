import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from helpers import api_error, now_utc

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
        raise api_error(400, "INCOMPLETE_PRESCRIPTION", "Unknown prescribed line.", fields={"prescribed_lines": "Unknown prescribed line."})
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
        raise api_error(400, "INCOMPLETE_PRESCRIPTION", "Confirm that every instruction on the paper has been copied.", fields={"full_transcription_confirmed": "Confirm that every instruction on the paper has been copied."})
    lines, none = prescribed_lines_of(body)
    content = extract_content(body)
    if "medicine" not in lines:
        content["prescribed_medicines"] = []
    if "specs_fixed" not in lines:
        content["fixed_power_r"] = content["fixed_power_l"] = None
    if "specs_made" not in lines:
        content["specs_measurements"] = None
    if none and lines:
        raise api_error(400, "INCOMPLETE_PRESCRIPTION", "Do not select fulfilment lines when recording no fulfilment.", fields={"prescribed_lines": "Do not select fulfilment lines when recording no fulfilment."})
    if not none and not lines:
        raise api_error(400, "INCOMPLETE_PRESCRIPTION", "Select prescribed lines or record that no fulfilment was prescribed.", fields={"prescribed_lines": "Select prescribed lines or record that no fulfilment was prescribed."})
    if not none and is_blank_content(content):
        raise api_error(400, "INCOMPLETE_PRESCRIPTION", "The prescription is blank.", fields={"content": "The prescription is blank."})
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
        raise api_error(400, "INCOMPLETE_PRESCRIPTION", "Check the highlighted fields.", fields=errors)
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
    return api_error(409, code.upper(), message, **extra)


SPECS_EXCLUSION = {
    "specs_fixed": ("specs_made", "Spectacles to be made"),
    "specs_made": ("specs_fixed", "Fixed-power specs"),
}


def require_printed(patient: dict) -> None:
    gate = arrival_ready(patient)
    if gate == "not_arrived":
        raise conflict("not_arrived", "This patient has not arrived at the door yet.")
    if gate == "never_printed":
        raise conflict("never_printed", "This patient's prescription was never printed.")


def require_not_completed(patient: dict) -> None:
    if patient.get("committed_revision_id"):
        raise conflict("already_completed", "This patient already has a completed prescription.")


def require_generation(patient: dict, expected: int) -> None:
    if generation_of(patient) != expected:
        raise conflict("stale_generation", "The prescription changed; reload and retry.")


def require_unchanged(patient: dict, expected: int, revision_id: Any) -> None:
    if generation_of(patient) != expected or patient.get("committed_revision_id") != revision_id:
        raise conflict("stale_generation", "The prescription changed; reload and retry.")


def draft_conflict() -> HTTPException:
    return conflict("draft_version_conflict", "This prescription changed since you opened it. Reload to see the saved version.")


def require_draft_version(transcription: Optional[dict], expected: Optional[int]) -> None:
    if transcription and expected is not None and (transcription.get("draft_version") or 0) != max(expected, 0):
        raise draft_conflict()


def require_undoable(patient: dict, issued: bool) -> None:
    if issued:
        raise conflict("undo_after_issue", "Completion cannot be undone after an issue or pending issue.")
    if not patient.get("committed_revision_id"):
        raise conflict("not_completed", "There is no current completion to undo.")


def require_fresh_review(
    patient: dict, revision: Optional[dict], paper_reviewed: bool, revision_id: Optional[str], generation: Optional[int],
) -> dict:
    """The operator compared the paper with the prescription that is still committed."""
    if not patient.get("committed_revision_id") or patient.get("queue_status") != "seen":
        raise conflict("not_completed", "Issue requires a completed prescription.")
    if not paper_reviewed or not revision_id or generation is None:
        raise conflict("review_required", "Confirm the paper against the saved prescription before issuing.")
    stale = conflict("stale_review", "The reviewed prescription is no longer current. Review the paper again.")
    if str(patient["committed_revision_id"]) != revision_id or generation_of(patient) != generation:
        raise stale
    if not revision:
        raise conflict("not_completed", "Issue requires a completed prescription.")
    if str(revision.get("patient_id")) != str(patient["_id"]):
        raise stale
    return revision


def require_line_prescribed(revision: dict, item_type: str) -> None:
    if revision.get("none_prescribed") or item_type not in (revision.get("prescribed_lines") or []):
        raise conflict("line_not_prescribed", "This line is not prescribed on the completed prescription.")
    if item_type == "ot" and revision.get("ot_outcome") != "iol_surgery":
        raise conflict("hospital_referral", "A Hospital referral is complete once the prescription is saved; nothing is recorded at the Hospital station.")


def require_specs_exclusive(item_type: str, other_record: Optional[dict]) -> None:
    if other_record:
        raise api_error(409, "SPECS_LINE_EXCLUSIVE", f'This patient already has a {SPECS_EXCLUSION[item_type][1]} record.')


def require_correction_allowed(surgery_scheduled: bool, specs_scheduled: bool) -> None:
    if surgery_scheduled:
        raise conflict("surgery_scheduled", "Record Surgery declined at the Hospital station before changing a scheduled IOL surgery.")
    if specs_scheduled:
        raise conflict("SPECS_SCHEDULED", "Cancel the Spectacles to be made order at the Spectacles station before changing it.")


def carry_medicine_outcomes(outcomes: List[dict], prescribed: List[dict]) -> Tuple[List[dict], bool]:
    """Issued medicine outcomes against a corrected prescription, matched by catalogue id, then name (ADR 0097).

    Given stays given and not available stays not available while still prescribed. A medicine the correction adds
    is open (given None). One it removes after it was given stays, marked prescribed False. Returns the outcomes and
    whether the correction changed the line.
    """
    by_id = {o["medicine_id"]: o for o in outcomes}
    by_name = {o["name"]: o for o in outcomes}
    carried, matched = [], []
    for m in prescribed:
        earlier = by_id.get(m["medicine_id"]) or by_name.get(m["name"])
        if earlier:
            matched.append(earlier)
        carried.append({"medicine_id": m["medicine_id"], "name": m["name"], "given": earlier["given"] if earlier else None})
    unmatched = [o for o in outcomes if not any(o is m for m in matched)]
    carried += [{**o, "prescribed": False} for o in unmatched if o["given"]]
    return carried, len(matched) < len(prescribed) or any(o.get("prescribed") is not False for o in unmatched)


def fixed_power_corrected(issued: dict, before: dict, after: dict) -> bool:
    """The correction moved the prescribed fixed power away from the power already handed over."""
    was = (before.get("fixed_power_r"), before.get("fixed_power_l"))
    now = (after.get("fixed_power_r"), after.get("fixed_power_l"))
    return was != now and now != (issued.get("issued_power_r"), issued.get("issued_power_l"))


def keep_removed(prior: List[dict], outcomes: List[dict], corrected: bool = False) -> List[dict]:
    """A re-issue records the prescribed medicines; one a correction removed after it was given stays recorded.

    When the line was corrected after issue, settled outcomes cannot be altered at the persistence boundary.
    """
    prior_by_id = {o["medicine_id"]: o for o in prior}
    resolved = []
    for o in outcomes:
        p = prior_by_id.get(o["medicine_id"])
        if corrected and p and p.get("given") is not None:
            resolved.append({**o, "given": p["given"]})
        else:
            resolved.append(o)
    ids = {o["medicine_id"] for o in resolved}
    return resolved + [o for o in prior if o.get("prescribed") is False and o["medicine_id"] not in ids]


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


async def commit(db, patient: dict, fields: dict, session) -> dict:
    """Writes the patient's clinical fields and moves its generation on by one."""
    return await db.patients.find_one_and_update(
        {"_id": patient["_id"]},
        {"$set": {**fields, "clinical_generation": generation_of(patient) + 1}},
        return_document=True,
        session=session,
    )


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
