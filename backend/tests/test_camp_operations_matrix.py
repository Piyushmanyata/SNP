"""C/F/P/S/M acceptance matrix against shipped clinical/desk/camp handlers."""
import asyncio
from datetime import datetime
from functools import partial

import pytest
from bson import ObjectId
from fastapi import HTTPException
from pymongo.asynchronous.collection import AsyncCollection

import routes_camps
import routes_reports
import sms
from helpers import IST
from models import (
    CampBody,
    CompletePrescriptionBody,
    CorrectionBody,
    FulfilmentBody,
    IdentityCheckBody,
    PrintWindowBody,
    RegisterBody,
    TranscriptionBody,
    UndoCompletionBody,
)
from routes_clinical import (
    add_correction,
    clinical_lookup,
    complete_prescription,
    create_transcription,
    record_fulfilment,
    undo_completion,
)
from routes_desk import arrive, preview_prescription, print_prescription, record_identity_check
from routes_registration import _create_registration
from seed import (
    FIXED_POWER, MEDICINE, MEDICINE_ALT, NOW, TODAY, TOMORROW, Request, day, patient_doc, register, run_camp,
    seed_camp, user_doc,
)

VOLUNTEER = {"_id": ObjectId(), "role": "volunteer", "name": "Vol"}
LEAD = {"_id": ObjectId(), "role": "team_lead", "name": "Lead"}
ADMIN = {"_id": ObjectId(), "role": "admin", "name": "Admin"}
CLINICAL = {"_id": ObjectId(), "role": "clinical_desk_operator", "name": "Clin"}
RX = {
    "r_sph": "-1.00", "r_cyl": "-0.50", "r_axis": "90",
    "l_sph": "-1.25", "l_cyl": "-0.25", "l_axis": "85", "add": "+2.00",
}
OT_DATE = day(7)


def ist(day_date, hhmm):
    return datetime.fromisoformat(f"{day_date}T{hhmm}").replace(tzinfo=IST)


def intercept(monkeypatch, collection, method, hook):
    real = getattr(AsyncCollection, method)

    async def patched(self, *args, **kwargs):
        if self.name != collection:
            return await real(self, *args, **kwargs)
        return await hook(partial(real, self), *args, **kwargs)

    monkeypatch.setattr(AsyncCollection, method, patched)
    return lambda: monkeypatch.setattr(AsyncCollection, method, real)


async def _seed_camp(db, day_date=TODAY):
    camp_id, (day_id,) = await seed_camp(db, days=(day_date,), camp_date=day_date, print_override=None)
    return camp_id, day_id


async def _ensure_user(db, actor):
    if await db.users.find_one({"_id": actor["_id"]}):
        return
    await db.users.insert_one(user_doc(
        actor["name"], actor["role"], _id=actor["_id"], team_lead_id=actor.get("team_lead_id"),
    ))


async def _register_printed(day_id, registrar=VOLUNTEER, arrived=True, printed=True, **fields):
    pid = (await register(day_id, actor=registrar, **fields))["id"]
    if arrived or printed:
        await _identity_checked(pid)
    if arrived:
        await arrive(pid, actor=registrar)
    if printed:
        await print_prescription(pid, actor=registrar)
    return pid


async def _printed_patient(db, registrar=VOLUNTEER, **fields):
    await _ensure_user(db, registrar)
    await _ensure_user(db, CLINICAL)
    await _ensure_user(db, LEAD)
    camp_id, day_id = await _seed_camp(db)
    pid = await _register_printed(day_id, registrar, **fields)
    return camp_id, day_id, await db.patients.find_one({"_id": ObjectId(pid)})


async def _identity_checked(patient_id):
    await record_identity_check(
        IdentityCheckBody(patient_id=str(patient_id), reason="Voter ID seen"), actor=ADMIN,
    )


def _complete_body(patient_id, operation_id, **extra):
    data = dict(
        patient_id=str(patient_id),
        expected_generation=0,
        full_transcription_confirmed=True,
        prescribed_lines=["medicine"],
        operation_id=operation_id,
        diagnosis_options=["Cataract"],
        prescribed_medicine_ids=[MEDICINE["medicine_id"]],
        bp="120/80",
    )
    data.update(extra)
    return CompletePrescriptionBody(**data)


def _issue_body(transcription_id, revision_id, generation, operation_id, **extra):
    data = dict(
        transcription_id=str(transcription_id),
        item_type="medicine",
        status="fulfilled",
        paper_reviewed=True,
        reviewed_revision_id=str(revision_id),
        reviewed_generation=generation,
        operation_id=operation_id,
    )
    data.update(extra)
    if data.get("item_type") == "medicine" and "medicine_outcomes" not in data:
        data["medicine_outcomes"] = [
            {"medicine_id": MEDICINE["medicine_id"], "given": data.get("status") != "not_available"},
        ]
    return FulfilmentBody(**data)


def _code(exc):
    detail = exc.value.detail
    if isinstance(detail, dict):
        return detail.get("code")
    return detail


