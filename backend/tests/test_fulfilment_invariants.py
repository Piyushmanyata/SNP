"""Deferred Fulfilment keeps one current record; a failed write leaves prior state."""
import asyncio

import pytest
from bson import ObjectId
from fastapi import HTTPException

import routes_clinical
from models import CorrectionBody
from routes_clinical import add_correction, record_fulfilment
from seed import CLINICAL, NOW, day, fulfil, patient_doc, run_camp, seen_patient


async def _ot_day(database, camp_id, offset, seat_limit=1, venue="OT"):
    result = await database.ot_schedule_days.insert_one({
        "camp_id": camp_id, "day_date": day(offset), "venue": venue, "seat_limit": seat_limit, "seats_taken": 0,
    })
    return result.inserted_id


async def _specs_day(database, camp_id, offset, venue="Optical", **fields):
    result = await database.specs_collection_days.insert_one({
        "camp_id": camp_id, "day_date": day(offset), "venue": venue, "start_time": "10:00", "end_time": "17:00",
        **fields,
    })
    return result.inserted_id


def _issue(seen, **kw):
    return record_fulfilment(fulfil(seen["trans_id"], seen["rev_id"], **kw), actor=CLINICAL, background_tasks=None)


def test_failed_ot_replace_leaves_prior_fulfilment_and_seat(monkeypatch):
    async def body(database):
        seen = await seen_patient(database)
        day_a = await _ot_day(database, seen["camp_id"], 1, venue="OT A")
        day_b = await _ot_day(database, seen["camp_id"], 2, venue="OT B")
        first = await _issue(seen, item_type="ot", status="deferred", ot_schedule_day_id=str(day_a))
        prior_id = first["fulfilment"]["id"]
        assert (await database.ot_schedule_days.find_one({"_id": day_a}))["seats_taken"] == 1

        async def boom(*_a, **_k):
            raise RuntimeError("injected write failure")

        monkeypatch.setattr(routes_clinical, "persist_fulfilment", boom)
        with pytest.raises(RuntimeError):
            await _issue(seen, item_type="ot", status="deferred", ot_schedule_day_id=str(day_b), operation_id="op-replace")
        still = await database.fulfilments.find_one({"_id": ObjectId(prior_id)})
        assert still["ot_schedule_day_id"] == day_a
        assert (await database.ot_schedule_days.find_one({"_id": day_a}))["seats_taken"] == 1
        assert (await database.ot_schedule_days.find_one({"_id": day_b}))["seats_taken"] == 0
        assert await database.fulfilments.count_documents({"transcription_id": seen["trans_id"], "item_type": "ot"}) == 1
        active_slips = await database.deferred_slips.find({"transcription_id": seen["trans_id"], "active": True}).to_list(10)
        assert len(active_slips) == 1
        assert active_slips[0]["ot_schedule_day_id"] == day_a

    run_camp(monkeypatch, body)


def test_overlapping_ot_assignments_never_consume_two_seats(monkeypatch):
    async def body(database):
        seen = await seen_patient(database)
        day_id = await _ot_day(database, seen["camp_id"], 1, seat_limit=10, venue="Hospital")
        request = fulfil(seen["trans_id"], seen["rev_id"], item_type="ot", status="deferred",
                         ot_schedule_day_id=str(day_id), operation_id="op-overlap")
        original = routes_clinical._process_deferral

        async def delayed(*args, **kwargs):
            await asyncio.sleep(0.02)
            return await original(*args, **kwargs)

        monkeypatch.setattr(routes_clinical, "_process_deferral", delayed)
        results = await asyncio.gather(
            record_fulfilment(request, actor=CLINICAL, background_tasks=None),
            record_fulfilment(request, actor=CLINICAL, background_tasks=None),
            return_exceptions=True,
        )
        assert sum(isinstance(result, dict) for result in results) >= 1
        assert (await database.ot_schedule_days.find_one({"_id": day_id}))["seats_taken"] == 1
        assert await database.fulfilments.count_documents({"transcription_id": seen["trans_id"]}) == 1

    run_camp(monkeypatch, body)


def test_concurrent_same_line_leaves_one_current_specs_record(monkeypatch):
    async def body(database):
        seen = await seen_patient(database)
        day_id = await _specs_day(database, seen["camp_id"], 15)
        request = fulfil(seen["trans_id"], seen["rev_id"], item_type="specs_made", status="deferred",
                         specs_collection_day_id=str(day_id), operation_id="op-specs")
        await record_fulfilment(request, actor=CLINICAL, background_tasks=None)
        await record_fulfilment(request, actor=CLINICAL, background_tasks=None)
        rows = await database.fulfilments.find({"transcription_id": seen["trans_id"], "item_type": "specs_made"}).to_list(20)
        assert len(rows) == 1
        assert rows[0].get("current") is True
        assert await database.deferred_slips.count_documents({"active": True}) == 1

    run_camp(monkeypatch, body)


def test_an_unknown_transcription_is_a_404(monkeypatch):
    async def body(database):
        with pytest.raises(HTTPException) as exc:
            await record_fulfilment(fulfil(ObjectId(), ObjectId(), item_type="medicine", status="fulfilled"),
                                    actor=CLINICAL, background_tasks=None)
        assert exc.value.status_code == 404
        assert "Transcription not found" in exc.value.detail

    run_camp(monkeypatch, body)


