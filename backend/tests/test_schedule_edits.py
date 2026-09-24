import pytest
from bson import ObjectId
from fastapi import BackgroundTasks, HTTPException
from pymongo.asynchronous.collection import AsyncCollection

import routes_camps
import routes_clinical
import sms
from models import CampDayBody, OtScheduleBody
from seed import NOW, OTHER_DAY, day, patient_doc, recorder, register, run_camp, seed_camp

MOVED_DAY = day(4)
MOVED_SHOWN = "09-10-2026"
OTHER_SHOWN = "07-10-2026"


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


async def _seed_ot_appointment(database, camp_id, seat_limit):
    day_id, patient_id, transcription_id = ObjectId(), ObjectId(), ObjectId()
    await database.ot_schedule_days.insert_one({
        "_id": day_id, "camp_id": camp_id, "day_date": OTHER_DAY, "venue": "Old Hospital",
        "venue_sms": None, "seat_limit": seat_limit, "seats_taken": 1,
    })
    await database.patients.insert_one(patient_doc(
        _id=patient_id, camp_id=camp_id, reg_no=501, phone="9876500001", phone_normalized="9876500001",
    ))
    await database.deferred_slips.insert_one({
        "patient_id": patient_id, "transcription_id": transcription_id, "item_type": "ot",
        "ot_schedule_day_id": day_id, "collection_date": OTHER_DAY, "collection_venue": "Old Hospital",
        "active": True,
    })
    await database.fulfilments.insert_one({
        "transcription_id": transcription_id, "item_type": "ot", "status": "deferred",
        "ot_schedule_day_id": day_id, "collection_date": OTHER_DAY, "collection_venue": "Old Hospital",
    })
    return day_id, patient_id, transcription_id


def test_camp_day_list_reports_bookings_above_reduced_seats(monkeypatch):
    async def body(database):
        camp_id, (day_id,) = await seed_camp(database, days=(OTHER_DAY,))
        await database.camp_days.update_one({"_id": day_id}, {"$set": {"booked": 3, "seat_limit": 2}})

        listed = await routes_camps.list_days(str(camp_id), actor={})

        assert listed["days"][0]["booked"] == 3
        assert listed["days"][0]["over_capacity"] is True

    run_camp(monkeypatch, body)


def test_camp_day_move_keeps_bookings_and_sends_new_date(monkeypatch):
    sent = recorder(monkeypatch)

    async def body(database):
        camp_id, (day_id,) = await seed_camp(database, days=(OTHER_DAY,))
        await database.camps.update_one({"_id": camp_id}, {"$set": {"venue_sms": "Short Camp Venue", "camp_date": OTHER_DAY}})
        first = await register(day_id, manual_entry=True)
        second = await register(day_id, full_name="Ram Prasad", manual_entry=True)
        sent.clear()

        tasks = BackgroundTasks()
        result = await routes_camps.update_camp_day(
            str(day_id), CampDayBody(camp_id=str(camp_id), day_date=MOVED_DAY, seat_limit=1),
            actor={}, background_tasks=tasks,
        )
        assert sent == []
        await tasks()
        assert result["day"]["day_date"] == MOVED_DAY
        assert result["day"]["seat_limit"] == 1
        assert await database.patients.count_documents({"booked_camp_day_id": day_id}) == 2
        assert (await database.camps.find_one({"_id": camp_id}))["camp_date"] == MOVED_DAY
        with pytest.raises(HTTPException) as full:
            await register(day_id, full_name="Third Patient", manual_entry=True)
        assert full.value.status_code == 409
        assert len(sent) == 2
        assert all(s["type"] == "registration" and s["date"] == MOVED_SHOWN for s in sent)
        assert sorted(s["reg_no"] for s in sent) == sorted([first["reg_no"], second["reg_no"]])
        await _update_camp_day(
            str(day_id), CampDayBody(camp_id=str(camp_id), day_date=OTHER_DAY, seat_limit=2), actor={}
        )
        assert len(sent) == 4
        assert [s["date"] for s in sent[2:]] == [OTHER_SHOWN, OTHER_SHOWN]

    run_camp(monkeypatch, body)


def test_ot_day_seats_cannot_drop_below_assigned(monkeypatch):
    async def body(database):
        camp_id, _ = await seed_camp(database)
        day_id = ObjectId()
        await database.ot_schedule_days.insert_one({"_id": day_id, "camp_id": camp_id, "day_date": OTHER_DAY,
                                                    "venue": "Old Hospital", "venue_sms": None,
                                                    "seat_limit": 3, "seats_taken": 2})
        with pytest.raises(HTTPException) as exc:
            await _update_ot_day(
                str(day_id), OtScheduleBody(camp_id=str(camp_id), day_date=MOVED_DAY,
                                            seat_limit=1, venue="New Hospital", venue_sms=None), actor={}
            )
        assert exc.value.status_code == 409
        assert (await database.ot_schedule_days.find_one({"_id": day_id}))["day_date"] == OTHER_DAY

    run_camp(monkeypatch, body)


