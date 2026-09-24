import asyncio

import pytest
from bson import ObjectId
from fastapi import HTTPException

from models import CorrectionBody, UndoCompletionBody
from routes_clinical import add_correction, complete_prescription, record_fulfilment, undo_completion
from seed import FIXED_POWER, MEDICINE, day, recorder, run_camp
import routes_clinical
from test_camp_operations_matrix import CLINICAL, RX, _complete_body, _issue_body, _printed_patient, intercept
from test_hospital_outcomes import _complete, _lines, _ot_day, _record


def _failing(name):
    async def hook(real, *args, **kwargs):
        raise RuntimeError(f"injected {name} failure")
    return hook


async def _specs_day(db, camp_id):
    result = await db.specs_collection_days.insert_one({
        "camp_id": camp_id, "day_date": day(5), "end_date": day(12), "venue": "Optical",
    })
    return result.inserted_id


async def _record_specs(done, op, status, day_id=None, generation=None):
    extra = {"item_type": "specs_made", "status": status}
    if day_id:
        extra["specs_collection_day_id"] = str(day_id)
    body = _issue_body(
        done["transcription"]["id"], done["revision"]["id"],
        generation or done["registration"]["clinical_generation"], op, **extra,
    )
    return await record_fulfilment(body, actor=CLINICAL, background_tasks=None)


def test_an_error_after_the_seat_is_taken_leaves_no_seat_slip_fulfilment_or_operation(monkeypatch):
    async def run(db):
        camp_id, _day, patient = await _printed_patient(db)
        done = await _complete(patient, **_lines(["ot"]))
        day_id = await _ot_day(db, camp_id)
        restore = intercept(monkeypatch, "deferred_slips", "insert_one", _failing("slip"))
        with pytest.raises(RuntimeError):
            await _record(done, "schedule", "deferred", day_id)
        restore()
        assert (await db.ot_schedule_days.find_one({"_id": day_id}))["seats_taken"] == 0
        assert await db.deferred_slips.count_documents({}) == 0
        assert await db.fulfilments.count_documents({}) == 0
        assert await db.clinical_operations.count_documents({"operation_id": "schedule"}) == 0
        out = await _record(done, "schedule", "deferred", day_id)
        assert out["fulfilment"]["status"] == "deferred"
        assert (await db.ot_schedule_days.find_one({"_id": day_id}))["seats_taken"] == 1

    run_camp(monkeypatch, run)


def test_a_token_and_its_sms_intent_commit_together(monkeypatch):
    async def run(db):
        camp_id, _day, patient = await _printed_patient(db)
        sent = recorder(monkeypatch)
        done = await _complete(patient, **_lines(["ot"]))
        day_id = await _ot_day(db, camp_id)
        restore = intercept(monkeypatch, "reminder_ledger", "insert_many", _failing("ledger"))
        with pytest.raises(RuntimeError):
            await _record(done, "schedule", "deferred", day_id)
        restore()
        assert await db.deferred_slips.count_documents({}) == 0
        assert (await db.ot_schedule_days.find_one({"_id": day_id}))["seats_taken"] == 0
        out = await _record(done, "schedule", "deferred", day_id)
        row = await db.reminder_ledger.find_one({"message_type": "ot_token"})
        assert row["event_key"] == out["slip"]["id"] and row["status"] == "sent"
        assert [s["type"] for s in sent] == ["ot_token"]

    run_camp(monkeypatch, run)


def test_two_lines_issued_at_once_on_one_patient_both_commit(monkeypatch):
    async def run(db):
        _camp, _day, patient = await _printed_patient(db)
        done = await _complete(patient, **_lines(["medicine", "specs_fixed"]))
        tid, rid = done["transcription"]["id"], done["revision"]["id"]
        await asyncio.gather(
            record_fulfilment(_issue_body(tid, rid, 1, "med"), actor=CLINICAL, background_tasks=None),
            record_fulfilment(_issue_body(tid, rid, 1, "specs", item_type="specs_fixed", status="fulfilled"),
                              actor=CLINICAL, background_tasks=None),
        )
        assert await db.fulfilments.count_documents({}) == 2
        assert await db.clinical_operations.count_documents({"kind": "issue"}) == 2

    run_camp(monkeypatch, run)


