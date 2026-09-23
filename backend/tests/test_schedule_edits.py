import asyncio

import pytest
from bson import ObjectId
from fastapi import BackgroundTasks, HTTPException

import routes_camps
import routes_clinical
import sms
from models import CampDayBody, OtScheduleBody
from test_camp_lifecycle import _mock, _recorder, _register, _seed_camp, OTHER_DAY, TODAY


async def _update_camp_day(*args, **kwargs):
    tasks = BackgroundTasks()
    result = await routes_camps.update_camp_day(*args, **kwargs, background_tasks=tasks)
    await tasks()
    return result


async def _update_ot_day(*args, **kwargs):
    tasks = BackgroundTasks()
    result = await routes_clinical.update_ot_day(*args, **kwargs, background_tasks=tasks)
    await tasks()
    return result


def test_camp_day_list_reports_bookings_above_reduced_seats(monkeypatch):
    async def run():
        db = _mock(monkeypatch)
        camp_id, (day_id,) = await _seed_camp(db, days=(OTHER_DAY,))
        await db.camp_days.update_one({"_id": day_id}, {"$set": {"booked": 3, "seat_limit": 2}})

        listed = await routes_camps.list_days(str(camp_id), actor={})

        assert listed["days"][0]["booked"] == 3
        assert listed["days"][0]["over_capacity"] is True

    asyncio.run(run())


def test_camp_day_move_keeps_bookings_and_sends_new_date(monkeypatch):
    async def run():
        db = _mock(monkeypatch)
        sent = _recorder(monkeypatch)
        camp_id, (day_id,) = await _seed_camp(db, days=(OTHER_DAY,))
        await db.camps.update_one({"_id": camp_id}, {"$set": {"venue_sms": "Short Camp Venue", "camp_date": OTHER_DAY}})
        registered = await _register(day_id, manual_entry=True)
        await _register(day_id, full_name="Ram Prasad", manual_entry=True)
        sent.clear()

        tasks = BackgroundTasks()
        result = await routes_camps.update_camp_day(
            str(day_id), CampDayBody(camp_id=str(camp_id), day_date="2026-09-05", seat_limit=1),
            actor={}, background_tasks=tasks,
        )
        assert sent == []
        await tasks()
        assert result["day"]["day_date"] == "2026-09-05"
        assert result["day"]["seat_limit"] == 1
        assert await db.patients.count_documents({"booked_camp_day_id": day_id}) == 2
        assert (await db.camps.find_one({"_id": camp_id}))["camp_date"] == "2026-09-05"
        with pytest.raises(HTTPException) as full:
            await _register(day_id, full_name="Third Patient", manual_entry=True)
        assert full.value.status_code == 409
        assert len(sent) == 2
        assert all(s["type"] == "registration" and s["date"] == "05-09-2026" for s in sent)
        assert sent[0]["reg_no"] == registered["reg_no"]
        await _update_camp_day(
            str(day_id), CampDayBody(camp_id=str(camp_id), day_date=OTHER_DAY, seat_limit=2), actor={}
        )
        assert len(sent) == 4
        assert [s["date"] for s in sent[2:]] == ["03-09-2026", "03-09-2026"]

    asyncio.run(run())


def test_ot_day_seats_cannot_drop_below_assigned(monkeypatch):
    async def run():
        db = _mock(monkeypatch)
        camp_id, _ = await _seed_camp(db)
        day_id = ObjectId()
        await db.ot_schedule_days.insert_one({"_id": day_id, "camp_id": camp_id, "day_date": OTHER_DAY,
                                               "venue": "Old Hospital", "venue_sms": None,
                                               "seat_limit": 3, "seats_taken": 2})
        with pytest.raises(HTTPException) as exc:
            await _update_ot_day(
                str(day_id), OtScheduleBody(camp_id=str(camp_id), day_date="2026-09-05",
                                            seat_limit=1, venue="New Hospital", venue_sms=None), actor={}
            )
        assert exc.value.status_code == 409
        assert (await db.ot_schedule_days.find_one({"_id": day_id}))["day_date"] == OTHER_DAY

    asyncio.run(run())


