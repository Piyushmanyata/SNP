"""Arrival, camp-day scan resolution, per-patient SMS and Fulfilment gates.

In-process seam: the routers are driven directly against a mock database with the
outbound DLT send replaced by a recorder.
"""
import asyncio
import os
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "snp_test")
os.environ.setdefault("AADHAAR_HASH_PEPPER", "test-pepper")

import pytest
from bson import ObjectId
from fastapi import HTTPException

import helpers
import msg91
import routes_desk
import sms
from models import FulfilmentBody, RegisterBody, ScanBody, ScanConfirmBody
from routes_clinical import record_fulfilment
from routes_desk import arrive, mark_seen, print_prescription, scan, scan_confirm
from routes_registration import desk_register
from test_adversarial_challenger import MockDB, setup_mock_db

TODAY = "2026-09-01"
OTHER_DAY = "2026-09-03"
ACTOR = {"_id": ObjectId(), "role": "volunteer"}
CARD = "AADHAAR|Sunita Devi|F|1975-06-14|123456781234|12 Station Road Sikar"
OTHER_CARD = "AADHAAR|Ram Prasad|M|1968-01-09|999988887777|4 Mill Lane Sikar"
RX = {"r_sph": "-1.00", "l_sph": "-1.25", "add": "+2.00"}


class _Request:
    client = None


def _mock(monkeypatch):
    mock_db = setup_mock_db(monkeypatch)
    monkeypatch.setattr(routes_desk, "get_db", lambda: mock_db)
    monkeypatch.setattr(sms, "get_db", lambda: mock_db, raising=False)
    monkeypatch.setattr(helpers, "today_ist_str", lambda: TODAY)
    monkeypatch.setattr(routes_desk, "today_ist_str", lambda: TODAY)
    return mock_db


def _recorder(monkeypatch):
    sent = []

    def fake_send(message_type, mobile, reg_no, event_date, venue):
        sent.append({"type": message_type, "mobile": mobile, "reg_no": reg_no,
                     "date": event_date, "venue": venue})
        return f"id-{len(sent)}"

    monkeypatch.setattr(msg91, "send_dlt_sms", fake_send)
    monkeypatch.setattr(sms.msg91, "send_dlt_sms", fake_send)
    monkeypatch.setattr(sms.msg91, "configured", lambda: True)
    return sent


async def _seed_camp(mock_db, days=(TODAY,)):
    camp_id = ObjectId()
    await mock_db.camps.insert_one({
        "_id": camp_id, "name": "Sikar Camp", "venue": "Sikar Bhawan", "is_active": True,
    })
    day_ids = []
    for date in days:
        day_id = ObjectId()
        await mock_db.camp_days.insert_one({
            "_id": day_id, "camp_id": camp_id, "day_date": date,
            "seat_limit": 50, "printing_open": True,
        })
        day_ids.append(day_id)
    return camp_id, day_ids


async def _register(day_id, **fields):
    body = RegisterBody(
        full_name=fields.pop("full_name", "Sunita Devi"),
        age=fields.pop("age", 51),
        phone=fields.pop("phone", "9876500001"),
        camp_day_id=str(day_id),
        **fields,
    )
    result = await desk_register(body, _Request(), actor=ACTOR)
    return result["registration"]


# --------------------------------------------------------------------------
# Arrival
# --------------------------------------------------------------------------

