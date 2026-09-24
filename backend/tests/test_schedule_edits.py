import pytest
from bson import ObjectId
from fastapi import BackgroundTasks, HTTPException

import msg91
import routes_camps
import routes_clinical
from conftest import run_db
from models import CampDayBody, OtScheduleBody, SpecsScheduleBody
from seed import ADMIN, NOW, OTHER_DAY, day, patient_doc, recorder, register, run_camp, seed_camp
from test_camp_operations_matrix import intercept

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


async def _update_specs_day(*args, **kwargs):
    tasks = BackgroundTasks()
    result = await routes_clinical.update_specs_day(*args, **kwargs, background_tasks=tasks)
    await tasks()
    return result


async def _seed_appointment(database, camp_id, item_type, day_field, day_id, venue, end_date=None):
    patient_id, transcription_id, slip_id = ObjectId(), ObjectId(), ObjectId()
    await database.patients.insert_one(patient_doc(
        _id=patient_id, camp_id=camp_id, reg_no=501, phone="9876500001", phone_normalized="9876500001",
    ))
    await database.deferred_slips.insert_one({
        "_id": slip_id, "patient_id": patient_id, "transcription_id": transcription_id, "item_type": item_type,
        "version": 1, "active": True, "cancelled": False, day_field: day_id, "collection_date": OTHER_DAY,
        "collection_end_date": end_date, "collection_venue": venue, "instructions": "Bring this Token",
    })
    await database.fulfilments.insert_one({
        "transcription_id": transcription_id, "item_type": item_type, "status": "deferred", "slip_id": slip_id,
        day_field: day_id, "collection_date": OTHER_DAY, "collection_venue": venue,
    })
    return patient_id, transcription_id, slip_id


async def _seed_ot_appointment(database, camp_id, seat_limit):
    day_id = ObjectId()
    await database.ot_schedule_days.insert_one({
        "_id": day_id, "camp_id": camp_id, "day_date": OTHER_DAY, "venue": "Old Hospital",
        "venue_sms": None, "seat_limit": seat_limit, "seats_taken": 1,
    })
    patient_id, transcription_id, _slip = await _seed_appointment(
        database, camp_id, "ot", "ot_schedule_day_id", day_id, "Old Hospital",
    )
    return day_id, patient_id, transcription_id


async def _seed_specs_appointment(database, camp_id):
    day_id = ObjectId()
    await database.specs_collection_days.insert_one({
        "_id": day_id, "camp_id": camp_id, "day_date": OTHER_DAY, "end_date": day(9),
        "venue": "Old Optical", "venue_sms": None,
    })
    patient_id, transcription_id, _slip = await _seed_appointment(
        database, camp_id, "specs_made", "specs_collection_day_id", day_id, "Old Optical", end_date=day(9),
    )
    return day_id, patient_id, transcription_id


def _ot(camp_id, **change):
    return OtScheduleBody(**{"camp_id": str(camp_id), "day_date": OTHER_DAY, "seat_limit": 2,
                             "venue": "Old Hospital", "venue_sms": None, **change})


async def _raise(real, *args, **kwargs):
    raise RuntimeError("interrupted")


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


def test_an_error_during_a_camp_day_move_changes_nothing_and_the_retry_notifies_once(monkeypatch):
    sent = recorder(monkeypatch)

    async def body(database):
        camp_id, (day_id,) = await seed_camp(database, days=(OTHER_DAY,))
        await register(day_id, manual_entry=True)
        sent.clear()
        request = CampDayBody(camp_id=str(camp_id), day_date=MOVED_DAY, seat_limit=20)
        restore = intercept(monkeypatch, "reminder_ledger", "insert_many", _raise)
        with pytest.raises(RuntimeError):
            await _update_camp_day(str(day_id), request, actor={})
        restore()
        assert (await database.camp_days.find_one({"_id": day_id}))["day_date"] == OTHER_DAY
        assert await database.reminder_ledger.count_documents({}) == 1

        await _update_camp_day(str(day_id), request, actor={})
        await _update_camp_day(str(day_id), request, actor={})
        assert [item["date"] for item in sent] == [MOVED_SHOWN]

    run_camp(monkeypatch, body)


def test_a_camp_day_move_queues_its_notices_before_sending(monkeypatch):
    recorder(monkeypatch)

    async def body(database):
        camp_id, (day_id,) = await seed_camp(database, days=(OTHER_DAY,))
        await register(day_id, manual_entry=True)
        await register(day_id, full_name="Ram Prasad", manual_entry=True)
        await routes_camps.update_camp_day(
            str(day_id), CampDayBody(camp_id=str(camp_id), day_date=MOVED_DAY, seat_limit=20),
            actor={}, background_tasks=BackgroundTasks(),
        )
        revision = (await database.camp_days.find_one({"_id": day_id}))["edit_revision"]
        queued = await database.reminder_ledger.find({"status": "queued"}).to_list(None)
        assert len(queued) == 2
        assert {row["event_key"] for row in queued} == {f"edit:{revision}"}

    run_camp(monkeypatch, body)


