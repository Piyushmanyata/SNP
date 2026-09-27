"""The Clinical operation runner through its interface: replay, refusal, claim, rollback and SMS dispatch."""

import asyncio

import pytest
from bson import ObjectId
from fastapi import HTTPException

import clinical_operation
import helpers
import routes_clinical
import sms
from clinical_operation import Operation
from models import CorrectionBody
from seed import TOMORROW, patient_doc, recorder, run_camp, seed_camp
from test_camp_operations_matrix import CLINICAL, _complete_body, _issue_body, _printed_patient


async def _patient(db):
    camp_id, _ = await seed_camp(db, venue="Hall A")
    patient = patient_doc(camp_id=camp_id, phone="9876500001", phone_normalized="9876500001")
    await db.patients.insert_one(patient)
    return patient


def _counting(db, patient_id, *, fail=False, intents=False):
    async def apply(patient, session):
        await db.patients.update_one({"_id": patient_id}, {"$inc": {"applied": 1}}, session=session)
        await db.applied.insert_one({"patient_id": patient_id}, session=session)
        ids = await sms.record(
            db, [patient], "ot_token", TOMORROW, "Hall A", event_key=str(ObjectId()), session=session, now=helpers.now_utc(),
        ) if intents else []
        if fail:
            raise RuntimeError("injected failure")
        return {"applied": (patient.get("applied") or 0) + 1}, ids
    return apply




def test_a_failure_inside_apply_rolls_back_and_the_retry_applies_once(monkeypatch):
    async def run(db):
        patient = await _patient(db)
        failing = Operation("issue", "op-1", patient["_id"], {"n": 1}, _counting(db, patient["_id"], fail=True))
        with pytest.raises(RuntimeError):
            await clinical_operation.run(db, failing)
        assert await db.applied.count_documents({}) == 0
        assert await db.clinical_operations.count_documents({}) == 0
        assert (await db.patients.find_one({"_id": patient["_id"]})).get("applied") is None
        working = Operation("issue", "op-1", patient["_id"], {"n": 1}, _counting(db, patient["_id"]))
        assert await clinical_operation.run(db, working) == {"applied": 1}
        assert await clinical_operation.run(db, working) == {"applied": 1}
        assert (await db.patients.find_one({"_id": patient["_id"]}))["applied"] == 1

    run_camp(monkeypatch, run)


def test_the_same_id_with_a_different_payload_or_kind_is_refused(monkeypatch):
    async def run(db):
        patient = await _patient(db)
        await clinical_operation.run(db, Operation("issue", "op-1", patient["_id"], {"n": 1}, _counting(db, patient["_id"])))
        for kind, payload in (("issue", {"n": 2}), ("correct", {"n": 1})):
            with pytest.raises(HTTPException) as exc:
                await clinical_operation.run(db, Operation(kind, "op-1", patient["_id"], payload, _counting(db, patient["_id"])))
            assert exc.value.detail["code"] == "OPERATION_CONFLICT"

    run_camp(monkeypatch, run)


def test_a_superseded_replay_is_refused(monkeypatch):
    async def run(db):
        patient = await _patient(db)
        operation = Operation(
            "complete", "op-1", patient["_id"], {"n": 1}, _counting(db, patient["_id"]),
            lambda current, result: "gone" if current.get("applied") != result["applied"] else None,
        )
        await clinical_operation.run(db, operation)
        await clinical_operation.run(db, operation)
        await db.patients.update_one({"_id": patient["_id"]}, {"$set": {"applied": 7}})
        with pytest.raises(HTTPException) as exc:
            await clinical_operation.run(db, operation)
        assert (exc.value.detail["code"], exc.value.detail["message"]) == ("OPERATION_SUPERSEDED", "gone")

    run_camp(monkeypatch, run)


def test_a_missing_patient_or_id_is_refused(monkeypatch):
    async def run(db):
        patient = await _patient(db)
        with pytest.raises(HTTPException) as exc:
            await clinical_operation.run(db, Operation("issue", None, patient["_id"], {}, _counting(db, patient["_id"])))
        assert (exc.value.status_code, exc.value.detail["code"]) == (400, "OPERATION_ID_IS_REQUIRED")
        with pytest.raises(HTTPException) as exc:
            await clinical_operation.run(db, Operation("issue", "op-2", ObjectId(), {}, _counting(db, patient["_id"])))
        assert (exc.value.status_code, exc.value.detail["code"]) == (404, "REGISTRATION_NOT_FOUND")

    run_camp(monkeypatch, run)


def test_two_writers_on_one_patient_both_apply_on_fresh_state(monkeypatch):
    async def run(db):
        patient = await _patient(db)
        first, second = await asyncio.gather(*(
            clinical_operation.run(db, Operation("issue", op_id, patient["_id"], {"op": op_id}, _counting(db, patient["_id"])))
            for op_id in ("op-a", "op-b")
        ))
        assert sorted([first["applied"], second["applied"]]) == [1, 2]
        assert (await db.patients.find_one({"_id": patient["_id"]}))["applied"] == 2

    run_camp(monkeypatch, run)


def test_sms_intents_are_sent_only_after_commit_and_never_on_replay(monkeypatch):
    sent = recorder()

    async def run(db):
        patient = await _patient(db)
        failing = Operation("issue", "op-1", patient["_id"], {}, _counting(db, patient["_id"], fail=True, intents=True))
        with pytest.raises(RuntimeError):
            await clinical_operation.run(db, failing)
        assert sent == [] and await db.reminder_ledger.count_documents({}) == 0
        working = Operation("issue", "op-1", patient["_id"], {}, _counting(db, patient["_id"], intents=True))
        await clinical_operation.run(db, working)
        await clinical_operation.run(db, working)
        assert [message["type"] for message in sent] == ["ot_token"]

    run_camp(monkeypatch, run)


@pytest.mark.parametrize("write", ["issue", "correction"])
def test_an_issue_or_correction_without_an_operation_id_is_refused(monkeypatch, write):
    async def run(db):
        _, _, patient = await _printed_patient(db)
        done = await routes_clinical.complete_prescription(_complete_body(patient["_id"], "complete"), actor=CLINICAL)
        with pytest.raises(HTTPException) as exc:
            if write == "issue":
                await routes_clinical.record_fulfilment(
                    _issue_body(done["transcription"]["id"], done["revision"]["id"], 1, None),
                    actor=CLINICAL, background_tasks=None,
                )
            else:
                await routes_clinical.add_correction(CorrectionBody(
                    patient_id=str(patient["_id"]), reason="Correct pressure", expected_generation=1,
                    full_transcription_confirmed=True, bp="130/85",
                ), actor=CLINICAL)
        assert (exc.value.status_code, exc.value.detail["code"]) == (400, "OPERATION_ID_IS_REQUIRED")
        assert await db.fulfilments.count_documents({}) == 0
        assert await db.prescription_revisions.count_documents({"kind": "correct"}) == 0

    run_camp(monkeypatch, run)