class TestClinicalMatrix:
    def test_c01_lookup_after_print_before_seen(self, monkeypatch):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)
            out = await clinical_lookup({"value": str(patient["reg_no"])}, actor=CLINICAL)
            assert out["registration"]["id"] == str(patient["_id"])
            assert out["registration"]["queue_status"] != "seen"
            assert out["transcription"] is None
        run_camp(monkeypatch, run)

    def test_c02_non_operator_cannot_mutate_clinical(self, monkeypatch):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)
            body = _complete_body(patient["_id"], "op-c02")
            for actor in (VOLUNTEER, LEAD, ADMIN):
                with pytest.raises(HTTPException) as exc:
                    await complete_prescription(body, actor=actor)
                assert exc.value.status_code == 403
            refreshed = await db.patients.find_one({"_id": patient["_id"]})
            assert refreshed.get("committed_revision_id") is None
            assert refreshed.get("queue_status") != "seen"
        run_camp(monkeypatch, run)

    def test_c04_draft_saves_without_seen_or_fulfilment(self, monkeypatch):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)
            out = await create_transcription(
                TranscriptionBody(patient_id=str(patient["_id"]), bp="110/70"),
                actor=CLINICAL,
            )
            assert out["transcription"]["bp"] == "110/70"
            refreshed = await db.patients.find_one({"_id": patient["_id"]})
            assert refreshed.get("seen_at") is None
            assert refreshed.get("committed_revision_id") is None
            trans_id = out["transcription"]["id"]
            with pytest.raises(HTTPException) as exc:
                await record_fulfilment(
                    _issue_body(trans_id, ObjectId(), 0, "op-f-draft"),
                    actor=CLINICAL,
                 background_tasks=None)
            assert exc.value.status_code == 409
        run_camp(monkeypatch, run)

    def test_c05_complete_without_arrival_or_print(self, monkeypatch):
        async def run(db):
            camp_id, day_id = await _seed_camp(db)
            pid = (await register(day_id, actor=VOLUNTEER, full_name="No Arrive", age=40, phone="9876500099"))["id"]
            with pytest.raises(HTTPException) as exc:
                await complete_prescription(_complete_body(pid, "op-c05"), actor=CLINICAL)
            assert exc.value.status_code == 409
            assert _code(exc) in ("NOT_ARRIVED", "NEVER_PRINTED")
            patient = await db.patients.find_one({"_id": ObjectId(pid)})
            assert patient.get("committed_revision_id") is None
        run_camp(monkeypatch, run)

    def test_c06_blank_completion_rejected(self, monkeypatch):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)
            with pytest.raises(HTTPException) as exc:
                await complete_prescription(
                    CompletePrescriptionBody(
                        patient_id=str(patient["_id"]),
                        full_transcription_confirmed=True,
                        operation_id="op-c06",
                    ),
                    actor=CLINICAL,
                )
            assert exc.value.status_code == 400
            assert exc.value.detail["code"] == "INCOMPLETE_PRESCRIPTION"
            refreshed = await db.patients.find_one({"_id": patient["_id"]})
            assert refreshed.get("seen_at") is None
        run_camp(monkeypatch, run)

    def test_c07_none_prescribed_completion_awards_point(self, monkeypatch):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)
            out = await complete_prescription(
                CompletePrescriptionBody(
                    patient_id=str(patient["_id"]),
                    full_transcription_confirmed=True,
                    none_prescribed=True,
                    operation_id="op-c07",
                    remarks="Observe only",
                ),
                actor=CLINICAL,
            )
            assert out["registration"]["queue_status"] == "seen"
            assert out["revision"]["none_prescribed"] is True
            refreshed = await db.patients.find_one({"_id": patient["_id"]})
            assert refreshed.get("committed_revision_id") is not None
            assert await db.fulfilments.find_one({"patient_id": patient["_id"]}) is None
        run_camp(monkeypatch, run)

    def test_c08_whole_rx_completion_is_atomic(self, monkeypatch):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)
            out = await complete_prescription(_complete_body(patient["_id"], "op-c08"), actor=CLINICAL)
            assert out["registration"]["queue_status"] == "seen"
            assert out["revision"]["id"]
            assert out["registration"]["clinical_generation"] == 1
            refreshed = await db.patients.find_one({"_id": patient["_id"]})
            assert str(refreshed["committed_revision_id"]) == out["revision"]["id"]
            assert refreshed["queue_status"] == "seen"
        run_camp(monkeypatch, run)

    def test_c09_a_failed_commit_leaves_no_revision_and_grants_nothing(self, monkeypatch):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)

            async def boom(*_a, **_k):
                raise RuntimeError("commit failed")

            restore = intercept(monkeypatch, "patients", "find_one_and_update", boom)
            with pytest.raises(RuntimeError):
                await complete_prescription(_complete_body(patient["_id"], "op-c09"), actor=CLINICAL)
            restore()
            refreshed = await db.patients.find_one({"_id": patient["_id"]})
            assert refreshed.get("seen_at") is None
            assert refreshed.get("committed_revision_id") is None
            assert not await db.prescription_revisions.find_one({"operation_id": "op-c09"})
            out = await complete_prescription(_complete_body(patient["_id"], "op-c09"), actor=CLINICAL)
            assert out["registration"]["queue_status"] == "seen"
        run_camp(monkeypatch, run)

    def test_c10_lost_response_reconciles(self, monkeypatch):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)
            first = await complete_prescription(_complete_body(patient["_id"], "op-c10"), actor=CLINICAL)
            second = await complete_prescription(_complete_body(patient["_id"], "op-c10"), actor=CLINICAL)
            assert first["revision"]["id"] == second["revision"]["id"]
            assert await db.prescription_revisions.count_documents({}) == 1
        run_camp(monkeypatch, run)

    def test_c11_concurrent_completion_one_winner(self, monkeypatch):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)
            other = {"_id": ObjectId(), "role": "clinical_desk_operator", "name": "Clin2"}
            results = await asyncio.gather(
                complete_prescription(
                    _complete_body(patient["_id"], "op-c11a",
                                   prescribed_medicine_ids=[MEDICINE["medicine_id"]]),
                    actor=CLINICAL,
                ),
                complete_prescription(
                    _complete_body(patient["_id"], "op-c11b",
                                   prescribed_medicine_ids=[MEDICINE_ALT["medicine_id"]]),
                    actor=other,
                ),
                return_exceptions=True,
            )
            wins = [r for r in results if not isinstance(r, Exception)]
            losses = [r for r in results if isinstance(r, HTTPException)]
            assert len(wins) == 1
            assert len(losses) == 1
            assert losses[0].status_code == 409
            refreshed = await db.patients.find_one({"_id": patient["_id"]})
            assert str(refreshed["committed_revision_id"]) == wins[0]["revision"]["id"]
            winner_rev = await db.prescription_revisions.find_one({"_id": refreshed["committed_revision_id"]})
            trans = await db.transcriptions.find_one({"patient_id": patient["_id"]})
            assert trans["prescribed_medicines"] == winner_rev["prescribed_medicines"]
        run_camp(monkeypatch, run)

    def test_c12_pre_issue_undo_revokes_point(self, monkeypatch):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)
            done = await complete_prescription(_complete_body(patient["_id"], "op-c12"), actor=CLINICAL)
            out = await undo_completion(
                UndoCompletionBody(
                    patient_id=str(patient["_id"]),
                    expected_generation=done["registration"]["clinical_generation"],
                    reason="Wrong patient",
                    operation_id="op-c12-undo",
                ),
                actor=CLINICAL,
            )
            assert out["registration"]["queue_status"] == "arrived"
            refreshed = await db.patients.find_one({"_id": patient["_id"]})
            assert refreshed.get("committed_revision_id") is None
            assert refreshed.get("seen_at") is None
            assert await db.prescription_revisions.find_one({"operation_id": "op-c12"})
        run_camp(monkeypatch, run)

    def test_c13_old_complete_retry_after_undo(self, monkeypatch):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)
            done = await complete_prescription(_complete_body(patient["_id"], "op-c13"), actor=CLINICAL)
            await undo_completion(
                UndoCompletionBody(
                    patient_id=str(patient["_id"]),
                    expected_generation=done["registration"]["clinical_generation"],
                    reason="Undo",
                    operation_id="op-c13-undo",
                ),
                actor=CLINICAL,
            )
            with pytest.raises(HTTPException) as exc:
                await complete_prescription(_complete_body(patient["_id"], "op-c13"), actor=CLINICAL)
            assert exc.value.status_code == 409
            refreshed = await db.patients.find_one({"_id": patient["_id"]})
            assert refreshed.get("committed_revision_id") is None
        run_camp(monkeypatch, run)

    def test_c14_undo_after_issue_rejected(self, monkeypatch):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)
            done = await complete_prescription(_complete_body(patient["_id"], "op-c14"), actor=CLINICAL)
            await record_fulfilment(
                _issue_body(
                    done["transcription"]["id"],
                    done["revision"]["id"],
                    done["registration"]["clinical_generation"],
                    "op-c14-issue",
                ),
                actor=CLINICAL,
             background_tasks=None)
            with pytest.raises(HTTPException) as exc:
                await undo_completion(
                    UndoCompletionBody(
                        patient_id=str(patient["_id"]),
                        expected_generation=done["registration"]["clinical_generation"],
                        reason="too late",
                        operation_id="op-c14-undo",
                    ),
                    actor=CLINICAL,
                )
            assert exc.value.status_code == 409
            refreshed = await db.patients.find_one({"_id": patient["_id"]})
            assert refreshed.get("committed_revision_id") is not None
            assert await db.fulfilments.find_one({"transcription_id": ObjectId(done["transcription"]["id"])})
        run_camp(monkeypatch, run)

    def test_c15_correction_after_issue_keeps_history(self, monkeypatch):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)
            done = await complete_prescription(_complete_body(patient["_id"], "op-c15"), actor=CLINICAL)
            issued = await record_fulfilment(
                _issue_body(
                    done["transcription"]["id"],
                    done["revision"]["id"],
                    done["registration"]["clinical_generation"],
                    "op-c15-issue",
                ),
                actor=CLINICAL,
             background_tasks=None)
            corr = await add_correction(
                CorrectionBody(
                    transcription_id=done["transcription"]["id"],
                    patient_id=str(patient["_id"]),
                    reason="BP mistyped",
                    expected_generation=done["registration"]["clinical_generation"],
                    operation_id="op-c15-corr",
                    full_transcription_confirmed=True,
                    prescribed_lines=["medicine"],
                    diagnosis_options=["Cataract"],
                    prescribed_medicine_ids=[MEDICINE["medicine_id"]],
                    bp="140/90",
                ),
                actor=CLINICAL,
            )
            assert corr["revision"]["bp"] == "140/90"
            assert corr["revision"]["id"] != done["revision"]["id"]
            assert issued["fulfilment"]["id"]
            assert await db.fulfilments.find_one({"_id": ObjectId(issued["fulfilment"]["id"])})
        run_camp(monkeypatch, run)

    def test_c16_second_complete_conflicts(self, monkeypatch):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)
            await complete_prescription(_complete_body(patient["_id"], "op-c16a"), actor=CLINICAL)
            with pytest.raises(HTTPException) as exc:
                await complete_prescription(_complete_body(patient["_id"], "op-c16b"), actor=CLINICAL)
            assert exc.value.status_code == 409
        run_camp(monkeypatch, run)