def test_a_booking_after_a_move_gets_one_notice_and_a_seat_change_sends_nothing(monkeypatch):
    sent = recorder(monkeypatch)

    async def body(database):
        camp_id, (day_id,) = await seed_camp(database, days=(OTHER_DAY,))
        await _update_camp_day(str(day_id), CampDayBody(camp_id=str(camp_id), day_date=MOVED_DAY, seat_limit=5), actor={})
        late = await register(day_id, manual_entry=True)
        await _update_camp_day(str(day_id), CampDayBody(camp_id=str(camp_id), day_date=MOVED_DAY, seat_limit=6), actor={})
        assert [s["reg_no"] for s in sent] == [late["reg_no"]]
        revision = (await database.camp_days.find_one({"_id": day_id}))["edit_revision"]
        row = await database.reminder_ledger.find_one({"message_type": "registration"})
        assert row["event_key"] == f"edit:{revision}"

    run_camp(monkeypatch, body)


def test_adding_a_day_on_a_date_that_already_has_one_is_refused(monkeypatch):
    async def body(database):
        camp_id, _ = await seed_camp(database)
        await routes_clinical.create_ot_day(_ot(camp_id), actor={})
        with pytest.raises(HTTPException) as ot:
            await routes_clinical.create_ot_day(_ot(camp_id, seat_limit=5, venue="Other"), actor={})
        specs = SpecsScheduleBody(camp_id=str(camp_id), day_date=OTHER_DAY, end_date=day(9), venue="Optical")
        await routes_clinical.create_specs_day(specs, actor={})
        with pytest.raises(HTTPException) as again:
            await routes_clinical.create_specs_day(specs.model_copy(update={"venue": "Other"}), actor={})
        for exc in (ot, again):
            assert exc.value.status_code == 409 and exc.value.detail["code"] == "DAY_EXISTS"
        assert (await database.ot_schedule_days.find_one({}))["venue"] == "Old Hospital"
        assert (await database.specs_collection_days.find_one({}))["venue"] == "Optical"

    run_camp(monkeypatch, body)


def test_specs_hours_are_fixed_and_not_stored(monkeypatch):
    async def body(database):
        camp_id, _ = await seed_camp(database)
        out = await routes_clinical.create_specs_day(
            SpecsScheduleBody(camp_id=str(camp_id), day_date=OTHER_DAY, venue="Optical"), actor={},
        )
        stored = await database.specs_collection_days.find_one({})
        assert "start_time" not in stored and "end_time" not in stored
        assert "window_required" not in out["specs_day"] and "start_time" not in out["specs_day"]

    run_camp(monkeypatch, body)


def test_a_venue_change_supersedes_the_ot_token_and_queues_one_notice(monkeypatch):
    sent = recorder(monkeypatch)

    async def body(database):
        camp_id, _ = await seed_camp(database)
        day_id, patient_id, transcription_id = await _seed_ot_appointment(database, camp_id, seat_limit=2)
        old = await database.deferred_slips.find_one({"patient_id": patient_id})
        await _update_ot_day(str(day_id), _ot(camp_id, venue="New Hospital"), actor={})
        revision = (await database.ot_schedule_days.find_one({"_id": day_id}))["edit_revision"]
        new = await database.deferred_slips.find_one({"patient_id": patient_id, "active": True})
        superseded = await database.deferred_slips.find_one({"_id": old["_id"]})
        assert superseded["active"] is False and superseded["superseded_by"] == new["_id"]
        assert (new["collection_venue"], new["version"], new["edit_revision"]) == ("New Hospital", 2, revision)
        assert new["replaces"] == old["_id"] and new["instructions"] == old["instructions"]
        fulfilment = await database.fulfilments.find_one({"transcription_id": transcription_id})
        assert fulfilment["slip_id"] == new["_id"] and fulfilment["collection_venue"] == "New Hospital"
        assert [(s["type"], s["date"], s["venue"]) for s in sent] == [("ot_change", OTHER_SHOWN, "New Hospital")]
        row = await database.reminder_ledger.find_one({"message_type": "ot_change"})
        assert row["event_key"] == f"edit:{revision}"

        await _update_ot_day(str(day_id), _ot(camp_id, venue="New Hospital", seat_limit=3), actor={})
        assert await database.deferred_slips.count_documents({"patient_id": patient_id}) == 2
        assert len(sent) == 1

    run_camp(monkeypatch, body)