class TestArrival:
    def test_a_booking_cannot_print(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _camp_id, (day_id,) = await _seed_camp(mock_db)
            reg = await _register(day_id, manual_entry=True)
            with pytest.raises(HTTPException) as exc:
                await print_prescription(reg["id"], actor=ACTOR)
            assert exc.value.status_code == 409
            assert exc.value.detail["code"] == "NOT_ARRIVED"
        asyncio.run(run())

    def test_arrival_then_print_then_seen(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _camp_id, (day_id,) = await _seed_camp(mock_db)
            reg = await _register(day_id, manual_entry=True)
            arrived = (await arrive(reg["id"], actor=ACTOR))["registration"]
            assert arrived["queue_status"] == "arrived"
            assert arrived["arrived_at"]
            await print_prescription(reg["id"], actor=ACTOR)
            seen = (await mark_seen(reg["id"], actor=ACTOR))["registration"]
            assert seen["queue_status"] == "seen"
        asyncio.run(run())

    def test_seen_is_unreachable_without_arrival(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _camp_id, (day_id,) = await _seed_camp(mock_db)
            reg = await _register(day_id, manual_entry=True)
            await mock_db.patients.update_one(
                {"_id": ObjectId(reg["id"])}, {"$set": {"printed_at": helpers.now_utc()}}
            )
            with pytest.raises(HTTPException) as exc:
                await mark_seen(reg["id"], actor=ACTOR)
            assert exc.value.detail["code"] == "NOT_ARRIVED"
        asyncio.run(run())

    def test_arrival_is_stamped_once(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _camp_id, (day_id,) = await _seed_camp(mock_db)
            reg = await _register(day_id, manual_entry=True)
            first = (await arrive(reg["id"], actor=ACTOR))["registration"]["arrived_at"]
            second = (await arrive(reg["id"], actor=ACTOR))["registration"]["arrived_at"]
            assert first == second
        asyncio.run(run())

    def test_a_no_show_keeps_an_empty_arrival(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _camp_id, (day_id,) = await _seed_camp(mock_db)
            reg = await _register(day_id, manual_entry=True)
            assert reg["arrived_at"] is None
        asyncio.run(run())


# --------------------------------------------------------------------------
# Camp-day scan resolution
# --------------------------------------------------------------------------

class TestScanResolution:
    def test_scan_with_aadhaar_on_file_checks_the_patient_in(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _camp_id, (day_id,) = await _seed_camp(mock_db)
            reg = await _register(
                day_id, full_name="Sunita Devi", gender="F", dob="1975-06-14",
                aadhaar_last4="1234", aadhaar_scanned=True,
            )
            out = await scan(ScanBody(payload=CARD), actor=ACTOR)
            assert out["outcome"] == "arrived"
            assert out["registration"]["reg_no"] == reg["reg_no"]
            assert out["registration"]["arrived_at"]
        asyncio.run(run())

    def test_a_known_person_is_matched_even_when_the_stored_name_differs(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _camp_id, (day_id,) = await _seed_camp(mock_db)
            reg = await _register(
                day_id, full_name="Sunita Devi", gender="F", dob="1975-06-14",
                aadhaar_last4="1234", aadhaar_scanned=True,
            )
            # A later correction changes the spelling; only the Person still ties them to the card.
            await mock_db.patients.update_one(
                {"_id": ObjectId(reg["id"])},
                {"$set": {"full_name": "S Devi", "full_name_normalized": "s devi",
                          "aadhaar_last4": None}},
            )
            out = await scan(ScanBody(payload=CARD), actor=ACTOR)
            assert out["outcome"] == "arrived"
            assert out["registration"]["reg_no"] == reg["reg_no"]
        asyncio.run(run())

    def test_scan_on_a_manual_entry_returns_a_diff_and_mutates_nothing(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _camp_id, (day_id,) = await _seed_camp(mock_db)
            reg = await _register(
                day_id, full_name="Sunita Devi", age=48, aadhaar_last4="1234",
                dob="1975-06-14", manual_entry=True,
            )
            out = await scan(ScanBody(payload=CARD), actor=ACTOR)
            assert out["outcome"] == "mismatch_review"
            assert out["registration"]["reg_no"] == reg["reg_no"]
            assert out["card"]["full_name"] == "Sunita Devi"
            assert {d["field"] for d in out["diff"]} >= {"age", "gender", "address"}
            stored = await mock_db.patients.find_one({"_id": ObjectId(reg["id"])})
            assert stored["age"] == 48
            assert stored["arrived_at"] is None
            assert stored["manual_entry"] is True
        asyncio.run(run())

    def test_confirming_review_overwrites_identity_and_keeps_the_booking(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _camp_id, (day_id,) = await _seed_camp(mock_db)
            reg = await _register(
                day_id, full_name="Sunita Devi", age=48, phone="9876500001",
                aadhaar_last4="1234", dob="1975-06-14", manual_entry=True,
            )
            out = await scan_confirm(
                ScanConfirmBody(patient_id=reg["id"], payload=CARD), actor=ACTOR
            )
            assert out["outcome"] == "arrived"
            after = out["registration"]
            assert after["reg_no"] == reg["reg_no"]
            assert after["phone"] == "9876500001"
            assert after["camp_day_id"] == str(day_id)
            assert after["age"] == helpers.age_from_dob("1975-06-14")
            assert after["gender"] == "F"
            assert after["address"] == "12 Station Road Sikar"
            assert after["manual_entry"] is False
            assert after["arrived_at"]
        asyncio.run(run())

    def test_confirming_a_registration_that_is_not_manual_is_refused(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _camp_id, (day_id,) = await _seed_camp(mock_db)
            reg = await _register(
                day_id, full_name="Sunita Devi", gender="F", dob="1975-06-14",
                aadhaar_last4="1234", aadhaar_scanned=True,
            )
            with pytest.raises(HTTPException) as exc:
                await scan_confirm(
                    ScanConfirmBody(patient_id=reg["id"], payload=CARD), actor=ACTOR
                )
            assert exc.value.detail["code"] == "NOT_A_MANUAL_ENTRY"
        asyncio.run(run())

    def test_a_scan_matching_nothing_registers_nobody(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            await _seed_camp(mock_db)
            out = await scan(ScanBody(payload=OTHER_CARD), actor=ACTOR)
            assert out["outcome"] == "no_match"
            assert out["card"]["full_name"] == "Ram Prasad"
            assert mock_db.patients.docs == []
        asyncio.run(run())

    def test_two_manual_matches_are_ambiguous_and_listed(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            camp_id, (day_id,) = await _seed_camp(mock_db)
            a = await _register(day_id, full_name="Sunita Devi", age=48,
                                aadhaar_last4="1234", dob="1975-06-14", manual_entry=True)
            # A second typed row for the same card can only arrive by repair or import.
            await mock_db.patients.insert_one({
                "_id": ObjectId(), "camp_id": camp_id, "camp_day_id": day_id, "reg_no": 999,
                "full_name": "Sunita Devi", "full_name_normalized": "sunita devi",
                "age": 49, "phone": "9876500002", "phone_normalized": "9876500002",
                "aadhaar_last4": "1234", "dob": "1975-06-14", "aadhaar_scanned": False,
                "manual_entry": True, "queue_status": "registered", "arrived_at": None,
                "patient_qr": "dup-qr",
            })
            out = await scan(ScanBody(payload=CARD), actor=ACTOR)
            assert out["outcome"] == "ambiguous"
            assert {r["reg_no"] for r in out["registrations"]} == {a["reg_no"], 999}
        asyncio.run(run())

    def test_an_unreadable_scan_is_refused(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            await _seed_camp(mock_db)
            with pytest.raises(HTTPException) as exc:
                await scan(ScanBody(payload="not a card at all"), actor=ACTOR)
            assert exc.value.status_code == 400
            assert exc.value.detail["code"] == "NOT_A_CARD"
        asyncio.run(run())

    def test_arriving_on_the_wrong_day_checks_in_on_the_day_they_came(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _camp_id, (today_id, other_id) = await _seed_camp(mock_db, days=(TODAY, OTHER_DAY))
            reg = await _register(
                other_id, full_name="Sunita Devi", gender="F", dob="1975-06-14",
                aadhaar_last4="1234", aadhaar_scanned=True,
            )
            out = await scan(ScanBody(payload=CARD), actor=ACTOR)
            assert out["outcome"] == "arrived"
            assert out["registration"]["camp_day_id"] == str(today_id)
            assert out["registration"]["camp_day_changed_from"] == OTHER_DAY
            assert out["registration"]["reg_no"] == reg["reg_no"]
        asyncio.run(run())

    def test_camp_day_capacity_refuses_registration_but_not_arrival(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            camp_id, (day_id,) = await _seed_camp(mock_db)
            await mock_db.camp_days.update_one({"_id": day_id}, {"$set": {"seat_limit": 1}})
            first = await _register(
                day_id, full_name="Sunita Devi", gender="F", dob="1975-06-14",
                aadhaar_last4="1234", aadhaar_scanned=True,
            )
            with pytest.raises(HTTPException) as exc:
                await _register(day_id, full_name="Ram Prasad", phone="9876500009",
                                manual_entry=True)
            assert exc.value.detail["code"] == "CAMP_DAY_FULL"
            out = await scan(ScanBody(payload=CARD), actor=ACTOR)
            assert out["outcome"] == "arrived"
            assert out["registration"]["reg_no"] == first["reg_no"]
        asyncio.run(run())


# --------------------------------------------------------------------------
# Per-patient SMS
# --------------------------------------------------------------------------

class TestRegistrationConfirmationSms:
    def test_each_registration_gets_its_own_reg_no_message(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            sent = _recorder(monkeypatch)
            _camp_id, (day_id,) = await _seed_camp(mock_db)
            a = await _register(day_id, full_name="Sunita Devi", manual_entry=True)
            b = await _register(day_id, full_name="Ram Prasad", manual_entry=True)
            assert [s["type"] for s in sent] == ["registration", "registration"]
            assert [s["reg_no"] for s in sent] == [a["reg_no"], b["reg_no"]]
            assert {s["mobile"] for s in sent} == {"9876500001"}
            assert {s["date"] for s in sent} == {TODAY}
            assert {s["venue"] for s in sent} == {"Sikar Bhawan"}
        asyncio.run(run())

    def test_a_send_failure_does_not_fail_the_registration(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _recorder(monkeypatch)

            def boom(*_a, **_k):
                raise RuntimeError("gateway down")

            monkeypatch.setattr(sms.msg91, "send_dlt_sms", boom)
            _camp_id, (day_id,) = await _seed_camp(mock_db)
            reg = await _register(day_id, manual_entry=True)
            assert reg["reg_no"]
            row = mock_db.reminder_ledger.docs[0]
            assert row["message_type"] == "registration"
            assert row["status"] == "failed"
        asyncio.run(run())

    def test_a_patient_with_no_usable_number_is_skipped(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            sent = _recorder(monkeypatch)
            _camp_id, (day_id,) = await _seed_camp(mock_db)
            body = RegisterBody(full_name="Sunita Devi", age=51, phone="9876500001",
                                camp_day_id=str(day_id), manual_entry=True)
            result = await desk_register(body, _Request(), actor=ACTOR)
            await mock_db.patients.update_one(
                {"_id": ObjectId(result["registration"]["id"])},
                {"$set": {"phone_normalized": None, "phone": None}},
            )
            sent.clear()
            mock_db.reminder_ledger.docs.clear()
            await sms.send_patient_sms(
                mock_db,
                await mock_db.patients.find_one({"_id": ObjectId(result["registration"]["id"])}),
                "camp", TODAY, "Sikar Bhawan",
            )
            assert sent == []
            assert mock_db.reminder_ledger.docs == []
        asyncio.run(run())


# --------------------------------------------------------------------------
# Fulfilment lines
# --------------------------------------------------------------------------

async def _seen_patient_with_transcription(mock_db, measurements=None):
    patient_id = ObjectId()
    trans_id = ObjectId()
    camp_id = ObjectId()
    await mock_db.patients.insert_one({
        "_id": patient_id, "camp_id": camp_id, "camp_day_id": ObjectId(), "reg_no": 501,
        "phone": "9876500001", "phone_normalized": "9876500001",
        "queue_status": "seen", "arrived_at": helpers.now_utc(),
        "printed_at": helpers.now_utc(), "seen_at": helpers.now_utc(),
    })
    await mock_db.transcriptions.insert_one({
        "_id": trans_id, "patient_id": patient_id, "camp_id": camp_id,
        "locked": False, "specs_measurements": measurements,
    })
    return camp_id, patient_id, trans_id


class TestFulfilmentLines:
    def test_fixed_power_specs_needs_the_prescribed_power(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _camp_id, _pid, trans_id = await _seen_patient_with_transcription(mock_db)
            body = FulfilmentBody(transcription_id=str(trans_id), item_type="specs",
                                  status="fulfilled")
            with pytest.raises(HTTPException) as exc:
                await record_fulfilment(body, actor=ACTOR)
            assert exc.value.status_code == 400
            assert exc.value.detail["code"] == "SPECS_MEASUREMENTS_REQUIRED"
        asyncio.run(run())

    def test_fixed_power_specs_records_without_token_or_sms(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            sent = _recorder(monkeypatch)
            _camp_id, _pid, trans_id = await _seen_patient_with_transcription(mock_db, RX)
            body = FulfilmentBody(transcription_id=str(trans_id), item_type="specs",
                                  status="fulfilled")
            out = await record_fulfilment(body, actor=ACTOR)
            assert out["fulfilment"]["status"] == "fulfilled"
            assert out["slip"] is None
            assert sent == []
        asyncio.run(run())

    def test_medicine_is_unaffected_by_the_measurement_rule(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _camp_id, _pid, trans_id = await _seen_patient_with_transcription(mock_db)
            body = FulfilmentBody(transcription_id=str(trans_id), item_type="medicine",
                                  status="fulfilled")
            out = await record_fulfilment(body, actor=ACTOR)
            assert out["fulfilment"]["status"] == "fulfilled"
        asyncio.run(run())

    def test_deferring_specs_prints_a_token_and_sends_one_sms(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            sent = _recorder(monkeypatch)
            camp_id, _pid, trans_id = await _seen_patient_with_transcription(mock_db, RX)
            specs_day = ObjectId()
            await mock_db.specs_collection_days.insert_one({
                "_id": specs_day, "camp_id": camp_id, "day_date": "2026-09-20",
                "venue": "Optical Desk", "seat_limit": 2, "seats_taken": 0,
            })
            body = FulfilmentBody(transcription_id=str(trans_id), item_type="specs",
                                  status="deferred", specs_collection_day_id=str(specs_day))
            out = await record_fulfilment(body, actor=ACTOR)
            assert out["slip"]["collection_date"] == "2026-09-20"
            assert sent == [{"type": "specs_token", "mobile": "9876500001", "reg_no": 501,
                             "date": "2026-09-20", "venue": "Optical Desk"}]
        asyncio.run(run())

    def test_deferring_ot_sends_the_ot_token_sms(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            sent = _recorder(monkeypatch)
            camp_id, _pid, trans_id = await _seen_patient_with_transcription(mock_db, RX)
            ot_day = ObjectId()
            await mock_db.ot_schedule_days.insert_one({
                "_id": ot_day, "camp_id": camp_id, "day_date": "2026-10-02",
                "venue": "OT Theatre", "seat_limit": 1, "seats_taken": 0,
            })
            body = FulfilmentBody(transcription_id=str(trans_id), item_type="ot",
                                  status="deferred", ot_schedule_day_id=str(ot_day))
            await record_fulfilment(body, actor=ACTOR)
            assert sent == [{"type": "ot_token", "mobile": "9876500001", "reg_no": 501,
                             "date": "2026-10-02", "venue": "OT Theatre"}]
        asyncio.run(run())

    def test_every_day_full_names_the_admin_action(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            camp_id, _pid, trans_id = await _seen_patient_with_transcription(mock_db, RX)
            full_day = ObjectId()
            await mock_db.ot_schedule_days.insert_one({
                "_id": full_day, "camp_id": camp_id, "day_date": "2026-10-02",
                "venue": "OT Theatre", "seat_limit": 1, "seats_taken": 1,
            })
            body = FulfilmentBody(transcription_id=str(trans_id), item_type="ot",
                                  status="deferred", ot_schedule_day_id=str(full_day))
            with pytest.raises(HTTPException) as exc:
                await record_fulfilment(body, actor=ACTOR)
            assert exc.value.detail["code"] == "NO_CLINICAL_DAY_AVAILABLE"
            assert "Call the admin" in exc.value.detail["message"]
        asyncio.run(run())

    def test_one_full_day_while_another_is_free_is_a_plain_refusal(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            camp_id, _pid, trans_id = await _seen_patient_with_transcription(mock_db, RX)
            full_day, free_day = ObjectId(), ObjectId()
            await mock_db.ot_schedule_days.insert_one({
                "_id": full_day, "camp_id": camp_id, "day_date": "2026-10-02",
                "venue": "OT Theatre", "seat_limit": 1, "seats_taken": 1,
            })
            await mock_db.ot_schedule_days.insert_one({
                "_id": free_day, "camp_id": camp_id, "day_date": "2026-10-09",
                "venue": "OT Theatre", "seat_limit": 1, "seats_taken": 0,
            })
            body = FulfilmentBody(transcription_id=str(trans_id), item_type="ot",
                                  status="deferred", ot_schedule_day_id=str(full_day))
            with pytest.raises(HTTPException) as exc:
                await record_fulfilment(body, actor=ACTOR)
            assert exc.value.detail == "OT day is full or not found"
        asyncio.run(run())


def test_mock_db_is_isolated_per_test():
    assert isinstance(MockDB(), MockDB)
