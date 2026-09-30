"""The queue stages through their interface: one definition of who is waiting for what."""

from datetime import timedelta

from bson import ObjectId

import arrival
import queue_stage
from db import aggregate_list
from helpers import ist_day_bounds
from seed import NOW, TODAY, patient_doc, run_camp, seed_camp

ACTOR_ID = str(ObjectId())
STAGE_FILTERS = {
    "awaiting_print": queue_stage.awaiting_print,
    "pending": queue_stage.pending,
    "doctor_seen": queue_stage.doctor_seen,
}
EMPTY_STAGES = {
    "awaiting_print": 0, "awaiting_seen": 0, "transcription_backlog": 0,
    "earlier_days": {"awaiting_print": 0, "awaiting_seen": 0, "transcription_backlog": 0},
}


def _patient(camp_id, name, **fields):
    return patient_doc(**{
        "camp_id": camp_id, "full_name": name, "queue_status": "arrived", "arrived_at": NOW, **fields,
    })


async def _names(db, query):
    return sorted([p["full_name"] async for p in db.patients.find(query)])


async def _ids(db, query):
    return {p["_id"] async for p in db.patients.find(query)}


async def _stages_of(db, camp_id, patient_id):
    return [
        name for name, stage in STAGE_FILTERS.items()
        if await db.patients.count_documents({"_id": patient_id, **stage(camp_id)})
    ]


async def _seed_stages(db):
    camp_id, _ = await seed_camp(db)
    other_camp = ObjectId()
    earlier = NOW - timedelta(days=1)
    await db.patients.insert_many([
        _patient(camp_id, "Registered", queue_status="registered", arrived_at=None),
        _patient(camp_id, "Unprinted Null", printed_at=None),
        _patient(camp_id, "Unprinted Missing"),
        _patient(camp_id, "Printed Today", printed_at=NOW),
        _patient(camp_id, "Printed Earlier", arrived_at=earlier, printed_at=earlier),
        _patient(camp_id, "Seen", queue_status="seen", printed_at=NOW, seen_at=NOW),
        _patient(other_camp, "Other Camp Unprinted"),
        _patient(other_camp, "Other Camp Printed", printed_at=NOW),
        _patient(other_camp, "Other Camp Seen", queue_status="seen", printed_at=NOW, seen_at=NOW),
    ])
    return camp_id


def test_stage_filters_select_the_camps_patients_by_stage(monkeypatch):
    async def run(db):
        camp_id = await _seed_stages(db)
        assert await _names(db, queue_stage.awaiting_print(camp_id)) == ["Unprinted Missing", "Unprinted Null"]
        assert await _names(db, queue_stage.pending(camp_id)) == ["Printed Earlier", "Printed Today"]
        assert await _names(db, queue_stage.doctor_seen(camp_id)) == ["Seen"]

    run_camp(monkeypatch, run)


def test_a_registered_patients_stage_is_the_stage_filter_that_selects_them(monkeypatch):
    async def run(db):
        camp_id = await _seed_stages(db)
        named = {"awaiting_print": "awaiting_print", "pending": "pending", "doctor_seen": "seen"}
        seen = []
        async for patient in db.patients.find(queue_stage.registered(camp_id)):
            selected = [named[stage] for stage in await _stages_of(db, camp_id, patient["_id"])] or ["booked"]
            assert [queue_stage.stage_of(patient)] == selected, patient["full_name"]
            seen.append(patient["full_name"])
        assert len(seen) == 6

    run_camp(monkeypatch, run)


def test_awaiting_print_and_pending_partition_the_arrived_status(monkeypatch):
    async def run(db):
        camp_id = await _seed_stages(db)
        awaiting_print = await _ids(db, queue_stage.awaiting_print(camp_id))
        pending = await _ids(db, queue_stage.pending(camp_id))
        arrived = await _ids(db, {"camp_id": camp_id, "queue_status": "arrived"})
        assert awaiting_print and pending
        assert awaiting_print.isdisjoint(pending)
        assert awaiting_print | pending == arrived

    run_camp(monkeypatch, run)