class TestFulfilmentMatrix:
    def test_f01_issue_without_completion_or_review(self, monkeypatch):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)
            draft = await create_transcription(
                TranscriptionBody(
                    patient_id=str(patient["_id"]),
                    diagnosis_options=["Cataract"],
                    prescribed_medicine_ids=[MEDICINE["medicine_id"]],
                ),
                actor=CLINICAL,
            )
            with pytest.raises(HTTPException) as exc:
                await record_fulfilment(
                    FulfilmentBody(
                        transcription_id=draft["transcription"]["id"],
                        item_type="medicine",
                        status="fulfilled",
                    ),
                    actor=CLINICAL,
                 background_tasks=None)
            assert exc.value.status_code == 409
            assert await db.fulfilments.find_one({}) is None
        run_camp(monkeypatch, run)

    def test_f02_foreign_revision_rejected(self, monkeypatch):
        async def run(db):
            _camp, day_id, patient = await _printed_patient(db)
            other_id = await _register_printed(day_id, full_name="Other Person", age=40, phone="9876500002")
            other = await db.patients.find_one({"_id": ObjectId(other_id)})
            done = await complete_prescription(_complete_body(patient["_id"], "op-f02a"), actor=CLINICAL)
            other_done = await complete_prescription(
                _complete_body(other["_id"], "op-f02b", prescribed_lines=["medicine"]),
                actor=CLINICAL,
            )
            with pytest.raises(HTTPException) as exc:
                await record_fulfilment(
                    _issue_body(
                        other_done["transcription"]["id"],
                        done["revision"]["id"],
                        done["registration"]["clinical_generation"],
                        "op-f02-issue",
                    ),
                    actor=CLINICAL,
                 background_tasks=None)
            assert exc.value.status_code in (404, 409)
            name = other["full_name"]
            assert name not in str(exc.value.detail)
        run_camp(monkeypatch, run)

    def test_f03_stale_review_after_new_revision(self, monkeypatch):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)
            done = await complete_prescription(_complete_body(patient["_id"], "op-f03"), actor=CLINICAL)
            corr = await add_correction(
                CorrectionBody(
                    transcription_id=done["transcription"]["id"],
                    patient_id=str(patient["_id"]),
                    reason="Add drops",
                    expected_generation=done["registration"]["clinical_generation"],
                    operation_id="op-f03-corr",
                    full_transcription_confirmed=True,
                    prescribed_lines=["medicine"],
                    diagnosis_options=["Cataract"],
                    prescribed_medicine_ids=[MEDICINE_ALT["medicine_id"]],
                    bp="120/80",
                ),
                actor=CLINICAL,
            )
            with pytest.raises(HTTPException) as exc:
                await record_fulfilment(
                    _issue_body(
                        done["transcription"]["id"],
                        done["revision"]["id"],
                        done["registration"]["clinical_generation"],
                        "op-f03-issue",
                    ),
                    actor=CLINICAL,
                 background_tasks=None)
            assert exc.value.status_code == 409
            assert _code(exc) == "STALE_REVIEW"
            ok = await record_fulfilment(
                _issue_body(
                    done["transcription"]["id"],
                    corr["revision"]["id"],
                    corr["registration"]["clinical_generation"],
                    "op-f03-issue-b",
                    medicine_outcomes=[{"medicine_id": MEDICINE_ALT["medicine_id"], "given": True}],
                ),
                actor=CLINICAL,
             background_tasks=None)
            assert ok["fulfilment"]["status"] == "fulfilled"
        run_camp(monkeypatch, run)

    def test_f04_correction_races_issue(self, monkeypatch):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)
            done = await complete_prescription(_complete_body(patient["_id"], "op-f04"), actor=CLINICAL)
            corr_body = CorrectionBody(
                transcription_id=done["transcription"]["id"],
                patient_id=str(patient["_id"]),
                reason="race",
                expected_generation=done["registration"]["clinical_generation"],
                operation_id="op-f04-corr",
                full_transcription_confirmed=True,
                prescribed_lines=["medicine"],
                diagnosis_options=["Cataract"],
                prescribed_medicine_ids=[MEDICINE["medicine_id"]],
                bp="130/85",
            )
            issue_body = _issue_body(
                done["transcription"]["id"],
                done["revision"]["id"],
                done["registration"]["clinical_generation"],
                "op-f04-issue",
            )
            results = await asyncio.gather(
                add_correction(corr_body, actor=CLINICAL),
                record_fulfilment(issue_body, actor=CLINICAL, background_tasks=None),
                return_exceptions=True,
            )
            http_err = [r for r in results if isinstance(r, HTTPException)]
            wins = [r for r in results if not isinstance(r, Exception)]
            assert len(wins) == 1
            assert len(http_err) == 1
            assert http_err[0].status_code == 409
        run_camp(monkeypatch, run)

    def test_f05_retry_recovers_same_allocation(self, monkeypatch):
        async def run(db):
            camp_id, _day, patient = await _printed_patient(db)
            done = await complete_prescription(
                _complete_body(patient["_id"], "op-f05", prescribed_lines=["ot"],
                               ot_eye="right", ot_outcome="iol_surgery",
                               prescribed_medicine_ids=[]),
                actor=CLINICAL,
            )
            ot_day = ObjectId()
            await db.ot_schedule_days.insert_one({
                "_id": ot_day, "camp_id": camp_id, "day_date": OT_DATE,
                "venue": "OT", "seat_limit": 1, "seats_taken": 0,
            })
            body = _issue_body(
                done["transcription"]["id"], done["revision"]["id"],
                done["registration"]["clinical_generation"], "op-f05-issue",
                item_type="ot", status="deferred", ot_schedule_day_id=str(ot_day),
            )
            first = await record_fulfilment(body, actor=CLINICAL, background_tasks=None)
            second = await record_fulfilment(body, actor=CLINICAL, background_tasks=None)
            assert first["fulfilment"]["id"] == second["fulfilment"]["id"]
            assert (await db.ot_schedule_days.find_one({"_id": ot_day}))["seats_taken"] == 1
        run_camp(monkeypatch, run)

    def test_f06_double_tap_same_issue(self, monkeypatch):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)
            done = await complete_prescription(_complete_body(patient["_id"], "op-f06"), actor=CLINICAL)
            body = _issue_body(
                done["transcription"]["id"], done["revision"]["id"],
                done["registration"]["clinical_generation"], "op-f06-issue",
            )
            a = await record_fulfilment(body, actor=CLINICAL, background_tasks=None)
            b = await record_fulfilment(body, actor=CLINICAL, background_tasks=None)
            assert a["fulfilment"]["id"] == b["fulfilment"]["id"]
            assert await db.fulfilments.count_documents({}) == 1
        run_camp(monkeypatch, run)

    def test_f07_last_ot_slot_no_oversubscribe(self, monkeypatch):
        async def run(db):
            camp_id, day_id = await _seed_camp(db)
            patients = []
            for i, name in enumerate(("One", "Two")):
                pid = await _register_printed(day_id, full_name=name, age=50, phone=f"987650001{i}")
                patients.append(await db.patients.find_one({"_id": ObjectId(pid)}))
            ot_day = ObjectId()
            await db.ot_schedule_days.insert_one({
                "_id": ot_day, "camp_id": camp_id, "day_date": OT_DATE,
                "venue": "OT", "seat_limit": 1, "seats_taken": 0,
            })
            bodies = []
            for i, p in enumerate(patients):
                done = await complete_prescription(
                    _complete_body(p["_id"], f"op-f07-{i}", prescribed_lines=["ot"],
                                   ot_eye="left", ot_outcome="iol_surgery",
                                   prescribed_medicine_ids=[]),
                    actor=CLINICAL,
                )
                bodies.append(_issue_body(
                    done["transcription"]["id"], done["revision"]["id"],
                    done["registration"]["clinical_generation"], f"op-f07-issue-{i}",
                    item_type="ot", status="deferred", ot_schedule_day_id=str(ot_day),
                ))
            results = await asyncio.gather(
                record_fulfilment(bodies[0], actor=CLINICAL, background_tasks=None),
                record_fulfilment(bodies[1], actor=CLINICAL, background_tasks=None),
                return_exceptions=True,
            )
            wins = [r for r in results if not isinstance(r, Exception)]
            losses = [r for r in results if isinstance(r, HTTPException)]
            assert len(wins) == 1
            assert len(losses) == 1
            assert (await db.ot_schedule_days.find_one({"_id": ot_day}))["seats_taken"] == 1
        run_camp(monkeypatch, run)

    def test_f08_fixed_and_made_exclusive(self, monkeypatch):
        async def run(db):
            camp_id, _day, patient = await _printed_patient(db)
            done = await complete_prescription(
                _complete_body(
                    patient["_id"], "op-f08",
                    prescribed_lines=["specs_fixed"],
                    specs_measurements=RX,
                    fixed_power_r=FIXED_POWER, fixed_power_l=FIXED_POWER,
                    prescribed_medicine_ids=[],
                ),
                actor=CLINICAL,
            )
            await db.prescription_revisions.update_one(
                {"_id": ObjectId(done["revision"]["id"])},
                {"$set": {"prescribed_lines": ["specs_fixed", "specs_made"]}},
            )
            await record_fulfilment(
                _issue_body(
                    done["transcription"]["id"], done["revision"]["id"],
                    done["registration"]["clinical_generation"], "op-f08-fixed",
                    item_type="specs_fixed", status="fulfilled",
                ),
                actor=CLINICAL,
             background_tasks=None)
            specs_day = ObjectId()
            await db.specs_collection_days.insert_one({
                "_id": specs_day, "camp_id": camp_id, "day_date": day(15),
                "venue": "Optical", "start_time": "09:00", "end_time": "17:00",
                "seat_limit": 10, "seats_taken": 0,
            })
            with pytest.raises(HTTPException) as exc:
                await record_fulfilment(
                    _issue_body(
                        done["transcription"]["id"], done["revision"]["id"],
                        done["registration"]["clinical_generation"], "op-f08-made",
                        item_type="specs_made", status="deferred",
                        specs_collection_day_id=str(specs_day),
                    ),
                    actor=CLINICAL,
                 background_tasks=None)
            assert exc.value.status_code == 409
        run_camp(monkeypatch, run)

    def test_f09_reprint_does_not_confer_care(self, monkeypatch):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)
            printed_at = patient["printed_at"]
            again = await print_prescription(str(patient["_id"]), actor=VOLUNTEER)
            refreshed = await db.patients.find_one({"_id": patient["_id"]})
            assert refreshed["printed_at"] == printed_at
            assert refreshed.get("seen_at") is None
            assert refreshed.get("committed_revision_id") is None
            assert again["registration"]["queue_status"] != "seen"
        run_camp(monkeypatch, run)