def test_completed_ot_day_cannot_move(monkeypatch):
    async def run():
        db = _mock(monkeypatch)
        camp_id, _ = await _seed_camp(db)
        day_id = ObjectId()
        await db.ot_schedule_days.insert_one({"_id": day_id, "camp_id": camp_id, "day_date": OTHER_DAY,
                                               "venue": "Old Hospital", "seat_limit": 3, "seats_taken": 1})
        await db.fulfilments.insert_one({"ot_schedule_day_id": day_id, "item_type": "ot", "status": "completed"})
        with pytest.raises(HTTPException) as exc:
            await _update_ot_day(
                str(day_id), OtScheduleBody(camp_id=str(camp_id), day_date="2026-09-05",
                                            seat_limit=3, venue="Old Hospital", venue_sms=None), actor={}
            )
        assert exc.value.status_code == 409

    asyncio.run(run())


def test_camp_day_with_arrival_cannot_move(monkeypatch):
    async def run():
        db = _mock(monkeypatch)
        camp_id, (day_id,) = await _seed_camp(db, days=(OTHER_DAY,))
        await db.patients.insert_one({"camp_id": camp_id, "booked_camp_day_id": day_id,
                                      "camp_day_id": day_id, "arrived_at": TODAY})
        with pytest.raises(HTTPException) as exc:
            await _update_camp_day(
                str(day_id), CampDayBody(camp_id=str(camp_id), day_date="2026-09-05", seat_limit=20), actor={}
            )
        assert exc.value.status_code == 409
        assert (await db.camp_days.find_one({"_id": day_id}))["day_date"] == OTHER_DAY

    asyncio.run(run())


def test_camp_day_edit_rejects_malformed_ids(monkeypatch):
    async def run():
        _mock(monkeypatch)
        with pytest.raises(HTTPException) as exc:
            await _update_camp_day(
                "not-an-id", CampDayBody(camp_id="not-an-id", day_date=OTHER_DAY, seat_limit=20), actor={}
            )
        assert exc.value.status_code == 400

    asyncio.run(run())


def test_camp_day_retry_finishes_notifications_after_interruption(monkeypatch):
    async def run():
        db = _mock(monkeypatch)
        sent = _recorder(monkeypatch)
        camp_id, (day_id,) = await _seed_camp(db, days=(OTHER_DAY,))
        await _register(day_id, manual_entry=True)
        sent.clear()
        actual_send = sms.send_patient_sms

        async def interrupted(*_args, **_kwargs):
            raise RuntimeError("interrupted after day update")

        monkeypatch.setattr(sms, "send_patient_sms", interrupted)
        body = CampDayBody(camp_id=str(camp_id), day_date="2026-09-05", seat_limit=20)
        with pytest.raises(RuntimeError):
            await _update_camp_day(str(day_id), body, actor={})
        assert (await db.camp_days.find_one({"_id": day_id}))["day_date"] == "2026-09-05"

        monkeypatch.setattr(sms, "send_patient_sms", actual_send)
        await _update_camp_day(str(day_id), body, actor={})
        await _update_camp_day(str(day_id), body, actor={})
        assert [item["date"] for item in sent] == ["05-09-2026"]

    asyncio.run(run())


