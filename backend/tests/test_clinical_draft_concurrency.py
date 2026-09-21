import asyncio

import pytest
from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from test_camp_operations_matrix import (
    CLINICAL, _complete_body, _mock, _printed_patient,
)
import routes_clinical
from models import TranscriptionBody


def _unique_patient_index(db, monkeypatch):
    original = db.transcriptions.insert_one

    async def guarded(doc):
        if await db.transcriptions.find_one({"patient_id": doc["patient_id"]}):
            raise DuplicateKeyError("transcriptions.patient_id")
        return await original(doc)

    monkeypatch.setattr(db.transcriptions, "insert_one", guarded)


def _hold_first_insert(db, monkeypatch):
    original = db.transcriptions.insert_one
    entered = asyncio.Event()
    proceed = asyncio.Event()
    seen = []

    async def held(doc):
        if not seen:
            seen.append(doc)
            entered.set()
            await proceed.wait()
        return await original(doc)

    monkeypatch.setattr(db.transcriptions, "insert_one", held)
    return entered, proceed


async def _save_draft(patient, version, bp):
    return await routes_clinical.create_transcription(
        TranscriptionBody(patient_id=str(patient["_id"]), bp=bp, expected_draft_version=version),
        actor=CLINICAL,
    )


def test_second_operator_at_the_same_version_gets_a_draft_conflict(monkeypatch):
    async def run():
        db = _mock(monkeypatch)
        _, _, patient = await _printed_patient(db)
        created = await _save_draft(patient, 0, "110/70")
        loaded = (await _save_draft(patient, created["transcription"]["draft_version"], "120/80"))
        version = loaded["transcription"]["draft_version"]
        assert version == 1
        first = await _save_draft(patient, version, "130/90")
        assert first["transcription"]["draft_version"] == 2
        with pytest.raises(HTTPException) as exc:
            await _save_draft(patient, version, "999/99")
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "draft_version_conflict"
        current = await db.transcriptions.find_one({"patient_id": patient["_id"]})
        assert current["bp"] == "130/90"
        assert current["draft_version"] == 2

    asyncio.run(run())


def test_legacy_draft_without_a_version_accepts_one_save_then_requires_the_stamp(monkeypatch):
    async def run():
        db = _mock(monkeypatch)
        _, _, patient = await _printed_patient(db)
        await db.transcriptions.insert_one({
            "_id": ObjectId(), "patient_id": patient["_id"], "person_id": patient.get("person_id"),
            "camp_id": patient["camp_id"], "created_by": str(CLINICAL["_id"]), "bp": "100/60",
            "locked": False,
        })
        saved = await _save_draft(patient, 0, "110/70")
        assert saved["transcription"]["draft_version"] == 1
        with pytest.raises(HTTPException) as exc:
            await _save_draft(patient, 0, "999/99")
        assert exc.value.detail["code"] == "draft_version_conflict"
        current = await db.transcriptions.find_one({"patient_id": patient["_id"]})
        assert current["bp"] == "110/70"

    asyncio.run(run())


def test_simultaneous_new_draft_creation_resolves_to_one_draft(monkeypatch):
    async def run():
        db = _mock(monkeypatch)
        _, _, patient = await _printed_patient(db)
        _unique_patient_index(db, monkeypatch)
        entered, proceed = _hold_first_insert(db, monkeypatch)
        first = asyncio.create_task(_save_draft(patient, 0, "110/70"))
        await entered.wait()
        second = asyncio.create_task(_save_draft(patient, 0, "120/80"))
        await second
        proceed.set()
        outcomes = await asyncio.gather(first, return_exceptions=True)
        loser = outcomes[0]
        assert isinstance(loser, HTTPException)
        assert loser.status_code == 409
        assert loser.detail["code"] == "draft_version_conflict"
        assert await db.transcriptions.count_documents({}) == 1
        current = await db.transcriptions.find_one({"patient_id": patient["_id"]})
        assert current["bp"] == "120/80"

    asyncio.run(run())


