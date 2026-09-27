import asyncio

import pytest
from bson import ObjectId
from fastapi import HTTPException

import routes_clinical
from models import CorrectionBody, TranscriptionBody, UndoCompletionBody
from seed import patient_doc, run_camp
from test_camp_operations_matrix import CLINICAL, _complete_body, _issue_body, _printed_patient, intercept


def _fail(monkeypatch, collection, method, predicate=lambda *a, **k: True):
    async def failing(real, *args, **kwargs):
        if predicate(*args, **kwargs):
            raise RuntimeError("injected failure")
        return await real(*args, **kwargs)

    return intercept(monkeypatch, collection, method, failing)


def _fail_locking(monkeypatch):
    inserted = _fail(monkeypatch, "transcriptions", "insert_one", lambda doc, *a, **k: doc.get("locked") is True)
    updated = _fail(monkeypatch, "transcriptions", "find_one_and_update",
                    lambda query, update, *a, **k: (update.get("$set") or {}).get("locked") is True)
    return lambda: (inserted(), updated())


def _recording(kind):
    return lambda doc, *args, **kwargs: doc.get("kind") == kind


def test_a_failed_completion_leaves_no_revision_or_operation(monkeypatch):
    async def run(db):
        _, _, patient = await _printed_patient(db)
        restore = _fail(monkeypatch, "patients", "find_one_and_update",
                        lambda query, update, *a, **k: "committed_revision_id" in (update.get("$set") or {}))
        with pytest.raises(RuntimeError):
            await routes_clinical.complete_prescription(_complete_body(patient["_id"], "complete"), actor=CLINICAL)
        restore()
        assert await db.prescription_revisions.count_documents({}) == 0
        assert await db.clinical_operations.count_documents({}) == 0
        assert not (await db.patients.find_one({"_id": patient["_id"]})).get("committed_revision_id")
        done = await routes_clinical.complete_prescription(
            _complete_body(patient["_id"], "complete", bp="150/90"), actor=CLINICAL,
        )
        assert done["revision"]["bp"] == "150/90"

    run_camp(monkeypatch, run)


@pytest.mark.parametrize("foreign_patient", [False, True])
def test_issue_operation_rejects_a_different_request(monkeypatch, foreign_patient):
    async def run(db):
        _, _, patient = await _printed_patient(db)
        done = await routes_clinical.complete_prescription(_complete_body(patient["_id"], "complete"), actor=CLINICAL)
        await routes_clinical.record_fulfilment(
            _issue_body(done["transcription"]["id"], done["revision"]["id"], 1, "issue"), actor=CLINICAL,
            background_tasks=None)
        if foreign_patient:
            other = {**patient, **patient_doc(_id=ObjectId(), full_name="Different Patient")}
            await db.patients.insert_one(other)
            done = await routes_clinical.complete_prescription(_complete_body(other["_id"], "complete-other"), actor=CLINICAL)
        with pytest.raises(HTTPException) as exc:
            await routes_clinical.record_fulfilment(
                _issue_body(done["transcription"]["id"], done["revision"]["id"], 1, "issue", status="not_available"),
                actor=CLINICAL, background_tasks=None)
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "OPERATION_CONFLICT"
        assert await db.fulfilments.count_documents({}) == 1

    run_camp(monkeypatch, run)