def test_board_stages_equal_the_filters_counts_and_split_by_earlier_days(monkeypatch):
    async def run(db):
        camp_id, _ = await seed_camp(db)
        day_start, _ = ist_day_bounds(TODAY)
        earlier = day_start - timedelta(hours=3)
        await db.patients.insert_many([
            _patient(camp_id, "Unprinted Null Today", printed_at=None),
            _patient(camp_id, "Unprinted Missing Today"),
            _patient(camp_id, "Unprinted Earlier", arrived_at=earlier, printed_at=None),
            _patient(camp_id, "Printed Today 1", printed_at=NOW),
            _patient(camp_id, "Printed Today 2", printed_at=NOW),
            _patient(camp_id, "Printed Today 3", printed_at=NOW),
            _patient(camp_id, "Printed Earlier 1", arrived_at=earlier, printed_at=earlier),
            _patient(camp_id, "Printed Earlier 2", arrived_at=earlier, printed_at=earlier),
            _patient(camp_id, "Seen Earlier", queue_status="seen", arrived_at=earlier, printed_at=earlier, seen_at=NOW),
            _patient(ObjectId(), "Other Camp", arrived_at=earlier),
        ])
        rows = await aggregate_list(db.patients, queue_stage.board_pipeline(camp_id, day_start))
        stages = queue_stage.board_stages(rows)

        def count(query, **extra):
            return db.patients.count_documents({**query, **extra})

        before_today = {"arrived_at": {"$lt": day_start}}
        assert stages["awaiting_print"] == await count(queue_stage.awaiting_print(camp_id)) == 3
        assert stages["awaiting_seen"] == stages["transcription_backlog"] == await count(queue_stage.pending(camp_id)) == 5
        assert stages["earlier_days"] == {
            "awaiting_print": await count(queue_stage.awaiting_print(camp_id), **before_today),
            "awaiting_seen": await count(queue_stage.pending(camp_id), **before_today),
            "transcription_backlog": await count(queue_stage.pending(camp_id), **before_today),
        } == {"awaiting_print": 1, "awaiting_seen": 2, "transcription_backlog": 2}

    run_camp(monkeypatch, run)


def test_board_stages_of_nothing_is_the_all_zero_shape():
    assert queue_stage.board_stages([]) == EMPTY_STAGES
    assert queue_stage.board_stages([{"_id": None, "printed": 4}]) == {
        **EMPTY_STAGES, "awaiting_seen": 4, "transcription_backlog": 4,
    }


def test_a_printed_patient_leaves_pending_when_seen_and_returns_on_undo(monkeypatch):
    async def run(db):
        camp_id, _ = await seed_camp(db)
        patient = _patient(camp_id, "Sunita Devi", printed_at=NOW)
        await db.patients.insert_one(patient)
        assert await _stages_of(db, camp_id, patient["_id"]) == ["pending"]

        await db.patients.find_one_and_update(
            {"_id": patient["_id"]}, {"$set": queue_stage.seen_fields(ACTOR_ID, NOW)},
        )
        seen = await db.patients.find_one({"_id": patient["_id"]})
        assert await _stages_of(db, camp_id, patient["_id"]) == ["doctor_seen"]
        assert (seen["seen_at"], seen["seen_by"]) == (NOW.replace(tzinfo=None), ACTOR_ID)

        await db.patients.find_one_and_update({"_id": patient["_id"]}, {"$set": queue_stage.unseen_fields()})
        undone = await db.patients.find_one({"_id": patient["_id"]})
        assert await _stages_of(db, camp_id, patient["_id"]) == ["pending"]
        assert (undone["seen_at"], undone["seen_by"]) == (None, None)

    run_camp(monkeypatch, run)


def test_unseen_fields_undo_exactly_what_seen_fields_set():
    seen, unseen = queue_stage.seen_fields(ACTOR_ID, NOW), queue_stage.unseen_fields()
    assert set(unseen) == set(seen) == {"queue_status", "seen_at", "seen_by"}
    assert {key: value for key, value in unseen.items() if value is not None} == {"queue_status": "arrived"}


def test_a_registration_made_or_stamped_by_arrival_awaits_print(monkeypatch):
    async def run(db):
        camp_id, (day_id,) = await seed_camp(db)
        created = patient_doc(camp_id=camp_id, printed_at=None, **arrival.fields_at_creation("desk", NOW))
        booked = patient_doc(camp_id=camp_id, printed_at=None, queue_status="registered",
                             **arrival.fields_at_creation(None, NOW))
        stamped = patient_doc(camp_id=camp_id, camp_day_id=day_id, queue_status="registered")
        await db.patients.insert_many([created, booked, stamped])
        await arrival.stamp(db, stamped, ACTOR_ID, {"printing_open": True})

        assert await _stages_of(db, camp_id, created["_id"]) == ["awaiting_print"]
        assert await _stages_of(db, camp_id, booked["_id"]) == []
        assert await _stages_of(db, camp_id, stamped["_id"]) == ["awaiting_print"]

    run_camp(monkeypatch, run)


def test_pending_is_ordered_longest_since_print_first_with_the_stage_sort(monkeypatch):
    async def run(db):
        camp_id, _ = await seed_camp(db)
        await db.patients.insert_many([
            _patient(camp_id, "Middle", printed_at=NOW - timedelta(minutes=20)),
            _patient(camp_id, "Newest", printed_at=NOW),
            _patient(camp_id, "Oldest", printed_at=NOW - timedelta(minutes=40)),
        ])
        rows = await db.patients.find(queue_stage.pending(camp_id)).sort(queue_stage.PENDING_SORT).to_list(None)
        assert [p["full_name"] for p in rows] == ["Oldest", "Middle", "Newest"]

    run_camp(monkeypatch, run)
