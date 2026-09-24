import pytest
from bson import ObjectId
from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError

import routes_clinical
from conftest import CommandLog
from models import CorrectionBody, OtScheduleBody
from seed import ADMIN, CLINICAL, NOW, TOMORROW, day, fulfil, patient_doc, run_camp, seed_camp, seen_patient


def test_surgery_venue_is_admin_typed_and_required(monkeypatch):
    async def body(database):
        camp_id, _ = await seed_camp(database, days=())
        seen = await seen_patient(database, camp_id)
        with pytest.raises(HTTPException) as error:
            await routes_clinical.record_fulfilment(fulfil(
                seen["trans_id"], seen["rev_id"], item_type="ot", status="fulfilled",
            ), actor=CLINICAL, background_tasks=None)
        assert error.value.status_code == 400
        result = await routes_clinical.create_ot_day(OtScheduleBody(
            camp_id=str(camp_id), day_date=TOMORROW,
            venue="District Hospital, Deoghar", venue_sms="जिला अस्पताल", seat_limit=20,
        ), actor=ADMIN)
        assert result["ot_day"]["venue"] == "District Hospital, Deoghar"
        assert result["ot_day"]["venue_sms"] == "जिला अस्पताल"
        with pytest.raises(HTTPException) as error:
            await routes_clinical.create_ot_day(OtScheduleBody(
                camp_id=str(camp_id), day_date=day(2), venue="   ", seat_limit=20,
            ), actor=ADMIN)
        assert error.value.status_code == 400
        plain = await routes_clinical.create_ot_day(OtScheduleBody(
            camp_id=str(camp_id), day_date=day(3), venue="Sadar Hospital", seat_limit=20,
        ), actor=ADMIN)
        assert plain["ot_day"]["venue_sms"] is None
        with pytest.raises(HTTPException) as error:
            await routes_clinical.create_ot_day(OtScheduleBody(
                camp_id=str(camp_id), day_date="2020-01-01", venue="Camp tent", seat_limit=20,
            ), actor=ADMIN)
        assert error.value.status_code == 400

    run_camp(monkeypatch, body)


def test_long_surgery_venue_requires_short_dlt_name():
    with pytest.raises(ValidationError):
        OtScheduleBody(camp_id=str(ObjectId()), day_date=TOMORROW, venue="A" * 41, seat_limit=20)
    with pytest.raises(ValidationError):
        OtScheduleBody(camp_id=str(ObjectId()), day_date=TOMORROW, venue="A" * 41, venue_sms="B" * 41, seat_limit=20)


def test_patient_history_uses_three_queries_for_twenty_visits(monkeypatch):
    log = CommandLog()

    async def body(database):
        camp_id = (await database.camps.insert_one({"name": "Eye camp"})).inserted_id
        person_id = ObjectId()
        patients = [patient_doc(camp_id=camp_id) for _ in range(20)]
        await database.patients.insert_many(patients)
        await database.transcriptions.insert_many([
            {"patient_id": p["_id"], "camp_id": camp_id, "person_id": person_id, "created_at": NOW} for p in patients
        ])
        log.commands.clear()
        result = await routes_clinical.clinical_history(str(person_id), actor=CLINICAL)
        assert len(result["history"]) == 20
        assert all(visit["camp_name"] == "Eye camp" for visit in result["history"])
        assert len(log.commands) <= 3

    run_camp(monkeypatch, body, listener=log)


def test_hospital_token_response_does_not_wait_for_sms(monkeypatch):
    async def body(database):
        seen = await seen_patient(database)
        day_id = (await database.ot_schedule_days.insert_one({
            "camp_id": seen["camp_id"], "day_date": TOMORROW, "venue": "Hospital", "seat_limit": 10, "seats_taken": 0,
        })).inserted_id
        sent = []

        async def provider(*args, **kwargs):
            sent.append(True)

        monkeypatch.setattr(routes_clinical.sms, "send_patient_sms", provider)
        background = BackgroundTasks()
        result = await routes_clinical.record_fulfilment(fulfil(
            seen["trans_id"], seen["rev_id"], item_type="ot", status="deferred", ot_schedule_day_id=str(day_id),
        ), actor=CLINICAL, background_tasks=background)
        assert result["slip"]["active"] is True
        assert sent == []
        await background()
        assert sent == [True]

    run_camp(monkeypatch, body)


def test_correction_rejects_values_that_would_break_the_prescription_screen(monkeypatch):
    async def body(database):
        seen = await seen_patient(database)
        with pytest.raises(HTTPException) as error:
            await routes_clinical.add_correction(CorrectionBody(
                transcription_id=str(seen["trans_id"]), reason="Correct blood pressure",
                changes={"bp": {"invalid": "object"}},
            ), actor=CLINICAL)
        assert error.value.status_code == 400
        assert await database.corrections.count_documents({"transcription_id": seen["trans_id"]}) == 0

    run_camp(monkeypatch, body)
