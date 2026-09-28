"""The prescription guards are pure: plain documents in, the existing refusal out."""

import pytest
from bson import ObjectId
from fastapi import HTTPException

from clinical_state import (
    require_correction_allowed, require_draft_version, require_fresh_review, require_generation,
    require_line_prescribed, require_not_completed, require_printed, require_specs_exclusive,
    require_unchanged, require_undoable,
)

PATIENT_ID = ObjectId()
REVISION_ID = ObjectId()
SEEN = {"_id": PATIENT_ID, "committed_revision_id": REVISION_ID, "queue_status": "seen", "clinical_generation": 1}
REVISION = {"_id": REVISION_ID, "patient_id": PATIENT_ID, "prescribed_lines": ["medicine", "ot"], "ot_outcome": "iol_surgery"}


def _code(call):
    with pytest.raises(HTTPException) as exc:
        call()
    return exc.value.detail["code"]


@pytest.mark.parametrize("patient,code", [
    ({}, "NOT_ARRIVED"),
    ({"arrived_at": "x", "aadhaar_scanned": True}, "NEVER_PRINTED"),
])
def test_requires_printed(patient, code):
    assert _code(lambda: require_printed(patient)) == code


def test_a_printed_patient_passes():
    assert require_printed({"arrived_at": "x", "printed_at": "y"}) is None


def test_not_already_completed():
    require_not_completed({})
    assert _code(lambda: require_not_completed(SEEN)) == "ALREADY_COMPLETED"


def test_generation_matches():
    require_generation(SEEN, 1)
    assert _code(lambda: require_generation(SEEN, 0)) == "STALE_GENERATION"
    require_unchanged(SEEN, 1, REVISION_ID)
    assert _code(lambda: require_unchanged(SEEN, 1, ObjectId())) == "STALE_GENERATION"


@pytest.mark.parametrize("transcription,expected,ok", [
    (None, 3, True), ({"draft_version": 2}, None, True), ({"draft_version": 2}, 2, True),
    ({}, 0, True), ({"draft_version": 2}, 1, False),
])
def test_draft_version_matches(transcription, expected, ok):
    if ok:
        require_draft_version(transcription, expected)
    else:
        assert _code(lambda: require_draft_version(transcription, expected)) == "DRAFT_VERSION_CONFLICT"


def test_a_lost_draft_save_reply_blames_no_other_operator():
    with pytest.raises(HTTPException) as exc:
        require_draft_version({"draft_version": 2}, 1)
    assert exc.value.detail["message"] == "This prescription changed since you opened it. Reload to see the saved version."


def test_undoable():
    require_undoable(SEEN, False)
    assert _code(lambda: require_undoable(SEEN, True)) == "UNDO_AFTER_ISSUE"
    assert _code(lambda: require_undoable({}, False)) == "NOT_COMPLETED"


@pytest.mark.parametrize("patient,revision,reviewed,revision_id,generation,code", [
    ({**SEEN, "queue_status": "arrived"}, REVISION, True, str(REVISION_ID), 1, "NOT_COMPLETED"),
    (SEEN, REVISION, False, str(REVISION_ID), 1, "REVIEW_REQUIRED"),
    (SEEN, REVISION, True, str(REVISION_ID), None, "REVIEW_REQUIRED"),
    (SEEN, REVISION, True, str(ObjectId()), 1, "STALE_REVIEW"),
    (SEEN, REVISION, True, str(REVISION_ID), 2, "STALE_REVIEW"),
    (SEEN, None, True, str(REVISION_ID), 1, "NOT_COMPLETED"),
    (SEEN, {**REVISION, "patient_id": ObjectId()}, True, str(REVISION_ID), 1, "STALE_REVIEW"),
])
def test_review_fresh(patient, revision, reviewed, revision_id, generation, code):
    assert _code(lambda: require_fresh_review(patient, revision, reviewed, revision_id, generation)) == code


def test_a_fresh_review_returns_the_revision():
    assert require_fresh_review(SEEN, REVISION, True, str(REVISION_ID), 1) is REVISION


def test_line_prescribed():
    require_line_prescribed(REVISION, "ot")
    assert _code(lambda: require_line_prescribed(REVISION, "specs_made")) == "LINE_NOT_PRESCRIBED"
    assert _code(lambda: require_line_prescribed({**REVISION, "none_prescribed": True}, "medicine")) == "LINE_NOT_PRESCRIBED"
    assert _code(lambda: require_line_prescribed({**REVISION, "ot_outcome": "referral"}, "ot")) == "HOSPITAL_REFERRAL"


def test_specs_lines_exclusive():
    require_specs_exclusive("specs_made", None)
    assert _code(lambda: require_specs_exclusive("specs_made", {"status": "fulfilled"})) == "SPECS_LINE_EXCLUSIVE"


def test_correction_allowed():
    require_correction_allowed(False, False)
    assert _code(lambda: require_correction_allowed(True, True)) == "SURGERY_SCHEDULED"
    assert _code(lambda: require_correction_allowed(False, True)) == "SPECS_SCHEDULED"