def test_late_initial_save_cannot_overwrite_a_completed_prescription(monkeypatch):
    async def run():
        db = _mock(monkeypatch)
        _, _, patient = await _printed_patient(db)
        _unique_patient_index(db, monkeypatch)
        entered, proceed = _hold_first_insert(db, monkeypatch)
        late = asyncio.create_task(_save_draft(patient, 0, "110/70"))
        await entered.wait()
        await _save_draft(patient, 0, "120/80")
        done = await routes_clinical.complete_prescription(
            _complete_body(patient["_id"], "complete", expected_draft_version=0), actor=CLINICAL,
        )
        assert done["transcription"]["locked"] is True
        proceed.set()
        with pytest.raises(HTTPException) as exc:
            await late
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "draft_version_conflict"
        assert await db.transcriptions.count_documents({}) == 1
        current = await db.transcriptions.find_one({"patient_id": patient["_id"]})
        assert current["bp"] == "120/80"
        assert current["locked"] is True

    asyncio.run(run())


def test_completion_cannot_apply_a_stale_draft_over_a_newer_save(monkeypatch):
    async def run():
        db = _mock(monkeypatch)
        _, _, patient = await _printed_patient(db)
        await _save_draft(patient, 0, "110/70")
        await _save_draft(patient, 0, "120/80")
        with pytest.raises(HTTPException) as exc:
            await routes_clinical.complete_prescription(
                _complete_body(patient["_id"], "stale", expected_draft_version=0, bp="90/60"),
                actor=CLINICAL,
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "draft_version_conflict"
        current = await db.patients.find_one({"_id": patient["_id"]})
        assert not current.get("committed_revision_id")
        draft = await db.transcriptions.find_one({"patient_id": patient["_id"]})
        assert draft["bp"] == "120/80"
        assert draft["locked"] is False
        assert draft.get("clinical_write_token") is None
        done = await routes_clinical.complete_prescription(
            _complete_body(patient["_id"], "fresh", expected_draft_version=1), actor=CLINICAL,
        )
        assert done["registration"]["clinical_generation"] == 1
        assert done["transcription"]["locked"] is True

    asyncio.run(run())


def test_a_lone_operator_can_edit_then_complete_without_sending_a_version(monkeypatch):
    async def run():
        db = _mock(monkeypatch)
        _camp, _day, patient = await _printed_patient(db)
        pid = str(patient["_id"])

        await routes_clinical.create_transcription(
            TranscriptionBody(patient_id=pid, diagnosis_options=["Cataract"], bp="130/85"),
            actor=CLINICAL,
        )
        await routes_clinical.create_transcription(
            TranscriptionBody(patient_id=pid, diagnosis_options=["Cataract"], bp="120/80"),
            actor=CLINICAL,
        )
        assert (await db.transcriptions.find_one({}))["draft_version"] == 1

        done = await routes_clinical.complete_prescription(
            _complete_body(pid, "op-lone-operator"), actor=CLINICAL,
        )
        assert done["transcription"]["locked"] is True

    asyncio.run(run())


def test_an_unversioned_save_still_advances_the_version_for_versioned_clients(monkeypatch):
    async def run():
        db = _mock(monkeypatch)
        _camp, _day, patient = await _printed_patient(db)
        pid = str(patient["_id"])

        await routes_clinical.create_transcription(
            TranscriptionBody(patient_id=pid, diagnosis_options=["Cataract"]), actor=CLINICAL,
        )
        await routes_clinical.create_transcription(
            TranscriptionBody(patient_id=pid, diagnosis_options=["Glaucoma"]), actor=CLINICAL,
        )

        with pytest.raises(HTTPException) as exc:
            await routes_clinical.create_transcription(
                TranscriptionBody(
                    patient_id=pid, diagnosis_options=["Presbyopia"], expected_draft_version=0,
                ),
                actor=CLINICAL,
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "draft_version_conflict"

    asyncio.run(run())


def test_a_draft_predating_the_version_field_can_still_be_saved(monkeypatch):
    async def run():
        db = _mock(monkeypatch)
        _camp, _day, patient = await _printed_patient(db)
        pid = str(patient["_id"])

        await db.transcriptions.insert_one({
            "patient_id": patient["_id"],
            "camp_id": patient["camp_id"],
            "diagnosis_options": ["Cataract"],
            "locked": False,
        })
        legacy = await db.transcriptions.find_one({})
        assert "draft_version" not in legacy

        served = routes_clinical.ser_trans(legacy)
        assert served["draft_version"] == 0

        saved = await routes_clinical.create_transcription(
            TranscriptionBody(
                patient_id=pid, diagnosis_options=["Glaucoma"], expected_draft_version=0,
            ),
            actor=CLINICAL,
        )
        assert saved["transcription"]["draft_version"] == 1

    asyncio.run(run())