def test_camp_day_with_arrival_cannot_move(monkeypatch):
    async def body(database):
        camp_id, (day_id,) = await seed_camp(database, days=(OTHER_DAY,))
        await database.patients.insert_one(patient_doc(
            camp_id=camp_id, booked_camp_day_id=day_id, camp_day_id=day_id, arrived_at=NOW,
        ))
        with pytest.raises(HTTPException) as exc:
            await _update_camp_day(
                str(day_id), CampDayBody(camp_id=str(camp_id), day_date=MOVED_DAY, seat_limit=20), actor={}
            )
        assert exc.value.status_code == 409
        assert (await database.camp_days.find_one({"_id": day_id}))["day_date"] == OTHER_DAY

    run_camp(monkeypatch, body)


def test_camp_day_edit_rejects_malformed_ids(monkeypatch):
    async def body(database):
        with pytest.raises(HTTPException) as exc:
            await _update_camp_day(
                "not-an-id", CampDayBody(camp_id="not-an-id", day_date=OTHER_DAY, seat_limit=20), actor={}
            )
        assert exc.value.status_code == 400

    run_camp(monkeypatch, body)


def test_camp_day_retry_finishes_notifications_after_interruption(monkeypatch):
    sent = recorder(monkeypatch)

    async def interrupted(*_args, **_kwargs):
        raise RuntimeError("interrupted after day update")

    async def body(database):
        camp_id, (day_id,) = await seed_camp(database, days=(OTHER_DAY,))
        await register(day_id, manual_entry=True)
        sent.clear()
        request = CampDayBody(camp_id=str(camp_id), day_date=MOVED_DAY, seat_limit=20)
        with monkeypatch.context() as broken:
            broken.setattr(sms, "send_patient_sms", interrupted)
            with pytest.raises(RuntimeError):
                await _update_camp_day(str(day_id), request, actor={})
        assert (await database.camp_days.find_one({"_id": day_id}))["day_date"] == MOVED_DAY

        await _update_camp_day(str(day_id), request, actor={})
        await _update_camp_day(str(day_id), request, actor={})
        assert [item["date"] for item in sent] == [MOVED_SHOWN]

    run_camp(monkeypatch, body)


def test_ot_day_retry_finishes_slip_and_notification_after_interruption(monkeypatch):
    sent = recorder(monkeypatch)
    update_many = AsyncCollection.update_many

    async def interrupted(self, *args, **kwargs):
        if self.name == "deferred_slips":
            raise RuntimeError("interrupted before appointment update")
        return await update_many(self, *args, **kwargs)

    async def body(database):
        camp_id, _ = await seed_camp(database)
        day_id, patient_id, transcription_id = await _seed_ot_appointment(database, camp_id, seat_limit=2)
        request = OtScheduleBody(camp_id=str(camp_id), day_date=MOVED_DAY,
                                 seat_limit=2, venue="New Hospital", venue_sms=None)
        with monkeypatch.context() as broken:
            broken.setattr(AsyncCollection, "update_many", interrupted)
            with pytest.raises(RuntimeError):
                await _update_ot_day(str(day_id), request, actor={})
        assert (await database.deferred_slips.find_one({"patient_id": patient_id}))["collection_date"] == OTHER_DAY

        await _update_ot_day(str(day_id), request, actor={})
        await _update_ot_day(str(day_id), request, actor={})
        assert (await database.deferred_slips.find_one({"patient_id": patient_id}))["collection_date"] == MOVED_DAY
        assert (await database.fulfilments.find_one({"transcription_id": transcription_id}))["collection_date"] == MOVED_DAY
        assert [item["date"] for item in sent] == [MOVED_SHOWN]

    run_camp(monkeypatch, body)


def test_ot_day_move_updates_current_appointment_and_sends_new_token(monkeypatch):
    sent = recorder(monkeypatch)

    async def body(database):
        camp_id, _ = await seed_camp(database)
        day_id, patient_id, transcription_id = await _seed_ot_appointment(database, camp_id, seat_limit=2)
        await sms.send_patient_sms(database, await database.patients.find_one({"_id": patient_id}),
                                   "ot_token", OTHER_DAY, "Old Hospital")
        sent.clear()

        result = await _update_ot_day(
            str(day_id), OtScheduleBody(camp_id=str(camp_id), day_date=MOVED_DAY,
                                        seat_limit=1, venue="New Hospital", venue_sms=None), actor={}
        )
        assert result["ot_day"]["day_date"] == MOVED_DAY
        assert (await database.deferred_slips.find_one({"patient_id": patient_id}))["collection_date"] == MOVED_DAY
        assert (await database.fulfilments.find_one({"transcription_id": transcription_id}))["collection_venue"] == "New Hospital"
        assert sent == [{"type": "ot_token", "mobile": "9876500001", "reg_no": 501,
                         "camp_no": "162", "date": MOVED_SHOWN, "venue": "New Hospital"}]
        await _update_ot_day(
            str(day_id), OtScheduleBody(camp_id=str(camp_id), day_date=OTHER_DAY,
                                        seat_limit=1, venue="New Hospital", venue_sms=None), actor={}
        )
        assert [s["date"] for s in sent] == [MOVED_SHOWN, OTHER_SHOWN]

    run_camp(monkeypatch, body)