def test_ot_day_retry_finishes_slip_and_notification_after_interruption(monkeypatch):
    async def run():
        db = _mock(monkeypatch)
        sent = _recorder(monkeypatch)
        camp_id, _ = await _seed_camp(db)
        day_id, patient_id, transcription_id = ObjectId(), ObjectId(), ObjectId()
        await db.ot_schedule_days.insert_one({"_id": day_id, "camp_id": camp_id, "day_date": OTHER_DAY,
                                               "venue": "Old Hospital", "seat_limit": 2, "seats_taken": 1})
        await db.patients.insert_one({"_id": patient_id, "camp_id": camp_id, "reg_no": 501,
                                      "phone": "9876500001", "phone_normalized": "9876500001"})
        await db.deferred_slips.insert_one({"patient_id": patient_id, "transcription_id": transcription_id,
                                             "item_type": "ot", "ot_schedule_day_id": day_id,
                                             "collection_date": OTHER_DAY, "collection_venue": "Old Hospital", "active": True})
        await db.fulfilments.insert_one({"transcription_id": transcription_id, "item_type": "ot",
                                          "status": "deferred", "ot_schedule_day_id": day_id,
                                          "collection_date": OTHER_DAY, "collection_venue": "Old Hospital"})
        actual_update = db.deferred_slips.update_many

        async def interrupted(*_args, **_kwargs):
            raise RuntimeError("interrupted before appointment update")

        monkeypatch.setattr(db.deferred_slips, "update_many", interrupted)
        body = OtScheduleBody(camp_id=str(camp_id), day_date="2026-09-05",
                             seat_limit=2, venue="New Hospital", venue_sms=None)
        with pytest.raises(RuntimeError):
            await _update_ot_day(str(day_id), body, actor={})
        assert (await db.deferred_slips.find_one({"patient_id": patient_id}))["collection_date"] == OTHER_DAY

        monkeypatch.setattr(db.deferred_slips, "update_many", actual_update)
        await _update_ot_day(str(day_id), body, actor={})
        await _update_ot_day(str(day_id), body, actor={})
        assert (await db.deferred_slips.find_one({"patient_id": patient_id}))["collection_date"] == "2026-09-05"
        assert (await db.fulfilments.find_one({"transcription_id": transcription_id}))["collection_date"] == "2026-09-05"
        assert [item["date"] for item in sent] == ["05-09-2026"]

    asyncio.run(run())


def test_ot_day_move_updates_current_appointment_and_sends_new_token(monkeypatch):
    async def run():
        db = _mock(monkeypatch)
        sent = _recorder(monkeypatch)
        camp_id, _ = await _seed_camp(db)
        day_id, patient_id, transcription_id = ObjectId(), ObjectId(), ObjectId()
        await db.ot_schedule_days.insert_one({"_id": day_id, "camp_id": camp_id, "day_date": OTHER_DAY,
                                               "venue": "Old Hospital", "venue_sms": None,
                                               "seat_limit": 2, "seats_taken": 1})
        await db.patients.insert_one({"_id": patient_id, "camp_id": camp_id, "reg_no": 501,
                                      "phone": "9876500001", "phone_normalized": "9876500001"})
        await db.deferred_slips.insert_one({"transcription_id": transcription_id, "patient_id": patient_id,
                                             "item_type": "ot", "ot_schedule_day_id": day_id,
                                             "collection_date": OTHER_DAY, "collection_venue": "Old Hospital",
                                             "active": True})
        await db.fulfilments.insert_one({"transcription_id": transcription_id, "item_type": "ot",
                                          "status": "deferred", "ot_schedule_day_id": day_id,
                                          "collection_date": OTHER_DAY, "collection_venue": "Old Hospital"})
        await sms.send_patient_sms(db, await db.patients.find_one({"_id": patient_id}),
                                   "ot_token", OTHER_DAY, "Old Hospital")
        sent.clear()

        result = await _update_ot_day(
            str(day_id), OtScheduleBody(camp_id=str(camp_id), day_date="2026-09-05",
                                        seat_limit=1, venue="New Hospital", venue_sms=None), actor={}
        )
        assert result["ot_day"]["day_date"] == "2026-09-05"
        assert (await db.deferred_slips.find_one({"patient_id": patient_id}))["collection_date"] == "2026-09-05"
        assert (await db.fulfilments.find_one({"transcription_id": transcription_id}))["collection_venue"] == "New Hospital"
        assert sent == [{"type": "ot_token", "mobile": "9876500001", "reg_no": 501,
                         "camp_no": "162", "date": "05-09-2026", "venue": "New Hospital"}]
        await _update_ot_day(
            str(day_id), OtScheduleBody(camp_id=str(camp_id), day_date=OTHER_DAY,
                                        seat_limit=1, venue="New Hospital", venue_sms=None), actor={}
        )
        assert [s["date"] for s in sent] == ["05-09-2026", "03-09-2026"]

    asyncio.run(run())