class TestPrintingMatrix:
    def test_p01_ist_midnight_opens_scheduled_day(self, monkeypatch):
        async def run(db):
            camp_id, day_id = await _seed_camp(db, day_date=TOMORROW)
            camp = await db.camps.find_one({"_id": camp_id})
            days = await db.camp_days.find().to_list(None)
            closed = routes_camps.effective_printing(camp, days, now=ist(TODAY, "23:30"))
            opened = routes_camps.effective_printing(camp, days, now=ist(TOMORROW, "00:01"))
            assert closed["printing_open"] is False
            assert opened["printing_open"] is True
            assert opened["operating_day_id"] == str(day_id)
        run_camp(monkeypatch, run)

    def test_p02_manual_off_blocks_door_scan(self, monkeypatch):
        async def run(db):
            camp_id, day_id = await _seed_camp(db)
            await routes_camps.toggle_print_window(str(day_id), PrintWindowBody(mode="disable"), actor=ADMIN)
            pid = (await register(
                day_id, actor=VOLUNTEER, full_name="Walk", aadhaar_scanned=True, aadhaar_last4="7766", dob="1970-02-02",
            ))["id"]
            with pytest.raises(HTTPException) as exc:
                await arrive(pid, actor=VOLUNTEER)
            assert exc.value.detail["code"] == "PRINT_WINDOW_CLOSED"
            refreshed = await db.patients.find_one({"_id": ObjectId(pid)})
            assert refreshed.get("arrived_at") is None
        run_camp(monkeypatch, run)

    def test_p03_manual_early_open_uses_selected_day(self, monkeypatch):
        async def run(db):
            camp_id, (_today_id, future_id) = await seed_camp(
                db, days=(TODAY, day(9)), name="Camp", venue="Hall", camp_date=TODAY, print_override=None,
            )
            await routes_camps.toggle_print_window(
                str(future_id), PrintWindowBody(mode="enable", day_id=str(future_id)), actor=ADMIN,
            )
            camp = await db.camps.find_one({"_id": camp_id})
            days = await db.camp_days.find().to_list(None)
            state = routes_camps.effective_printing(camp, days, now=ist(TODAY, "10:00"))
            assert state["printing_open"] is True
            assert state["operating_day_id"] == str(future_id)
        run_camp(monkeypatch, run)

    def test_p04_override_expires_and_does_not_cross_camps(self, monkeypatch):
        async def run(db):
            camp_id, day_id = await _seed_camp(db, day_date=day(9))
            await routes_camps.toggle_print_window(
                str(day_id), PrintWindowBody(mode="enable", day_id=str(day_id)), actor=ADMIN,
            )
            camp = await db.camps.find_one({"_id": camp_id})
            days = await db.camp_days.find().to_list(None)
            assert routes_camps.effective_printing(camp, days, now=ist(TODAY, "23:59"))["printing_open"] is True
            expired = routes_camps.effective_printing(camp, days, now=ist(TOMORROW, "00:01"))
            assert expired["printing_open"] is False
            other = ObjectId()
            await db.camps.insert_one({
                "_id": other, "name": "Other", "venue": "X", "is_active": False, "print_override": None,
            })
            await routes_camps.activate_camp(str(other), actor=ADMIN)
            other_doc = await db.camps.find_one({"_id": other})
            assert not other_doc.get("print_override")
        run_camp(monkeypatch, run)

    def test_p05_stale_print_rejected(self, monkeypatch):
        async def run(db):
            camp_id, day_id = await _seed_camp(db)
            pid = await _register_printed(day_id, printed=False, full_name="Stale", age=40, phone="9876500077")
            await routes_camps.toggle_print_window(str(day_id), PrintWindowBody(mode="disable"), actor=ADMIN)
            with pytest.raises(HTTPException) as exc:
                await print_prescription(pid, actor=VOLUNTEER)
            assert exc.value.detail["code"] == "PRINT_WINDOW_CLOSED"
            refreshed = await db.patients.find_one({"_id": ObjectId(pid)})
            assert refreshed.get("printed_at") is None
        run_camp(monkeypatch, run)

    def test_p06_walkin_vs_repeat_scan(self, monkeypatch):
        async def run(db):
            _camp, day_id, patient = await _printed_patient(db)
            created_by = patient["created_by"]
            await arrive(str(patient["_id"]), actor=LEAD)
            refreshed = await db.patients.find_one({"_id": patient["_id"]})
            assert refreshed["created_by"] == created_by
            assert refreshed.get("committed_revision_id") is None
        run_camp(monkeypatch, run)

    def test_p07_partial_camp_setup_no_false_success(self, monkeypatch):
        async def run(db):
            calls = []

            async def flaky(insert_one, doc, *args, **kwargs):
                calls.append(doc)
                if len(calls) == 2:
                    raise RuntimeError("day 2 failed")
                return await insert_one(doc, *args, **kwargs)

            restore = intercept(monkeypatch, "camp_days", "insert_one", flaky)
            days = [
                {"day_date": TODAY, "seat_limit": 50},
                {"day_date": TOMORROW, "seat_limit": 50},
            ]
            with pytest.raises(HTTPException) as exc:
                await routes_camps.create_camp(
                    CampBody(name="Setup", venue="Hall", camp_date=TODAY,
                             setup_request_id="setup-1", days=days),
                    actor=ADMIN,
                )
            assert exc.value.status_code == 409
            assert exc.value.detail["code"] == "CAMP_SETUP_INCOMPLETE"
            camp_id = exc.value.detail["camp_id"]
            camp = await db.camps.find_one({"_id": ObjectId(camp_id)})
            assert camp["is_active"] is False
            restore()
            out = await routes_camps.create_camp(
                CampBody(name="Setup", venue="Hall", camp_date=TODAY,
                         setup_request_id="setup-1", days=days),
                actor=ADMIN,
            )
            assert out["camp"]["id"] == camp_id
            assert out["camp"]["is_active"] is False
            assert await db.camp_days.count_documents({}) == 2
        run_camp(monkeypatch, run)

    def test_p07_camp_number_is_set_at_setup_and_editable(self, monkeypatch):
        async def run(db):
            out = await routes_camps.create_camp(
                CampBody(name="SNP नेत्र शिविर", venue="Hall", camp_date=TODAY, camp_number=162), actor=ADMIN,
            )
            assert out["camp"]["camp_number"] == 162
            edited = await routes_camps.update_camp(out["camp"]["id"], CampBody(
                name="SNP नेत्र शिविर", venue="हंसा गार्डन, देवघर", camp_date=TODAY, camp_number=163,
            ), actor=ADMIN)
            assert edited["camp"]["camp_number"] == 163
            assert edited["camp"]["venue"] == "हंसा गार्डन, देवघर"
            with pytest.raises(ValueError):
                CampBody(name="x", venue="y", camp_date=TODAY, camp_number=0)
        run_camp(monkeypatch, run)

    def test_p08_existing_arrival_no_second_booking(self, monkeypatch):
        async def run(db):
            camp_id, (d1, d2) = await seed_camp(
                db, days=(TODAY, day(2)), name="Camp", venue="Hall", camp_date=TODAY,
            )
            await db.camp_days.update_many({"camp_id": camp_id}, {"$set": {"seat_limit": 1}})
            pid = (await register(d1, actor=VOLUNTEER, full_name="Booked", age=40, phone="9876500044"))["id"]
            await _identity_checked(pid)
            await arrive(pid, actor=VOLUNTEER)
            day1 = await db.camp_days.find_one({"_id": d1})
            day2 = await db.camp_days.find_one({"_id": d2})
            assert day1["booked"] == 1
            assert day2["booked"] == 0
        run_camp(monkeypatch, run)

    def test_p09_print_blocked_once_doctor_seen(self, monkeypatch):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)
            done = await complete_prescription(_complete_body(patient["_id"], "op-p09"), actor=CLINICAL)
            assert done["registration"]["queue_status"] == "seen"
            for call in (preview_prescription, print_prescription):
                with pytest.raises(HTTPException) as exc:
                    await call(str(patient["_id"]), actor=VOLUNTEER)
                assert exc.value.status_code == 409
                assert exc.value.detail["code"] == "ALREADY_SEEN"
            await undo_completion(
                UndoCompletionBody(
                    patient_id=str(patient["_id"]),
                    expected_generation=done["registration"]["clinical_generation"],
                    reason="Wrong patient",
                    operation_id="op-p09-undo",
                ),
                actor=CLINICAL,
            )
            reprint = await print_prescription(str(patient["_id"]), actor=VOLUNTEER)
            assert reprint["prescription"]["reg_no"] == patient["reg_no"]
        run_camp(monkeypatch, run)