def test_the_same_issue_sent_twice_at_once_applies_once(monkeypatch):
    async def run(db):
        camp_id, _day, patient = await _printed_patient(db)
        done = await _complete(patient, **_lines(["ot"]))
        day_id = await _ot_day(db, camp_id)
        body = _issue_body(done["transcription"]["id"], done["revision"]["id"], 1, "schedule",
                           item_type="ot", status="deferred", ot_schedule_day_id=str(day_id))
        first, second = await asyncio.gather(
            record_fulfilment(body, actor=CLINICAL, background_tasks=None),
            record_fulfilment(body, actor=CLINICAL, background_tasks=None),
        )
        assert first == second
        assert (await db.ot_schedule_days.find_one({"_id": day_id}))["seats_taken"] == 1
        assert await db.deferred_slips.count_documents({}) == 1
        stored = await db.patients.find_one({"_id": patient["_id"]})
        assert "issue_auth_op" not in stored and "issue_authorization" not in stored

    run_camp(monkeypatch, run)


def test_a_replayed_completion_after_undo_is_superseded(monkeypatch):
    async def run(db):
        _camp, _day, patient = await _printed_patient(db)
        body = _complete_body(patient["_id"], "complete")
        await complete_prescription(body, actor=CLINICAL)
        await undo_completion(UndoCompletionBody(
            patient_id=str(patient["_id"]), expected_generation=1, reason="Wrong patient", operation_id="undo",
        ), actor=CLINICAL)
        with pytest.raises(HTTPException) as exc:
            await complete_prescription(body, actor=CLINICAL)
        assert exc.value.status_code == 409 and exc.value.detail["code"] == "OPERATION_SUPERSEDED"

    run_camp(monkeypatch, run)


def test_a_replayed_undo_after_a_new_completion_is_superseded(monkeypatch):
    async def run(db):
        _camp, _day, patient = await _printed_patient(db)
        await complete_prescription(_complete_body(patient["_id"], "complete"), actor=CLINICAL)
        undo = UndoCompletionBody(patient_id=str(patient["_id"]), expected_generation=1, reason="Wrong patient", operation_id="undo")
        await undo_completion(undo, actor=CLINICAL)
        await complete_prescription(_complete_body(patient["_id"], "again", expected_generation=2), actor=CLINICAL)
        with pytest.raises(HTTPException) as exc:
            await undo_completion(undo, actor=CLINICAL)
        assert exc.value.status_code == 409 and exc.value.detail["code"] == "OPERATION_SUPERSEDED"

    run_camp(monkeypatch, run)


def test_a_completion_retry_replays_after_its_medicine_is_retired(monkeypatch):
    async def run(db):
        _camp, _day, patient = await _printed_patient(db)
        body = _complete_body(patient["_id"], "complete")
        first = await complete_prescription(body.model_copy(), actor=CLINICAL)
        await db.medicines.update_one({"_id": ObjectId(MEDICINE["medicine_id"])}, {"$set": {"active": False}})
        assert await complete_prescription(body.model_copy(), actor=CLINICAL) == first

    run_camp(monkeypatch, run)


def test_only_future_days_count_when_deciding_every_day_is_full(monkeypatch):
    async def run(db):
        camp_id, _day, patient = await _printed_patient(db)
        done = await _complete(patient, **_lines(["ot"]))
        await db.ot_schedule_days.insert_one({
            "camp_id": camp_id, "day_date": day(-2), "venue": "Old", "seat_limit": 5, "seats_taken": 0,
        })
        full = await _ot_day(db, camp_id, seat_limit=1)
        await db.ot_schedule_days.update_one({"_id": full}, {"$set": {"seats_taken": 1}})
        with pytest.raises(HTTPException) as exc:
            await _record(done, "schedule", "deferred", full)
        assert exc.value.detail["code"] == "NO_CLINICAL_DAY_AVAILABLE"

    run_camp(monkeypatch, run)


def test_a_redeferral_to_the_same_day_keeps_its_seat_whatever_the_id_case(monkeypatch):
    async def run(db):
        camp_id, _day, patient = await _printed_patient(db)
        done = await _complete(patient, **_lines(["ot"]))
        day_id = await _ot_day(db, camp_id)
        await _record(done, "schedule", "deferred", day_id)
        await _record(done, "again", "deferred", str(day_id).upper())
        stored = await db.ot_schedule_days.find_one({"_id": day_id})
        assert stored["seats_taken"] == 1
        assert not any(key.startswith("released_issues") for key in stored)

    run_camp(monkeypatch, run)