def test_a_revision_for_another_patient_is_a_stale_review(monkeypatch):
    async def run(db):
        _, _, patient = await _printed_patient(db)
        done = await routes_clinical.complete_prescription(
            _complete_body(patient["_id"], "complete"), actor=CLINICAL,
        )
        await db.prescription_revisions.update_one(
            {"_id": ObjectId(done["revision"]["id"])},
            {"$set": {"patient_id": ObjectId()}},
        )
        with pytest.raises(HTTPException) as exc:
            await routes_clinical.record_fulfilment(
                _issue_body(done["transcription"]["id"], done["revision"]["id"], 1, "issue-mismatch"),
                actor=CLINICAL, background_tasks=None,
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "STALE_REVIEW"
        assert await db.fulfilments.count_documents({}) == 0

    run_camp(monkeypatch, run)


def test_correction_can_clear_prescribed_lines_and_content(monkeypatch):
    async def run(db):
        _, _, patient = await _printed_patient(db)
        done = await routes_clinical.complete_prescription(_complete_body(patient["_id"], "complete"), actor=CLINICAL)
        result = await routes_clinical.add_correction(CorrectionBody(
            patient_id=str(patient["_id"]), transcription_id=done["transcription"]["id"],
            reason="No medicine prescribed", operation_id="correct", expected_generation=1,
            full_transcription_confirmed=True, none_prescribed=True, prescribed_lines=[],
            prescribed_medicine_ids=[], bp=None, diagnosis_options=[],
        ), actor=CLINICAL)
        assert result["revision"]["prescribed_lines"] == []
        assert result["revision"]["none_prescribed"] is True
        assert result["revision"]["prescribed_medicines"] == []
        assert result["revision"]["bp"] is None
        assert result["revision"]["diagnosis_options"] == []

    run_camp(monkeypatch, run)


def test_draft_write_racing_completion_cannot_unlock_issued_prescription(monkeypatch):
    async def run(db):
        _, _, patient = await _printed_patient(db)
        draft = await routes_clinical.create_transcription(
            TranscriptionBody(patient_id=str(patient["_id"]), bp="110/70"), actor=CLINICAL,
        )
        entered = asyncio.Event()
        proceed = asyncio.Event()

        async def paused(find_one_and_update, query, update, *args, **kwargs):
            if update.get("$set", {}).get("locked") is False:
                entered.set()
                await proceed.wait()
            return await find_one_and_update(query, update, *args, **kwargs)

        intercept(monkeypatch, "transcriptions", "find_one_and_update", paused)
        pending = asyncio.create_task(routes_clinical.create_transcription(
            TranscriptionBody(patient_id=str(patient["_id"]), bp="999/99"), actor=CLINICAL,
        ))
        await entered.wait()
        try:
            done = await routes_clinical.complete_prescription(_complete_body(patient["_id"], "complete"), actor=CLINICAL)
            await routes_clinical.record_fulfilment(
                _issue_body(done["transcription"]["id"], done["revision"]["id"], 1, "issue"), actor=CLINICAL,
                background_tasks=None)
        finally:
            proceed.set()
        with pytest.raises(HTTPException) as exc:
            await pending
        assert exc.value.status_code == 409
        current = await db.transcriptions.find_one({"_id": ObjectId(draft["transcription"]["id"])})
        assert current["locked"] is True
        assert current["bp"] == "120/80"

    run_camp(monkeypatch, run)


def test_an_undo_and_an_issue_on_one_patient_serialize(monkeypatch):
    async def run(db):
        _, _, patient = await _printed_patient(db)
        done = await routes_clinical.complete_prescription(_complete_body(patient["_id"], "complete"), actor=CLINICAL)
        undo_result, issue_result = await asyncio.gather(
            routes_clinical.undo_completion(UndoCompletionBody(
                patient_id=str(patient["_id"]), operation_id="undo", expected_generation=1,
                reason="Entered in error",
            ), actor=CLINICAL),
            routes_clinical.record_fulfilment(
                _issue_body(done["transcription"]["id"], done["revision"]["id"], 1, "issue"),
                actor=CLINICAL, background_tasks=None,
            ),
            return_exceptions=True,
        )
        stored = await db.patients.find_one({"_id": patient["_id"]})
        fulfilments = await db.fulfilments.count_documents({})
        if isinstance(undo_result, HTTPException):
            assert undo_result.status_code == 409
            assert undo_result.detail["code"] == "UNDO_AFTER_ISSUE"
            assert not isinstance(issue_result, Exception)
            assert fulfilments == 1
            assert stored.get("committed_revision_id")
        else:
            assert not isinstance(undo_result, Exception)
            assert isinstance(issue_result, HTTPException)
            assert issue_result.status_code == 409
            assert fulfilments == 0
            assert not stored.get("committed_revision_id")

    run_camp(monkeypatch, run)


@pytest.mark.parametrize("failure_stage", ["transcription", "ledger"])
def test_a_failed_completion_write_rolls_back_and_the_retry_applies_once(monkeypatch, failure_stage):
    async def run(db):
        _, _, patient = await _printed_patient(db)
        body = _complete_body(patient["_id"], "complete")
        if failure_stage == "transcription":
            restore = _fail_locking(monkeypatch)
        else:
            restore = _fail(monkeypatch, "clinical_operations", "insert_one", _recording("complete"))
        with pytest.raises(RuntimeError):
            await routes_clinical.complete_prescription(body, actor=CLINICAL)
        restore()
        assert (await db.patients.find_one({"_id": patient["_id"]})).get("clinical_generation") in (0, None)
        assert await db.prescription_revisions.count_documents({}) == 0
        result = await routes_clinical.complete_prescription(body, actor=CLINICAL)
        assert result["registration"]["clinical_generation"] == 1
        assert result["transcription"]["locked"] is True
        assert await db.prescription_revisions.count_documents({}) == 1
        assert await routes_clinical.complete_prescription(body, actor=CLINICAL) == result

    run_camp(monkeypatch, run)


@pytest.mark.parametrize("failure_stage", ["transcription", "ledger"])
def test_a_failed_correction_rolls_back_and_the_retry_applies_one_generation(monkeypatch, failure_stage):
    async def run(db):
        _, _, patient = await _printed_patient(db)
        done = await routes_clinical.complete_prescription(_complete_body(patient["_id"], "complete"), actor=CLINICAL)
        body = CorrectionBody(
            patient_id=str(patient["_id"]), reason="Correct pressure", operation_id="correct-1",
            expected_generation=done["registration"]["clinical_generation"],
            full_transcription_confirmed=True, bp="130/85",
        )
        if failure_stage == "transcription":
            restore = _fail_locking(monkeypatch)
        else:
            restore = _fail(monkeypatch, "clinical_operations", "insert_one", _recording("correct"))
        with pytest.raises(RuntimeError):
            await routes_clinical.add_correction(body, actor=CLINICAL)
        restore()
        assert (await db.patients.find_one({"_id": patient["_id"]}))["clinical_generation"] == 1
        assert await db.prescription_revisions.count_documents({"kind": "correct"}) == 0
        result = await routes_clinical.add_correction(body, actor=CLINICAL)
        assert result["registration"]["clinical_generation"] == 2
        assert await db.prescription_revisions.count_documents({"kind": "correct"}) == 1
        assert await routes_clinical.add_correction(body, actor=CLINICAL) == result

        changed = body.model_copy(update={"bp": "140/90"})
        with pytest.raises(HTTPException) as exc:
            await routes_clinical.add_correction(changed, actor=CLINICAL)
        assert exc.value.detail["code"] == "OPERATION_CONFLICT"

    run_camp(monkeypatch, run)


def test_a_stale_correction_leaves_nothing_and_its_retry_lands_on_the_newer_one(monkeypatch):
    async def run(db):
        _, _, patient = await _printed_patient(db)
        done = await routes_clinical.complete_prescription(_complete_body(patient["_id"], "complete"), actor=CLINICAL)
        generation = done["registration"]["clinical_generation"]
        stale = CorrectionBody(
            patient_id=str(patient["_id"]), reason="Correct pressure", operation_id="stale",
            expected_generation=generation, full_transcription_confirmed=True, bp="130/85",
        )
        await routes_clinical.add_correction(CorrectionBody(
            patient_id=str(patient["_id"]), reason="Correct sugar", operation_id="newer",
            expected_generation=generation, full_transcription_confirmed=True, blood_sugar="140",
        ), actor=CLINICAL)
        with pytest.raises(HTTPException) as exc:
            await routes_clinical.add_correction(stale, actor=CLINICAL)
        assert exc.value.detail["code"] == "STALE_GENERATION"
        assert await db.prescription_revisions.count_documents({"operation_id": "stale"}) == 0
        retry = await routes_clinical.add_correction(stale.model_copy(update={"expected_generation": generation + 1}), actor=CLINICAL)
        assert retry["revision"]["bp"] == "130/85" and retry["revision"]["blood_sugar"] == "140"

    run_camp(monkeypatch, run)


def test_a_failed_undo_rolls_back_and_the_retry_clears_one_completion(monkeypatch):
    async def run(db):
        _, _, patient = await _printed_patient(db)
        done = await routes_clinical.complete_prescription(_complete_body(patient["_id"], "complete"), actor=CLINICAL)
        body = UndoCompletionBody(
            patient_id=str(patient["_id"]),
            expected_generation=done["registration"]["clinical_generation"],
            reason="Wrong patient", operation_id="undo-1",
        )
        restore = _fail(monkeypatch, "clinical_operations", "insert_one", _recording("undo"))
        with pytest.raises(RuntimeError):
            await routes_clinical.undo_completion(body, actor=CLINICAL)
        restore()
        still = await db.patients.find_one({"_id": patient["_id"]})
        assert still["clinical_generation"] == 1 and still["committed_revision_id"]
        result = await routes_clinical.undo_completion(body, actor=CLINICAL)
        assert result["registration"]["clinical_generation"] == 2
        assert result["registration"]["committed_revision_id"] is None
        assert result["transcription"]["locked"] is False
        assert await routes_clinical.undo_completion(body, actor=CLINICAL) == result
        assert (await db.patients.find_one({"_id": patient["_id"]}))["clinical_generation"] == 2

    run_camp(monkeypatch, run)


def test_malformed_correction_content_is_rejected_before_processing(monkeypatch):
    async def run(db):
        _, _, patient = await _printed_patient(db)
        done = await routes_clinical.complete_prescription(_complete_body(patient["_id"], "complete"), actor=CLINICAL)
        with pytest.raises(HTTPException) as exc:
            await routes_clinical.add_correction(CorrectionBody(
                patient_id=str(patient["_id"]), transcription_id=done["transcription"]["id"],
                reason="Malformed client payload", operation_id="correct", expected_generation=1,
                changes={"prescribed_medicines": 123},
            ), actor=CLINICAL)
        assert exc.value.status_code == 400
        assert (await db.patients.find_one({"_id": patient["_id"]}))["clinical_generation"] == 1

    run_camp(monkeypatch, run)


def test_late_issue_retry_preserves_the_newer_outcome(monkeypatch):
    async def run(db):
        _, _, patient = await _printed_patient(db)
        done = await routes_clinical.complete_prescription(_complete_body(patient["_id"], "complete"), actor=CLINICAL)
        first = _issue_body(done["transcription"]["id"], done["revision"]["id"], 1, "issue-a", status="not_available")
        second = _issue_body(done["transcription"]["id"], done["revision"]["id"], 1, "issue-b")
        original = await routes_clinical.record_fulfilment(first, actor=CLINICAL, background_tasks=None)
        latest = await routes_clinical.record_fulfilment(second, actor=CLINICAL, background_tasks=None)
        replayed = await routes_clinical.record_fulfilment(first, actor=CLINICAL, background_tasks=None)
        assert replayed == original
        current = await db.fulfilments.find_one({"_id": ObjectId(latest["fulfilment"]["id"])})
        assert current["operation_id"] == "issue-b"
        assert current["status"] == "fulfilled"

    run_camp(monkeypatch, run)