class TestScoringAndMessages:
    def test_s01_lead_direct_no_double_count(self, monkeypatch):
        async def run(db):
            camp_id, _day, patient = await _printed_patient(db, registrar=LEAD)
            await complete_prescription(_complete_body(patient["_id"], "op-s01"), actor=CLINICAL)
            board = await routes_reports.leaderboard(actor=LEAD)
            lead = next(x for x in board["team_leads"] if x["id"] == str(LEAD["_id"]))
            assert lead["personal_completed"] == 1
            assert lead["completed"] == 1
        run_camp(monkeypatch, run)

    def test_s02_team_change_keeps_original_credit(self, monkeypatch):
        async def run(db):
            lead_a, lead_b = ObjectId(), ObjectId()
            vol = {"_id": ObjectId(), "role": "volunteer", "name": "V", "team_lead_id": str(lead_a)}
            await db.users.insert_many([
                user_doc("A", "team_lead", _id=lead_a), user_doc("B", "team_lead", _id=lead_b),
                user_doc("V", "volunteer", _id=vol["_id"], team_lead_id=str(lead_a)),
            ])
            _camp, _day, patient = await _printed_patient(db, registrar=vol)
            await complete_prescription(_complete_body(patient["_id"], "op-s02"), actor=CLINICAL)
            await db.users.update_one({"_id": vol["_id"]}, {"$set": {"team_lead_id": str(lead_b)}})
            board = await routes_reports.leaderboard(actor=ADMIN)
            leads = {x["id"]: x for x in board["team_leads"]}
            assert leads[str(lead_a)]["completed"] == 1
            assert leads.get(str(lead_b), {}).get("completed", 0) == 0
        run_camp(monkeypatch, run)

    def test_s03_self_registration_no_staff_point(self, monkeypatch):
        async def run(db):
            await _ensure_user(db, VOLUNTEER)
            await _ensure_user(db, CLINICAL)
            camp_id, day_id = await _seed_camp(db)
            pid = ObjectId()
            await db.patients.insert_one(patient_doc(
                _id=pid, camp_id=camp_id, camp_day_id=day_id,
                full_name="Self Pat", created_by=None, is_self_registered=True,
                arrived_at=NOW, printed_at=NOW,
                queue_status="arrived", clinical_generation=0,
                committed_revision_id=None,
            ))
            await complete_prescription(_complete_body(pid, "op-s03"), actor=CLINICAL)
            board = await routes_reports.leaderboard(actor=VOLUNTEER)
            for row in board["volunteers"]:
                assert row["completed"] == 0
        run_camp(monkeypatch, run)

    def test_s04_point_follows_valid_completion(self, monkeypatch):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)
            done = await complete_prescription(_complete_body(patient["_id"], "op-s04"), actor=CLINICAL)
            board = await routes_reports.leaderboard(actor=VOLUNTEER)
            vol = next(v for v in board["volunteers"] if v["id"] == str(VOLUNTEER["_id"]))
            assert vol["completed"] == 1
            await undo_completion(
                UndoCompletionBody(
                    patient_id=str(patient["_id"]),
                    expected_generation=done["registration"]["clinical_generation"],
                    reason="undo",
                    operation_id="op-s04-undo",
                ),
                actor=CLINICAL,
            )
            board = await routes_reports.leaderboard(actor=VOLUNTEER)
            vol = next(v for v in board["volunteers"] if v["id"] == str(VOLUNTEER["_id"]))
            assert vol["completed"] == 0
            await complete_prescription(
                _complete_body(patient["_id"], "op-s04-b", expected_generation=2),
                actor=CLINICAL,
            )
            board = await routes_reports.leaderboard(actor=VOLUNTEER)
            vol = next(v for v in board["volunteers"] if v["id"] == str(VOLUNTEER["_id"]))
            assert vol["completed"] == 1
        run_camp(monkeypatch, run)

    def test_s05_shared_mobile_not_collapsed(self, monkeypatch):
        async def run(db):
            camp_id, day_id = await _seed_camp(db)
            a = await register(day_id, actor=VOLUNTEER, full_name="One", age=40, phone="9876500066")
            b = await register(day_id, actor=VOLUNTEER, full_name="Two", age=41, phone="9876500066")
            assert a["id"] != b["id"]
        run_camp(monkeypatch, run)

    def test_m01_self_register_requires_mobile(self, monkeypatch):
        async def run(db):
            _camp, day_id = await _seed_camp(db)
            with pytest.raises(HTTPException) as exc:
                await _create_registration(
                    RegisterBody(full_name="No Phone", age=40, camp_day_id=str(day_id)),
                    None, True, Request(),
                )
            assert exc.value.status_code == 400
        run_camp(monkeypatch, run)

    def test_m02_reminder_includes_aadhaar_hindi(self, monkeypatch):
        text = sms.REGISTRATION_CONFIRMATION + sms.CAMP_REMINDER
        assert "कृपया शिविर के दिन अपना आधार कार्ड अवश्य साथ लाएँ।" in sms.REGISTRATION_CONFIRMATION
        assert "कृपया शिविर के दिन अपना आधार कार्ड अवश्य साथ लाएँ।" in sms.CAMP_REMINDER
        assert "{date}" in sms.CAMP_REMINDER
        assert "{venue}" in sms.CAMP_REMINDER
        assert "{reg_no}" in sms.REGISTRATION_CONFIRMATION
        assert text