def test_redeferring_specs_versions_the_slip_and_never_touches_seats(monkeypatch):
    async def body(database):
        seen = await seen_patient(database)
        first_day = await _specs_day(database, seen["camp_id"], 1, "District Hospital")
        second_day = await _specs_day(database, seen["camp_id"], 2, "Community Health Center", seat_limit=1, seats_taken=0)
        for freeform in ({}, {"collection_date": day(1), "collection_venue": "District Hospital"}):
            with pytest.raises(HTTPException) as exc:
                await _issue(seen, item_type="specs_made", status="deferred", **freeform)
            assert exc.value.status_code == 400

        first = await _issue(seen, item_type="specs_made", status="deferred", specs_collection_day_id=str(first_day))
        assert first["slip"]["version"] == 1
        assert first["slip"]["active"] is True
        assert first["slip"]["collection_date"] == day(1)
        assert first["slip"]["collection_venue"] == "District Hospital"
        assert first["fulfilment"]["status"] == "deferred"
        moved = await _issue(seen, item_type="specs_made", status="deferred", specs_collection_day_id=str(second_day))
        assert moved["slip"]["version"] == 2
        assert moved["slip"]["collection_date"] == day(2)
        again = await _issue(seen, item_type="specs_made", status="deferred", specs_collection_day_id=str(second_day))
        assert again["slip"]["version"] == 3

        slips = await database.deferred_slips.find({"transcription_id": seen["trans_id"]}).to_list(10)
        assert [slip["version"] for slip in slips if slip["active"]] == [3]
        assert sum(slip["cancelled"] for slip in slips) == 2
        assert (await database.specs_collection_days.find_one({"_id": first_day})).get("seats_taken") is None
        assert (await database.specs_collection_days.find_one({"_id": second_day}))["seats_taken"] == 0

    run_camp(monkeypatch, body)


def test_moving_an_ot_booking_releases_the_first_seat(monkeypatch):
    async def body(database):
        seen = await seen_patient(database)
        first_day = await _ot_day(database, seen["camp_id"], 1, seat_limit=5)
        second_day = await _ot_day(database, seen["camp_id"], 2, seat_limit=5)
        await _issue(seen, item_type="ot", status="deferred", ot_schedule_day_id=str(first_day))
        assert (await database.ot_schedule_days.find_one({"_id": first_day}))["seats_taken"] == 1
        await _issue(seen, item_type="ot", status="deferred", ot_schedule_day_id=str(second_day))
        assert (await database.ot_schedule_days.find_one({"_id": first_day}))["seats_taken"] == 0
        assert (await database.ot_schedule_days.find_one({"_id": second_day}))["seats_taken"] == 1

    run_camp(monkeypatch, body)


def test_issuing_a_line_locks_the_transcription(monkeypatch):
    async def body(database):
        seen = await seen_patient(database)
        await database.transcriptions.update_one({"_id": seen["trans_id"]}, {"$set": {"locked": False}})
        await _issue(seen, item_type="medicine", status="fulfilled")
        assert (await database.transcriptions.find_one({"_id": seen["trans_id"]}))["locked"] is True

    run_camp(monkeypatch, body)


@pytest.mark.parametrize("legacy_lists", [{}, {"diagnosis_options": None, "prescribed_medicines": None}])
def test_a_correction_changes_only_allowed_fields_and_keeps_an_audit_row(monkeypatch, legacy_lists):
    async def body(database):
        patient_id, trans_id, rev_id = ObjectId(), ObjectId(), ObjectId()
        await database.patients.insert_one(patient_doc(
            _id=patient_id, camp_id=ObjectId(), camp_day_id=ObjectId(), queue_status="seen", full_name="Corr Patient",
            arrived_at=NOW, printed_at=NOW, seen_at=NOW,
            committed_revision_id=rev_id, clinical_generation=1, issue_auth_op=None,
        ))
        await database.prescription_revisions.insert_one({
            "_id": rev_id, "patient_id": patient_id, "operation_id": str(ObjectId()),
            "none_prescribed": True, "prescribed_lines": [], "bp": "120/80", "blood_sugar": "110",
            **legacy_lists,
        })
        await database.transcriptions.insert_one({
            "_id": trans_id, "patient_id": patient_id, "locked": True, "blood_sugar": "110", "bp": "120/80",
        })
        result = await add_correction(CorrectionBody(
            transcription_id=str(trans_id),
            reason="Correcting BP reading per doctor re-check",
            changes={"bp": "135/85", "unauthorized_field": "hacked"},
            expected_generation=1,
            operation_id="op-corr-stress",
            full_transcription_confirmed=True,
            none_prescribed=True,
        ), actor=CLINICAL)
        assert "correction_id" in result
        transcription = await database.transcriptions.find_one({"_id": trans_id})
        assert transcription["bp"] == "135/85"
        assert transcription["diagnosis_options"] == []
        assert transcription["prescribed_medicines"] == []
        assert "unauthorized_field" not in transcription
        correction = await database.corrections.find_one({"transcription_id": trans_id})
        assert correction["reason"] == "Correcting BP reading per doctor re-check"
        assert correction["changes"]["bp"] == "135/85"

    run_camp(monkeypatch, body)


def test_fifty_concurrent_specs_deferrals_all_succeed_without_seats(monkeypatch):
    async def body(database):
        camp_id = ObjectId()
        day_id = await _specs_day(database, camp_id, 1, "Vision Center", seat_limit=3, seats_taken=0)
        patients = [await seen_patient(database, camp_id) for _ in range(50)]
        results = await asyncio.gather(*[
            _issue(seen, item_type="specs_made", status="deferred", specs_collection_day_id=str(day_id))
            for seen in patients
        ], return_exceptions=True)
        assert [r for r in results if not isinstance(r, dict)] == []
        assert (await database.specs_collection_days.find_one({"_id": day_id}))["seats_taken"] == 0

    run_camp(monkeypatch, body)
