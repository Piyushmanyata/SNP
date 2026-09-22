import asyncio

import pytest
from bson import ObjectId
from fastapi import HTTPException

from test_camp_operations_matrix import (
    CLINICAL, _complete_body, _issue_body, _mock, _printed_patient,
)
import routes_clinical
from models import CorrectionBody, TranscriptionBody, UndoCompletionBody


@pytest.mark.parametrize("foreign_patient", [False, True])
def test_orphan_revision_operation_rejects_a_different_request(monkeypatch, foreign_patient):
    async def run():
        db = _mock(monkeypatch)
        _, _, first = await _printed_patient(db)
        second = {**first, "_id": ObjectId(), "full_name": "Different Patient"}
        await db.patients.insert_one(second)
        original = routes_clinical.commit_completion

        async def fail_commit(*args, **kwargs):
            raise RuntimeError("injected commit failure")

        monkeypatch.setattr(routes_clinical, "commit_completion", fail_commit)
        with pytest.raises(RuntimeError):
            await routes_clinical.complete_prescription(_complete_body(first["_id"], "orphan"), actor=CLINICAL)
        monkeypatch.setattr(routes_clinical, "commit_completion", original)
        target = second if foreign_patient else first
        with pytest.raises(HTTPException) as exc:
            await routes_clinical.complete_prescription(
                _complete_body(target["_id"], "orphan", bp="150/90"), actor=CLINICAL,
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "operation_conflict"
        current = await db.patients.find_one({"_id": target["_id"]})
        assert not current.get("committed_revision_id")

    asyncio.run(run())


@pytest.mark.parametrize("foreign_patient", [False, True])
def test_issue_operation_rejects_a_different_request(monkeypatch, foreign_patient):
    async def run():
        db = _mock(monkeypatch)
        _, _, patient = await _printed_patient(db)
        done = await routes_clinical.complete_prescription(_complete_body(patient["_id"], "complete"), actor=CLINICAL)
        await routes_clinical.record_fulfilment(
            _issue_body(done["transcription"]["id"], done["revision"]["id"], 1, "issue"), actor=CLINICAL,
         background_tasks=None)
        if foreign_patient:
            other = {**patient, "_id": ObjectId(), "full_name": "Different Patient"}
            await db.patients.insert_one(other)
            done = await routes_clinical.complete_prescription(_complete_body(other["_id"], "complete-other"), actor=CLINICAL)
        with pytest.raises(HTTPException) as exc:
            await routes_clinical.record_fulfilment(
                _issue_body(done["transcription"]["id"], done["revision"]["id"], 1, "issue", status="not_available"),
                actor=CLINICAL,
             background_tasks=None)
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "operation_conflict"
        assert await db.fulfilments.count_documents({}) == 1

    asyncio.run(run())


@pytest.mark.parametrize("paused_function", ["_record_fulfilment", "_ensure_transcription_locked"])
def test_duplicate_inflight_issue_keeps_first_authorization(monkeypatch, paused_function):
    async def run():
        db = _mock(monkeypatch)
        _, _, patient = await _printed_patient(db)
        done = await routes_clinical.complete_prescription(_complete_body(patient["_id"], "complete"), actor=CLINICAL)
        body = _issue_body(done["transcription"]["id"], done["revision"]["id"], 1, "issue")
        entered = asyncio.Event()
        proceed = asyncio.Event()
        original = getattr(routes_clinical, paused_function)

        async def paused(*args, **kwargs):
            entered.set()
            await proceed.wait()
            return await original(*args, **kwargs)

        monkeypatch.setattr(routes_clinical, paused_function, paused)
        pending = asyncio.create_task(routes_clinical.record_fulfilment(body, actor=CLINICAL, background_tasks=None))
        await entered.wait()
        try:
            with pytest.raises(HTTPException) as exc:
                await routes_clinical.record_fulfilment(body, actor=CLINICAL, background_tasks=None)
            assert exc.value.status_code == 409
            current = await db.patients.find_one({"_id": patient["_id"]})
            assert current["issue_auth_op"] == "issue"
        finally:
            proceed.set()
            await pending

    asyncio.run(run())


def test_correction_can_clear_prescribed_lines_and_content(monkeypatch):
    async def run():
        db = _mock(monkeypatch)
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

    asyncio.run(run())


def test_draft_write_racing_completion_cannot_unlock_issued_prescription(monkeypatch):
    async def run():
        db = _mock(monkeypatch)
        _, _, patient = await _printed_patient(db)
        draft = await routes_clinical.create_transcription(
            TranscriptionBody(patient_id=str(patient["_id"]), bp="110/70"), actor=CLINICAL,
        )
        entered = asyncio.Event()
        proceed = asyncio.Event()
        original = db.transcriptions.find_one_and_update

        async def paused(query, update, **kwargs):
            if update.get("$set", {}).get("locked") is False:
                entered.set()
                await proceed.wait()
            return await original(query, update, **kwargs)

        monkeypatch.setattr(db.transcriptions, "find_one_and_update", paused)
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

    asyncio.run(run())


def test_draft_write_cannot_overwrite_active_clinical_claim(monkeypatch):
    async def run():
        db = _mock(monkeypatch)
        _, _, patient = await _printed_patient(db)
        draft = await routes_clinical.create_transcription(
            TranscriptionBody(patient_id=str(patient["_id"]), bp="110/70"), actor=CLINICAL,
        )
        async with routes_clinical._clinical_write(db, draft["transcription"]["id"]):
            with pytest.raises(HTTPException) as exc:
                await routes_clinical.create_transcription(
                    TranscriptionBody(patient_id=str(patient["_id"]), bp="999/99"), actor=CLINICAL,
                )
            assert exc.value.status_code == 409
        current = await db.transcriptions.find_one({"_id": ObjectId(draft["transcription"]["id"])})
        assert current["bp"] == "110/70"

    asyncio.run(run())


def test_undo_cannot_race_a_completed_issue(monkeypatch):
    async def run():
        db = _mock(monkeypatch)
        _, _, patient = await _printed_patient(db)
        done = await routes_clinical.complete_prescription(_complete_body(patient["_id"], "complete"), actor=CLINICAL)
        entered = asyncio.Event()
        proceed = asyncio.Event()
        original = routes_clinical.commit_undo

        async def paused(*args, **kwargs):
            entered.set()
            await proceed.wait()
            return await original(*args, **kwargs)

        monkeypatch.setattr(routes_clinical, "commit_undo", paused)
        pending = asyncio.create_task(routes_clinical.undo_completion(UndoCompletionBody(
            patient_id=str(patient["_id"]), operation_id="undo", expected_generation=1,
            reason="Entered in error",
        ), actor=CLINICAL))
        await entered.wait()
        try:
            with pytest.raises(HTTPException) as exc:
                await routes_clinical.record_fulfilment(
                    _issue_body(done["transcription"]["id"], done["revision"]["id"], 1, "issue"), actor=CLINICAL,
                 background_tasks=None)
            assert exc.value.status_code == 409
        finally:
            proceed.set()
            await pending
        assert await db.fulfilments.count_documents({}) == 0

    asyncio.run(run())


def test_correction_without_transcription_id_obeys_the_write_claim(monkeypatch):
    async def run():
        db = _mock(monkeypatch)
        _, _, patient = await _printed_patient(db)
        done = await routes_clinical.complete_prescription(_complete_body(patient["_id"], "complete"), actor=CLINICAL)
        async with routes_clinical._clinical_write(db, done["transcription"]["id"]):
            with pytest.raises(HTTPException) as exc:
                await routes_clinical.add_correction(CorrectionBody(
                    patient_id=str(patient["_id"]), reason="Correct pressure", operation_id="correct",
                    expected_generation=1, full_transcription_confirmed=True, bp="130/85",
                ), actor=CLINICAL)
            assert exc.value.status_code == 409
        current = await db.patients.find_one({"_id": patient["_id"]})
        assert current["clinical_generation"] == 1

    asyncio.run(run())


@pytest.mark.parametrize("failure_stage", ["transcription", "ledger"])
def test_completion_retry_recovers_writes_after_patient_commit(monkeypatch, failure_stage):
    async def run():
        db = _mock(monkeypatch)
        _, _, patient = await _printed_patient(db)
        body = _complete_body(patient["_id"], "complete")
        target = "_upsert_transcription" if failure_stage == "transcription" else "save_operation"
        original = getattr(routes_clinical, target)

        async def failed(*args, **kwargs):
            if target == "save_operation" or kwargs.get("locked"):
                raise RuntimeError("injected completion failure")
            return await original(*args, **kwargs)

        monkeypatch.setattr(routes_clinical, target, failed)
        with pytest.raises(RuntimeError):
            await routes_clinical.complete_prescription(body, actor=CLINICAL)
        committed = await db.patients.find_one({"_id": patient["_id"]})
        assert committed["clinical_generation"] == 1
        monkeypatch.setattr(routes_clinical, target, original)
        result = await routes_clinical.complete_prescription(body, actor=CLINICAL)
        assert result["registration"]["clinical_generation"] == 1
        assert result["transcription"]["locked"] is True
        assert await db.prescription_revisions.count_documents({}) == 1
        assert await routes_clinical.complete_prescription(body, actor=CLINICAL) == result

    asyncio.run(run())


def test_completion_obeys_an_existing_clinical_write_claim(monkeypatch):
    async def run():
        db = _mock(monkeypatch)
        _, _, patient = await _printed_patient(db)
        draft = await routes_clinical.create_transcription(
            TranscriptionBody(patient_id=str(patient["_id"]), bp="110/70"), actor=CLINICAL,
        )
        async with routes_clinical._clinical_write(db, draft["transcription"]["id"]):
            with pytest.raises(HTTPException) as exc:
                await routes_clinical.complete_prescription(_complete_body(patient["_id"], "complete"), actor=CLINICAL)
            assert exc.value.status_code == 409
        current = await db.patients.find_one({"_id": patient["_id"]})
        assert not current.get("committed_revision_id")

    asyncio.run(run())


@pytest.mark.parametrize("failure_stage", ["transcription", "audit", "ledger"])
def test_correction_retry_applies_one_generation(monkeypatch, failure_stage):
    async def run():
        db = _mock(monkeypatch)
        _, _, patient = await _printed_patient(db)
        done = await routes_clinical.complete_prescription(
            _complete_body(patient["_id"], "complete"), actor=CLINICAL,
        )
        body = CorrectionBody(
            patient_id=str(patient["_id"]), reason="Correct pressure", operation_id="correct-1",
            expected_generation=done["registration"]["clinical_generation"],
            full_transcription_confirmed=True, bp="130/85",
        )
        if failure_stage == "transcription":
            original = routes_clinical._upsert_transcription

            async def failed(*args, **kwargs):
                if kwargs.get("locked"):
                    raise RuntimeError("injected correction failure")
                return await original(*args, **kwargs)

            monkeypatch.setattr(routes_clinical, "_upsert_transcription", failed)
            restore = lambda: monkeypatch.setattr(routes_clinical, "_upsert_transcription", original)
        elif failure_stage == "audit":
            original_insert = db.corrections.insert_one

            async def failed(*args, **kwargs):
                raise RuntimeError("injected correction failure")

            monkeypatch.setattr(db.corrections, "insert_one", failed)
            restore = lambda: monkeypatch.setattr(db.corrections, "insert_one", original_insert)
        else:
            original = routes_clinical.save_operation

            async def failed(db_arg, doc):
                if doc.get("status") == "committed" and doc.get("kind") == "correct":
                    raise RuntimeError("injected correction failure")
                return await original(db_arg, doc)

            monkeypatch.setattr(routes_clinical, "save_operation", failed)
            restore = lambda: monkeypatch.setattr(routes_clinical, "save_operation", original)

        with pytest.raises(RuntimeError):
            await routes_clinical.add_correction(body, actor=CLINICAL)
        restore()
        result = await routes_clinical.add_correction(body, actor=CLINICAL)
        assert result["registration"]["clinical_generation"] == 2
        assert await db.prescription_revisions.count_documents({"kind": "correct"}) == 1
        assert await db.corrections.count_documents({}) == 1
        assert await routes_clinical.add_correction(body, actor=CLINICAL) == result

        changed = body.model_copy(update={"bp": "140/90"})
        with pytest.raises(HTTPException) as exc:
            await routes_clinical.add_correction(changed, actor=CLINICAL)
        assert exc.value.detail["code"] == "operation_conflict"

    asyncio.run(run())


def test_undo_retry_clears_one_completion(monkeypatch):
    async def run():
        db = _mock(monkeypatch)
        _, _, patient = await _printed_patient(db)
        done = await routes_clinical.complete_prescription(
            _complete_body(patient["_id"], "complete"), actor=CLINICAL,
        )
        body = UndoCompletionBody(
            patient_id=str(patient["_id"]),
            expected_generation=done["registration"]["clinical_generation"],
            reason="Wrong patient", operation_id="undo-1",
        )
        original = routes_clinical.save_operation

        async def failed(db_arg, doc):
            if doc.get("status") == "committed" and doc.get("kind") == "undo":
                raise RuntimeError("injected undo failure")
            return await original(db_arg, doc)

        monkeypatch.setattr(routes_clinical, "save_operation", failed)
        with pytest.raises(RuntimeError):
            await routes_clinical.undo_completion(body, actor=CLINICAL)
        monkeypatch.setattr(routes_clinical, "save_operation", original)
        result = await routes_clinical.undo_completion(body, actor=CLINICAL)
        assert result["registration"]["clinical_generation"] == 2
        assert result["registration"]["committed_revision_id"] is None
        assert result["transcription"]["locked"] is False
        again = await routes_clinical.undo_completion(body, actor=CLINICAL)
        assert again == result
        current = await db.patients.find_one({"_id": patient["_id"]})
        assert current["clinical_generation"] == 2

    asyncio.run(run())


def test_malformed_correction_content_is_rejected_before_processing(monkeypatch):
    async def run():
        db = _mock(monkeypatch)
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

    asyncio.run(run())


def test_late_issue_retry_preserves_the_newer_outcome(monkeypatch):
    async def run():
        db = _mock(monkeypatch)
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

    asyncio.run(run())


def test_paused_pending_issue_rechecks_history_after_retry_and_newer_issue(monkeypatch):
    async def run():
        db = _mock(monkeypatch)
        _, _, patient = await _printed_patient(db)
        done = await routes_clinical.complete_prescription(_complete_body(patient["_id"], "complete"), actor=CLINICAL)
        first = _issue_body(done["transcription"]["id"], done["revision"]["id"], 1, "issue-a", status="not_available")
        second = _issue_body(done["transcription"]["id"], done["revision"]["id"], 1, "issue-b")
        entered, proceed = asyncio.Event(), asyncio.Event()
        original = routes_clinical.save_operation

        async def pause_pending(db, doc):
            result = await original(db, doc)
            if doc["operation_id"] == "issue-a" and doc["status"] == "pending" and not entered.is_set():
                entered.set()
                await proceed.wait()
            return result

        monkeypatch.setattr(routes_clinical, "save_operation", pause_pending)
        pending = asyncio.create_task(routes_clinical.record_fulfilment(first, actor=CLINICAL, background_tasks=None))
        await entered.wait()
        try:
            replayed = await routes_clinical.record_fulfilment(first, actor=CLINICAL, background_tasks=None)
            latest = await routes_clinical.record_fulfilment(second, actor=CLINICAL, background_tasks=None)
        finally:
            proceed.set()
        resumed = await pending
        current = await db.fulfilments.find_one({"_id": ObjectId(latest["fulfilment"]["id"])})
        assert current["operation_id"] == "issue-b"
        assert current["status"] == "fulfilled"
        assert resumed == replayed
        assert (await db.patients.find_one({"_id": patient["_id"]}))["issue_auth_op"] is None

    asyncio.run(run())


@pytest.mark.parametrize("failure_stage", ["before_release", "after_release"])
def test_issue_retry_finishes_failed_cleanup_without_releasing_ot_twice(monkeypatch, failure_stage):
    async def run():
        db = _mock(monkeypatch)
        camp, _, patient = await _printed_patient(db)
        done = await routes_clinical.complete_prescription(_complete_body(
            patient["_id"], "complete", prescribed_lines=["ot"],
            prescribed_medicine_ids=[], ot_eye="right", ot_outcome="iol_surgery",
        ), actor=CLINICAL)
        old_day, new_day = ObjectId(), ObjectId()
        for day in (old_day, new_day):
            await db.ot_schedule_days.insert_one({
                "_id": day, "camp_id": camp, "day_date": "2099-10-02",
                "venue": "OT", "seat_limit": 10, "seats_taken": 0,
            })
        first = _issue_body(done["transcription"]["id"], done["revision"]["id"], 1, "ot-a",
                            item_type="ot", status="deferred", ot_schedule_day_id=str(old_day))
        second = _issue_body(done["transcription"]["id"], done["revision"]["id"], 1, "ot-b",
                             item_type="ot", status="deferred", ot_schedule_day_id=str(new_day))
        await routes_clinical.record_fulfilment(first, actor=CLINICAL, background_tasks=None)
        await db.ot_schedule_days.update_one({"_id": old_day}, {"$inc": {"seats_taken": 1}})
        original = routes_clinical._ensure_transcription_locked

        async def fail_lock(*args, **kwargs):
            raise RuntimeError("injected finalization failure")

        original_update = db.ot_schedule_days.update_one

        async def fail_release(query, update, **kwargs):
            if query.get("_id") == old_day and update.get("$inc", {}).get("seats_taken") == -1:
                raise RuntimeError("injected finalization failure")
            return await original_update(query, update, **kwargs)

        if failure_stage == "after_release":
            monkeypatch.setattr(routes_clinical, "_ensure_transcription_locked", fail_lock)
        else:
            monkeypatch.setattr(db.ot_schedule_days, "update_one", fail_release)
        with pytest.raises(RuntimeError):
            await routes_clinical.record_fulfilment(second, actor=CLINICAL, background_tasks=None)
        current = await db.patients.find_one({"_id": patient["_id"]})
        assert current["issue_auth_op"] == "ot-b"
        monkeypatch.setattr(routes_clinical, "_ensure_transcription_locked", original)
        monkeypatch.setattr(db.ot_schedule_days, "update_one", original_update)
        result = await routes_clinical.record_fulfilment(second, actor=CLINICAL, background_tasks=None)
        assert result["fulfilment"]["status"] == "deferred"
        current = await db.patients.find_one({"_id": patient["_id"]})
        assert current["issue_auth_op"] is None
        assert (await db.ot_schedule_days.find_one({"_id": old_day}))["seats_taken"] == 1
        assert (await db.ot_schedule_days.find_one({"_id": new_day}))["seats_taken"] == 1
        assert await db.deferred_slips.count_documents({"active": True}) == 1
        assert await db.deferred_slips.count_documents({"ot_schedule_day_id": old_day, "active": True}) == 0
        assert await routes_clinical.record_fulfilment(second, actor=CLINICAL, background_tasks=None) == result

    asyncio.run(run())