def test_a_retired_medicine_or_power_cannot_be_newly_prescribed_or_issued(monkeypatch):
    async def run(db):
        _camp, _day, patient = await _printed_patient(db)
        done = await _complete(patient, **_lines(["specs_fixed"]))
        await db.medicines.update_one({"_id": ObjectId(MEDICINE["medicine_id"])}, {"$set": {"active": False}})
        await db.fixed_powers.update_one({"value": FIXED_POWER}, {"$set": {"active": False}})
        with pytest.raises(HTTPException) as exc:
            await record_fulfilment(_issue_body(done["transcription"]["id"], done["revision"]["id"], 1, "issue",
                                                item_type="specs_fixed", status="fulfilled"),
                                    actor=CLINICAL, background_tasks=None)
        assert exc.value.detail["code"] == "UNKNOWN_POWER"
        await undo_completion(UndoCompletionBody(
            patient_id=str(patient["_id"]), expected_generation=1, reason="Wrong lines", operation_id="undo",
        ), actor=CLINICAL)
        with pytest.raises(HTTPException) as exc:
            await complete_prescription(_complete_body(patient["_id"], "again", expected_generation=2), actor=CLINICAL)
        assert exc.value.detail["code"] == "UNKNOWN_MEDICINE"

    run_camp(monkeypatch, run)


def test_lines_that_are_not_prescribed_carry_no_content(monkeypatch):
    async def run(db):
        _camp, _day, patient = await _printed_patient(db)
        done = await _complete(patient, prescribed_lines=["specs_made"], prescribed_medicine_ids=[MEDICINE["medicine_id"]],
                               specs_measurements=RX, fixed_power_r=FIXED_POWER, fixed_power_l=FIXED_POWER)
        revision = done["revision"]
        assert revision["prescribed_medicines"] == []
        assert revision["fixed_power_r"] is None and revision["fixed_power_l"] is None
        assert revision["specs_measurements"] == RX

    run_camp(monkeypatch, run)


def test_a_correction_cannot_orphan_a_spectacles_token(monkeypatch):
    async def run(db):
        camp_id, _day, patient = await _printed_patient(db)
        done = await _complete(patient, **_lines(["specs_made"]))
        specs_day = await _specs_day(db, camp_id)
        await _record_specs(done, "order", "deferred", specs_day)
        base = dict(patient_id=str(patient["_id"]), reason="Doctor changed the order", expected_generation=1,
                    full_transcription_confirmed=True)
        for op, change in (
            ("away", {"prescribed_lines": ["specs_fixed"], "specs_measurements": None,
                      "fixed_power_r": FIXED_POWER, "fixed_power_l": FIXED_POWER}),
            ("regrind", {"prescribed_lines": ["specs_made"], "specs_measurements": {**RX, "r_sph": "-3.00"}}),
        ):
            with pytest.raises(HTTPException) as exc:
                await add_correction(CorrectionBody(**base, operation_id=op, **change), actor=CLINICAL)
            assert exc.value.status_code == 409 and exc.value.detail["code"] == "SPECS_SCHEDULED"
        cancelled = await _record_specs(done, "cancel", "cancelled")
        assert cancelled["fulfilment"]["status"] == "cancelled"
        assert await db.deferred_slips.count_documents({"active": True}) == 0
        corrected = await add_correction(CorrectionBody(
            **base, operation_id="after", prescribed_lines=["specs_fixed"], specs_measurements=None,
            fixed_power_r=FIXED_POWER, fixed_power_l=FIXED_POWER,
        ), actor=CLINICAL)
        issued = await record_fulfilment(_issue_body(
            done["transcription"]["id"], corrected["revision"]["id"], 2, "fixed", item_type="specs_fixed", status="fulfilled",
        ), actor=CLINICAL, background_tasks=None)
        assert issued["fulfilment"]["status"] == "fulfilled"

    run_camp(monkeypatch, run)


def test_the_unused_corrections_list_endpoint_is_gone():
    assert "/api/clinical/corrections/{transcription_id}" not in {route.path for route in routes_clinical.router.routes}
