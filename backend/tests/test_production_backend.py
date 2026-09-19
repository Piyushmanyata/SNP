import asyncio
from datetime import timedelta

import pytest
from bson import ObjectId
from fastapi import HTTPException

from test_camp_lifecycle import RX, _fulfil, _mock, _seen_patient_with_transcription
import routes_clinical
from helpers import now_ist
from models import CorrectionBody, OtScheduleBody
from fastapi import BackgroundTasks


def test_surgery_venue_is_admin_typed_and_required(monkeypatch):
    async def run():
        database = _mock(monkeypatch)
        camp_id, _, trans_id = await _seen_patient_with_transcription(database, RX)
        await database.camps.insert_one({"_id": camp_id, "is_active": True})
        actor = {"_id": ObjectId(), "role": "clinical_desk_operator"}
        with pytest.raises(HTTPException) as error:
            await routes_clinical.record_fulfilment(_fulfil(
                trans_id, database.last_rev_id, item_type="ot", status="fulfilled",
            ), actor=actor, background_tasks=None)
        assert error.value.status_code == 400
        admin = {"_id": ObjectId(), "role": "admin"}
        tomorrow = (now_ist() + timedelta(days=1)).date().isoformat()
        result = await routes_clinical.create_ot_day(OtScheduleBody(
            camp_id=str(camp_id), day_date=tomorrow,
            venue="District Hospital, Deoghar", venue_sms="जिला अस्पताल", seat_limit=20,
        ), actor=admin)
        assert result["ot_day"]["venue"] == "District Hospital, Deoghar"
        assert result["ot_day"]["venue_sms"] == "जिला अस्पताल"
        with pytest.raises(HTTPException) as error:
            await routes_clinical.create_ot_day(OtScheduleBody(
                camp_id=str(camp_id), day_date=(now_ist() + timedelta(days=2)).date().isoformat(),
                venue="   ", seat_limit=20,
            ), actor=admin)
        assert error.value.status_code == 400
        plain = await routes_clinical.create_ot_day(OtScheduleBody(
            camp_id=str(camp_id), day_date=(now_ist() + timedelta(days=3)).date().isoformat(),
            venue="Sadar Hospital", seat_limit=20,
        ), actor=admin)
        assert plain["ot_day"]["venue_sms"] is None
        with pytest.raises(HTTPException) as error:
            await routes_clinical.create_ot_day(OtScheduleBody(
                camp_id=str(camp_id), day_date="2020-01-01", venue="Camp tent", seat_limit=20,
            ), actor=admin)
        assert error.value.status_code == 400
    asyncio.run(run())


def test_patient_history_uses_three_queries_for_twenty_visits(monkeypatch):
    async def run():
        database = _mock(monkeypatch)
        camp_id, patient_id, trans_id = await _seen_patient_with_transcription(database, RX)
        person_id = ObjectId()
        await database.camps.insert_one({"_id": camp_id, "name": "Eye camp"})
        await database.transcriptions.update_one({"_id": trans_id}, {"$set": {"person_id": person_id, "created_at": now_ist()}})
        original = await database.transcriptions.find_one({"_id": trans_id})
        for _ in range(19):
            await database.transcriptions.insert_one({**original, "_id": ObjectId()})
        database.query_count = 0
        result = await routes_clinical.clinical_history(str(person_id), actor={"_id": ObjectId(), "role": "clinical_desk_operator"})
        assert len(result["history"]) == 20
        assert all(visit["camp_name"] == "Eye camp" for visit in result["history"])
        assert database.query_count <= 3
    asyncio.run(run())


def test_hospital_token_response_does_not_wait_for_sms(monkeypatch):
    async def run():
        database = _mock(monkeypatch)
        camp_id, _, trans_id = await _seen_patient_with_transcription(database, RX)
        day_id = ObjectId()
        await database.ot_schedule_days.insert_one({
            "_id": day_id, "camp_id": camp_id, "day_date": "2026-10-02",
            "venue": "Hospital", "seat_limit": 10, "seats_taken": 0,
        })
        sent = []

        async def provider(*args, **kwargs):
            sent.append(True)

        monkeypatch.setattr(routes_clinical.sms, "send_patient_sms", provider)
        background = BackgroundTasks()
        result = await routes_clinical.record_fulfilment(_fulfil(
            trans_id, database.last_rev_id, item_type="ot", status="deferred",
            ot_schedule_day_id=str(day_id),
        ), actor={"_id": ObjectId(), "role": "clinical_desk_operator"}, background_tasks=background)
        assert result["slip"]["active"] is True
        assert sent == []
        await background()
        assert sent == [True]
    asyncio.run(run())


def test_correction_rejects_values_that_would_break_the_prescription_screen(monkeypatch):
    async def run():
        database = _mock(monkeypatch)
        _, _, trans_id = await _seen_patient_with_transcription(database, RX)
        with pytest.raises(HTTPException) as error:
            await routes_clinical.add_correction(CorrectionBody(
                transcription_id=str(trans_id), reason="Correct blood pressure",
                changes={"bp": {"invalid": "object"}},
            ), actor={"_id": ObjectId(), "role": "clinical_desk_operator"})
        assert error.value.status_code == 400
        assert await database.corrections.count_documents({"transcription_id": trans_id}) == 0
    asyncio.run(run())