def test_each_ot_date_move_supersedes_the_token_once(monkeypatch):
    sent = recorder(monkeypatch)

    async def body(database):
        camp_id, _ = await seed_camp(database)
        day_id, patient_id, transcription_id = await _seed_ot_appointment(database, camp_id, seat_limit=2)
        await _update_ot_day(str(day_id), _ot(camp_id, day_date=MOVED_DAY, seat_limit=1), actor={})
        await _update_ot_day(str(day_id), _ot(camp_id, day_date=OTHER_DAY, seat_limit=1), actor={})
        slips = await database.deferred_slips.find({"patient_id": patient_id}).sort("version", 1).to_list(None)
        assert [(s["version"], s["active"], s["collection_date"]) for s in slips] == [
            (1, False, OTHER_DAY), (2, False, MOVED_DAY), (3, True, OTHER_DAY),
        ]
        assert [(s["type"], s["date"]) for s in sent] == [("ot_change", MOVED_SHOWN), ("ot_change", OTHER_SHOWN)]
        assert (await database.ot_schedule_days.find_one({"_id": day_id}))["seats_taken"] == 1

    run_camp(monkeypatch, body)


def test_a_specs_day_move_supersedes_the_token_and_queues_one_notice(monkeypatch):
    sent = recorder(monkeypatch)

    async def body(database):
        camp_id, _ = await seed_camp(database)
        day_id, patient_id, transcription_id = await _seed_specs_appointment(database, camp_id)
        await _update_specs_day(str(day_id), SpecsScheduleBody(
            camp_id=str(camp_id), day_date=MOVED_DAY, end_date=day(10), venue="Old Optical",
        ), actor={})
        new = await database.deferred_slips.find_one({"patient_id": patient_id, "active": True})
        assert (new["collection_date"], new["collection_end_date"], new["version"]) == (MOVED_DAY, day(10), 2)
        assert "collection_start_time" not in new
        fulfilment = await database.fulfilments.find_one({"transcription_id": transcription_id})
        assert fulfilment["slip_id"] == new["_id"] and fulfilment["collection_date"] == MOVED_DAY
        assert [(s["type"], s["date"], s["end_date"]) for s in sent] == [("specs_change", MOVED_SHOWN, "15-10-2026")]

    run_camp(monkeypatch, body)


def test_an_error_during_a_schedule_edit_changes_nothing(monkeypatch):
    recorder(monkeypatch)

    async def body(database):
        camp_id, _ = await seed_camp(database)
        day_id, patient_id, _t = await _seed_ot_appointment(database, camp_id, seat_limit=2)
        restore = intercept(monkeypatch, "reminder_ledger", "insert_many", _raise)
        with pytest.raises(RuntimeError):
            await _update_ot_day(str(day_id), _ot(camp_id, day_date=MOVED_DAY), actor={})
        restore()
        assert (await database.ot_schedule_days.find_one({"_id": day_id}))["day_date"] == OTHER_DAY
        assert await database.deferred_slips.count_documents({"patient_id": patient_id, "active": True}) == 1
        assert await database.deferred_slips.count_documents({"patient_id": patient_id}) == 1
        assert (await database.fulfilments.find_one({}))["collection_date"] == OTHER_DAY

    run_camp(monkeypatch, body)


@pytest.mark.parametrize("provider", ["unconfigured", "failed"])
def test_a_notice_that_cannot_be_sent_puts_the_patient_on_the_contact_list(monkeypatch, provider):
    if provider == "failed":
        recorder(monkeypatch)

        def refuse(*_args):
            raise msg91.Unsent("provider down")

        monkeypatch.setattr(msg91, "send_dlt_sms", refuse)

    async def body(database):
        camp_id, _ = await seed_camp(database)
        day_id, _patient, _t = await _seed_ot_appointment(database, camp_id, seat_limit=2)
        await _update_ot_day(str(day_id), _ot(camp_id, venue="New Hospital"), actor={})
        listed = (await routes_clinical.list_schedule_notices(actor=ADMIN))["notices"]
        assert [(n["reg_no"], n["phone"], n["collection_venue"], n["item_type"]) for n in listed] == [
            (501, "9876500001", "New Hospital", "ot"),
        ]
        await routes_clinical.mark_notice_contacted(listed[0]["slip_id"], actor=ADMIN)
        assert (await routes_clinical.list_schedule_notices(actor=ADMIN))["notices"] == []

    run_camp(monkeypatch, body)


def test_a_sent_notice_needs_no_phone_call(monkeypatch):
    recorder(monkeypatch)

    async def body(database):
        camp_id, _ = await seed_camp(database)
        day_id, _patient, _t = await _seed_ot_appointment(database, camp_id, seat_limit=2)
        await _update_ot_day(str(day_id), _ot(camp_id, venue="New Hospital"), actor={})
        assert (await routes_clinical.list_schedule_notices(actor=ADMIN))["notices"] == []

    run_camp(monkeypatch, body)


def test_schedule_lookups_are_indexed():
    async def body(database):
        return await database.deferred_slips.index_information(), await database.fulfilments.index_information()

    slips, fulfilments = run_db(body)
    keys = [tuple(index["key"]) for index in slips.values()]
    assert (("ot_schedule_day_id", 1), ("active", 1)) in keys
    assert (("specs_collection_day_id", 1), ("active", 1)) in keys
    assert (("ot_schedule_day_id", 1), ("status", 1)) in [tuple(index["key"]) for index in fulfilments.values()]
