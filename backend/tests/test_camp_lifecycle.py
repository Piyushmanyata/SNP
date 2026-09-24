"""Arrival, camp-day scan resolution, per-patient SMS and Fulfilment gates.

In-process seam: the routers are driven directly against a real per-test database with the
outbound DLT send replaced by a recorder.
"""
import pytest
from bson import ObjectId
from fastapi import HTTPException
from pydantic import ValidationError

import helpers
import routes_camps
import sms
from models import CampBody, CompletePrescriptionBody, ScanBody, ScanConfirmBody
from routes_clinical import complete_prescription, record_fulfilment
from routes_desk import arrive, print_prescription, scan, scan_confirm
from routes_registration import name_search
from seed import (
    ACTOR, CARD, CLINICAL, FIXED_POWER, MEDICINE, MEDICINE_ALT, OTHER_CARD, OTHER_DAY, TODAY,
    day, fulfil, recorder, register, run_camp, seed_camp, seen_patient,
)


def _dmy(iso):
    return "-".join(reversed(iso.split("-")))


class TestArrival:
    def test_a_booking_cannot_print(self, monkeypatch):
        async def body(database):
            _camp_id, (day_id,) = await seed_camp(database)
            reg = await register(day_id, manual_entry=True)
            with pytest.raises(HTTPException) as exc:
                await print_prescription(reg["id"], actor=ACTOR)
            assert exc.value.status_code == 409
            assert exc.value.detail["code"] == "NOT_ARRIVED"
        run_camp(monkeypatch, body)

    def test_a_day_that_received_an_arrival_cannot_be_deleted(self, monkeypatch):
        async def body(database):
            _camp_id, (booked_day, operating_day) = await seed_camp(database, days=(OTHER_DAY, TODAY))
            reg = await register(booked_day, aadhaar_scanned=True, qr_payload=CARD)
            await arrive(reg["id"], actor=ACTOR)
            stored = await database.patients.find_one({"_id": ObjectId(reg["id"])})
            assert stored["camp_day_id"] == operating_day
            with pytest.raises(HTTPException) as exc:
                await routes_camps.delete_day(str(operating_day), actor=ACTOR)
            assert exc.value.status_code == 409
            assert await database.camp_days.find_one({"_id": operating_day})
        run_camp(monkeypatch, body)

    def test_arrival_then_print_then_seen(self, monkeypatch):
        async def body(database):
            _camp_id, (day_id,) = await seed_camp(database)
            reg = await register(day_id, aadhaar_scanned=True, qr_payload=CARD)
            arrived = (await arrive(reg["id"], actor=ACTOR))["registration"]
            assert arrived["queue_status"] == "arrived"
            assert arrived["arrived_at"]
            await print_prescription(reg["id"], actor=ACTOR)
            done = await complete_prescription(
                CompletePrescriptionBody(
                    patient_id=reg["id"],
                    full_transcription_confirmed=True,
                    none_prescribed=True,
                    operation_id="op-lifecycle-complete",
                    remarks="observe",
                ),
                actor=CLINICAL,
            )
            assert done["registration"]["queue_status"] == "seen"
        run_camp(monkeypatch, body)

    def test_arrival_is_stamped_once(self, monkeypatch):
        async def body(database):
            _camp_id, (day_id,) = await seed_camp(database)
            reg = await register(day_id, aadhaar_scanned=True, qr_payload=CARD)
            first = (await arrive(reg["id"], actor=ACTOR))["registration"]["arrived_at"]
            second = (await arrive(reg["id"], actor=ACTOR))["registration"]["arrived_at"]
            assert first == second
        run_camp(monkeypatch, body)

    def test_a_no_show_keeps_an_empty_arrival(self, monkeypatch):
        async def body(database):
            _camp_id, (day_id,) = await seed_camp(database)
            reg = await register(day_id, manual_entry=True)
            assert reg["arrived_at"] is None
        run_camp(monkeypatch, body)


class TestScanResolution:
    def test_scan_with_aadhaar_on_file_checks_the_patient_in(self, monkeypatch):
        async def body(database):
            _camp_id, (day_id,) = await seed_camp(database)
            reg = await register(
                day_id, full_name="Sunita Devi", gender="F", dob="1975-06-14",
                aadhaar_last4="1234", aadhaar_scanned=True,
            )
            out = await scan(ScanBody(payload=CARD), actor=ACTOR)
            assert out["outcome"] == "arrived"
            assert out["registration"]["reg_no"] == reg["reg_no"]
            assert out["registration"]["arrived_at"]
        run_camp(monkeypatch, body)

    def test_a_known_person_is_matched_even_when_the_stored_name_differs(self, monkeypatch):
        async def body(database):
            _camp_id, (day_id,) = await seed_camp(database)
            reg = await register(
                day_id, full_name="Sunita Devi", gender="F", dob="1975-06-14",
                aadhaar_last4="1234", aadhaar_scanned=True,
            )
            await database.patients.update_one(
                {"_id": ObjectId(reg["id"])},
                {"$set": {"full_name": "S Devi", "full_name_normalized": "s devi", "aadhaar_last4": None}},
            )
            out = await scan(ScanBody(payload=CARD), actor=ACTOR)
            assert out["outcome"] == "arrived"
            assert out["registration"]["reg_no"] == reg["reg_no"]
        run_camp(monkeypatch, body)

    def test_scan_on_a_manual_entry_returns_a_diff_and_mutates_nothing(self, monkeypatch):
        async def body(database):
            _camp_id, (day_id,) = await seed_camp(database)
            reg = await register(
                day_id, full_name="Sunita Devi", age=48, aadhaar_last4="1234",
                dob="1975-06-14", gender="M", manual_entry=True,
            )
            out = await scan(ScanBody(payload=CARD), actor=ACTOR)
            assert out["outcome"] == "mismatch_review"
            assert out["registration"]["reg_no"] == reg["reg_no"]
            assert out["card"]["full_name"] == "Sunita Devi"
            assert {d["field"] for d in out["diff"]} == {"age", "gender"}
            assert "address" not in {d["field"] for d in out["diff"]}
            stored = await database.patients.find_one({"_id": ObjectId(reg["id"])})
            assert stored["age"] == 48
            assert stored["arrived_at"] is None
            assert stored["manual_entry"] is True
        run_camp(monkeypatch, body)

    def test_confirming_review_overwrites_identity_and_keeps_the_booking(self, monkeypatch):
        async def body(database):
            _camp_id, (day_id,) = await seed_camp(database)
            reg = await register(
                day_id, full_name="Sunita Devi", age=48, phone="9876500001",
                aadhaar_last4="1234", dob="1975-06-14", manual_entry=True,
            )
            out = await scan_confirm(ScanConfirmBody(patient_id=reg["id"], payload=CARD), actor=ACTOR)
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
        run_camp(monkeypatch, body)

    def test_confirming_a_scanned_registration_arrives_it_without_an_overwrite(self, monkeypatch):
        async def body(database):
            _camp_id, (day_id,) = await seed_camp(database)
            reg = await register(
                day_id, full_name="Sunita Devi", gender="F", dob="1975-06-14",
                aadhaar_last4="1234", aadhaar_scanned=True,
            )
            out = await scan_confirm(ScanConfirmBody(patient_id=reg["id"], payload=CARD), actor=ACTOR)
            assert out["outcome"] == "arrived" and out["registration"]["id"] == reg["id"]
            stored = await database.patients.find_one({"_id": ObjectId(reg["id"])})
            assert stored["arrived_at"] and stored["dob"] == "1975-06-14" and not stored.get("manual_entry")
        run_camp(monkeypatch, body)

    def test_a_scan_matching_nothing_registers_nobody(self, monkeypatch):
        async def body(database):
            await seed_camp(database)
            out = await scan(ScanBody(payload=OTHER_CARD), actor=ACTOR)
            assert out["outcome"] == "no_match"
            assert out["card"]["full_name"] == "Ram Prasad"
            assert await database.patients.count_documents({}) == 0
        run_camp(monkeypatch, body)

    def test_two_manual_matches_are_ambiguous_and_listed(self, monkeypatch):
        async def body(database):
            camp_id, (day_id,) = await seed_camp(database)
            a = await register(day_id, full_name="Sunita Devi", age=48,
                               aadhaar_last4="1234", dob="1975-06-14", manual_entry=True)
            await database.patients.insert_one({
                "camp_id": camp_id, "camp_day_id": day_id, "reg_no": 999,
                "full_name": "Sunita Devi", "full_name_normalized": "sunita devi",
                "age": 49, "phone": "9876500002", "phone_normalized": "9876500002",
                "aadhaar_last4": "1234", "dob": "1975-06-14", "aadhaar_scanned": False,
                "manual_entry": True, "queue_status": "registered", "arrived_at": None,
                "patient_qr": "dup-qr",
            })
            out = await scan(ScanBody(payload=CARD), actor=ACTOR)
            assert out["outcome"] == "ambiguous"
            assert {r["reg_no"] for r in out["registrations"]} == {a["reg_no"], 999}
        run_camp(monkeypatch, body)

    def test_an_unreadable_scan_is_refused(self, monkeypatch):
        async def body(database):
            await seed_camp(database)
            with pytest.raises(HTTPException) as exc:
                await scan(ScanBody(payload="not a card at all"), actor=ACTOR)
            assert exc.value.status_code == 400
            assert exc.value.detail["code"] == "NOT_A_CARD"
        run_camp(monkeypatch, body)

    def test_arriving_on_the_wrong_day_checks_in_on_the_day_they_came(self, monkeypatch):
        async def body(database):
            _camp_id, (today_id, other_id) = await seed_camp(database, days=(TODAY, OTHER_DAY))
            reg = await register(
                other_id, full_name="Sunita Devi", gender="F", dob="1975-06-14",
                aadhaar_last4="1234", aadhaar_scanned=True,
            )
            out = await scan(ScanBody(payload=CARD), actor=ACTOR)
            assert out["outcome"] == "arrived"
            assert out["registration"]["camp_day_id"] == str(today_id)
            assert out["registration"]["camp_day_changed_from"] == OTHER_DAY
            assert out["registration"]["reg_no"] == reg["reg_no"]
        run_camp(monkeypatch, body)

    def test_a_wrong_day_arrival_moves_no_camp_day_seat(self, monkeypatch):
        async def body(database):
            _camp_id, (today_id, other_id) = await seed_camp(database, days=(TODAY, OTHER_DAY))
            await database.camp_days.update_one({"_id": today_id}, {"$set": {"seat_limit": 1}})
            await register(today_id, full_name="Booked Today", phone="9876500007", manual_entry=True)
            await register(
                other_id, full_name="Sunita Devi", gender="F", dob="1975-06-14",
                aadhaar_last4="1234", aadhaar_scanned=True,
            )

            out = await scan(ScanBody(payload=CARD), actor=ACTOR)
            assert out["outcome"] == "arrived"
            assert out["registration"]["camp_day_id"] == str(today_id)

            assert (await database.camp_days.find_one({"_id": today_id}))["booked"] == 1
            assert (await database.camp_days.find_one({"_id": other_id}))["booked"] == 1
            assert await database.patients.count_documents({"booked_camp_day_id": other_id}) == 1
        run_camp(monkeypatch, body)

    def test_scanning_an_arrived_patient_again_does_not_move_them(self, monkeypatch):
        async def body(database):
            _camp_id, (today_id, other_id) = await seed_camp(database, days=(TODAY, OTHER_DAY))
            await register(
                other_id, full_name="Sunita Devi", gender="F", dob="1975-06-14",
                aadhaar_last4="1234", aadhaar_scanned=True,
            )
            first = await scan(ScanBody(payload=CARD), actor=ACTOR)
            second = await scan(ScanBody(payload=CARD), actor=ACTOR)

            assert second["registration"]["arrived_at"] == first["registration"]["arrived_at"]
            assert second["registration"]["camp_day_changed_from"] == OTHER_DAY
            assert second["registration"]["camp_day_id"] == str(today_id)
        run_camp(monkeypatch, body)

    def test_capacity_refuses_pre_registration_but_never_a_walk_in_or_arrival(self, monkeypatch):
        async def body(database):
            _camp_id, (day_id, other_id) = await seed_camp(database, days=(TODAY, OTHER_DAY))
            await database.camp_days.update_many({}, {"$set": {"seat_limit": 1}})
            first = await register(
                day_id, full_name="Sunita Devi", gender="F", dob="1975-06-14",
                aadhaar_last4="1234", aadhaar_scanned=True,
            )
            walk_in = await register(day_id, full_name="Ram Prasad", phone="9876500009", manual_entry=True)
            assert walk_in["reg_no"]
            today_day = await database.camp_days.find_one({"_id": day_id})
            assert today_day["booked"] == 2
            assert today_day["seat_limit"] == 1

            await register(other_id, full_name="Later One", phone="9876500010", manual_entry=True)
            with pytest.raises(HTTPException) as exc:
                await register(other_id, full_name="Later Two", phone="9876500011", manual_entry=True)
            assert exc.value.detail["code"] == "CAMP_DAY_FULL"

            out = await scan(ScanBody(payload=CARD), actor=ACTOR)
            assert out["outcome"] == "arrived"
            assert out["registration"]["reg_no"] == first["reg_no"]
        run_camp(monkeypatch, body)


class TestRegistrationConfirmationSms:
    def test_each_registration_gets_its_own_reg_no_message(self, monkeypatch):
        sent = recorder(monkeypatch)

        async def body(database):
            _camp_id, (day_id,) = await seed_camp(database, days=(OTHER_DAY,), venue_sms="Short Camp Venue")
            a = await register(day_id, full_name="Sunita Devi", manual_entry=True)
            b = await register(day_id, full_name="Ram Prasad", manual_entry=True)
            assert [s["type"] for s in sent] == ["registration", "registration"]
            assert [s["reg_no"] for s in sent] == [a["reg_no"], b["reg_no"]]
            assert {s["mobile"] for s in sent} == {"9876500001"}
            assert {s["date"] for s in sent} == {_dmy(OTHER_DAY)}
            assert {s["venue"] for s in sent} == {"Short Camp Venue"}
        run_camp(monkeypatch, body)

    def test_camp_sms_venue_is_saved_and_follows_the_sms_venue_rule(self, monkeypatch):
        async def body(database):
            created = await routes_camps.create_camp(
                CampBody(name="Camp", venue="A" * 64, venue_sms="Short Venue", camp_date=OTHER_DAY),
                actor=ACTOR,
            )
            assert created["camp"]["venue_sms"] == "Short Venue"
            changed = await routes_camps.update_camp(
                created["camp"]["id"],
                CampBody(name="Camp", venue="A" * 64, venue_sms="Another Venue", camp_date=OTHER_DAY),
                actor=ACTOR,
            )
            assert changed["camp"]["venue_sms"] == "Another Venue"
            stored = await database.camps.find_one({"_id": ObjectId(created["camp"]["id"])})
            assert stored["venue_sms"] == "Another Venue"

        run_camp(monkeypatch, body)
        for venue_sms in ("X" * 31, None, "  ", "NA", "N/A", "Hall 98765 43210", "www.snp.in"):
            with pytest.raises(ValidationError):
                CampBody(name="Camp", venue="A" * 64, venue_sms=venue_sms, camp_date=OTHER_DAY)
        assert CampBody(name="Camp", venue="A" * 64, venue_sms="  Hansa   Garden ", camp_date=OTHER_DAY).venue_sms == "Hansa Garden"
        assert CampBody(name="Camp", venue="Sikar Bhawan", camp_date=OTHER_DAY).venue_sms is None
        with pytest.raises(ValidationError):
            CampBody(name="Camp", venue="Sikar Bhawan, call 9876543210", camp_date=OTHER_DAY)

    def test_a_send_failure_does_not_fail_the_registration(self, monkeypatch):
        recorder(monkeypatch)

        def boom(*_a, **_k):
            raise sms.msg91.Unsent("gateway down")

        monkeypatch.setattr(sms.msg91, "send_dlt_sms", boom)

        async def body(database):
            _camp_id, (day_id,) = await seed_camp(database, days=(OTHER_DAY,))
            reg = await register(day_id, manual_entry=True)
            assert reg["reg_no"]
            row = await database.reminder_ledger.find_one({})
            assert row["message_type"] == "registration"
            assert row["status"] == "failed"
        run_camp(monkeypatch, body)

    def test_a_walk_in_registered_on_the_camp_day_gets_no_sms(self, monkeypatch):
        sent = recorder(monkeypatch)

        async def body(database):
            _camp_id, (today_id, later_id) = await seed_camp(database, days=(TODAY, OTHER_DAY))
            await register(today_id, full_name="Sunita Devi", manual_entry=True)
            assert sent == []
            assert await database.reminder_ledger.count_documents({}) == 0
            await register(later_id, full_name="Ram Prasad", manual_entry=True)
            assert [s["type"] for s in sent] == ["registration"]
            assert sent[0]["date"] == _dmy(OTHER_DAY)
        run_camp(monkeypatch, body)

    def test_a_patient_with_no_usable_number_is_skipped(self, monkeypatch):
        sent = recorder(monkeypatch)

        async def body(database):
            _camp_id, (day_id,) = await seed_camp(database)
            reg = await register(day_id, manual_entry=True)
            await database.patients.update_one(
                {"_id": ObjectId(reg["id"])}, {"$set": {"phone_normalized": None, "phone": None}},
            )
            sent.clear()
            await database.reminder_ledger.delete_many({})
            await sms.send_patient_sms(
                database, await database.patients.find_one({"_id": ObjectId(reg["id"])}),
                "camp", TODAY, "Sikar Bhawan",
            )
            assert sent == []
            assert await database.reminder_ledger.count_documents({}) == 0
        run_camp(monkeypatch, body)


class TestFulfilmentLines:
    def test_fixed_power_specs_needs_the_prescribed_power(self, monkeypatch):
        async def body(database):
            seen = await seen_patient(database, measurements=None, fixed_power=None)
            with pytest.raises(HTTPException) as exc:
                await record_fulfilment(
                    fulfil(seen["trans_id"], seen["rev_id"], item_type="specs_fixed", status="fulfilled"),
                    actor=CLINICAL, background_tasks=None,
                )
            assert exc.value.status_code == 400
            assert exc.value.detail["code"] == "FIXED_POWER_REQUIRED"
        run_camp(monkeypatch, body)

    def test_fixed_power_specs_records_without_token_or_sms(self, monkeypatch):
        sent = recorder(monkeypatch)

        async def body(database):
            seen = await seen_patient(database)
            out = await record_fulfilment(
                fulfil(seen["trans_id"], seen["rev_id"], item_type="specs_fixed", status="fulfilled"),
                actor=CLINICAL, background_tasks=None,
            )
            assert out["fulfilment"]["status"] == "fulfilled"
            assert out["fulfilment"]["issued_power_r"] == FIXED_POWER
            assert out["slip"] is None
            assert sent == []
        run_camp(monkeypatch, body)

    def test_a_power_that_ran_out_is_substituted_and_both_powers_are_kept(self, monkeypatch):
        async def body(database):
            seen = await seen_patient(database)
            out = await record_fulfilment(fulfil(
                seen["trans_id"], seen["rev_id"], item_type="specs_fixed", status="fulfilled",
                issued_power_r=2.25, issued_power_l=2.25,
            ), actor=CLINICAL, background_tasks=None)
            assert out["fulfilment"]["issued_power_r"] == 2.25
            rev = await database.prescription_revisions.find_one({"_id": seen["rev_id"]})
            assert rev["fixed_power_r"] == FIXED_POWER
        run_camp(monkeypatch, body)

    def test_a_substituted_power_the_camp_does_not_stock_is_refused(self, monkeypatch):
        async def body(database):
            seen = await seen_patient(database)
            with pytest.raises(HTTPException) as exc:
                await record_fulfilment(fulfil(
                    seen["trans_id"], seen["rev_id"], item_type="specs_fixed", status="fulfilled",
                    issued_power_r=9.75, issued_power_l=9.75,
                ), actor=CLINICAL, background_tasks=None)
            assert exc.value.detail["code"] == "UNKNOWN_POWER"
        run_camp(monkeypatch, body)

    def test_medicine_outcomes_derive_the_line_status(self, monkeypatch):
        async def body(database):
            seen = await seen_patient(database, fixed_power=None)
            await database.prescription_revisions.update_one(
                {"_id": seen["rev_id"]}, {"$set": {"prescribed_medicines": [MEDICINE, MEDICINE_ALT]}},
            )
            out = await record_fulfilment(fulfil(
                seen["trans_id"], seen["rev_id"], item_type="medicine", status="fulfilled",
                medicine_outcomes=[
                    {"medicine_id": MEDICINE["medicine_id"], "given": True},
                    {"medicine_id": MEDICINE_ALT["medicine_id"], "given": False},
                ],
            ), actor=CLINICAL, background_tasks=None)
            assert out["fulfilment"]["status"] == "partially_fulfilled"
            assert [o["name"] for o in out["fulfilment"]["medicine_outcomes"]] == [
                MEDICINE["name"], MEDICINE_ALT["name"],
            ]
        run_camp(monkeypatch, body)

    def test_an_outcome_set_that_misses_a_prescribed_medicine_is_refused(self, monkeypatch):
        async def body(database):
            seen = await seen_patient(database, fixed_power=None)
            with pytest.raises(HTTPException) as exc:
                await record_fulfilment(fulfil(
                    seen["trans_id"], seen["rev_id"], item_type="medicine", status="fulfilled",
                    medicine_outcomes=[],
                ), actor=CLINICAL, background_tasks=None)
            assert exc.value.detail["code"] == "MEDICINE_OUTCOMES_MISMATCH"
        run_camp(monkeypatch, body)

    def test_a_patient_who_needs_no_glasses_needs_no_power(self, monkeypatch):
        async def body(database):
            seen = await seen_patient(database, measurements=None, fixed_power=None)
            with pytest.raises(HTTPException) as exc:
                await record_fulfilment(
                    fulfil(seen["trans_id"], seen["rev_id"], item_type="specs_fixed", status="not_required"),
                    actor=CLINICAL, background_tasks=None,
                )
            assert exc.value.status_code == 400
        run_camp(monkeypatch, body)

    def test_medicine_is_unaffected_by_the_measurement_rule(self, monkeypatch):
        async def body(database):
            seen = await seen_patient(database, measurements=None, fixed_power=None)
            out = await record_fulfilment(
                fulfil(seen["trans_id"], seen["rev_id"], item_type="medicine", status="fulfilled"),
                actor=CLINICAL, background_tasks=None,
            )
            assert out["fulfilment"]["status"] == "fulfilled"
        run_camp(monkeypatch, body)

    def test_deferring_specs_prints_a_token_and_sends_one_sms(self, monkeypatch):
        sent = recorder(monkeypatch)

        async def body(database):
            camp_id, _ = await seed_camp(database)
            seen = await seen_patient(database, camp_id=camp_id, fixed_power=None, reg_no=501)
            specs_day = ObjectId()
            await database.specs_collection_days.insert_one({
                "_id": specs_day, "camp_id": camp_id, "day_date": day(15), "end_date": day(22),
                "venue": "Optical Desk", "start_time": "10:00", "end_time": "17:00", "seat_limit": 2, "seats_taken": 0,
            })
            out = await record_fulfilment(fulfil(
                seen["trans_id"], seen["rev_id"], item_type="specs_made",
                status="deferred", specs_collection_day_id=str(specs_day),
            ), actor=CLINICAL, background_tasks=None)
            assert out["slip"]["collection_date"] == day(15)
            assert sent == [{"type": "specs_token", "mobile": "9876500001", "reg_no": 501, "camp_no": "162",
                             "date": _dmy(day(15)), "end_date": _dmy(day(22)), "venue": "Optical Desk"}]
        run_camp(monkeypatch, body)

    def test_deferring_ot_sends_the_ot_token_sms(self, monkeypatch):
        sent = recorder(monkeypatch)

        async def body(database):
            camp_id, _ = await seed_camp(database)
            seen = await seen_patient(database, camp_id=camp_id, fixed_power=None, reg_no=501)
            ot_day = ObjectId()
            await database.ot_schedule_days.insert_one({
                "_id": ot_day, "camp_id": camp_id, "day_date": day(4),
                "venue": "OT Theatre", "seat_limit": 1, "seats_taken": 0,
            })
            await record_fulfilment(fulfil(
                seen["trans_id"], seen["rev_id"], item_type="ot",
                status="deferred", ot_schedule_day_id=str(ot_day),
            ), actor=CLINICAL, background_tasks=None)
            assert sent == [{"type": "ot_token", "mobile": "9876500001", "reg_no": 501, "camp_no": "162",
                             "date": _dmy(day(4)), "venue": "OT Theatre"}]
        run_camp(monkeypatch, body)

    def test_every_day_full_names_the_admin_action(self, monkeypatch):
        async def body(database):
            seen = await seen_patient(database, fixed_power=None)
            full_day = ObjectId()
            await database.ot_schedule_days.insert_one({
                "_id": full_day, "camp_id": seen["camp_id"], "day_date": day(4),
                "venue": "OT Theatre", "seat_limit": 1, "seats_taken": 1,
            })
            with pytest.raises(HTTPException) as exc:
                await record_fulfilment(fulfil(
                    seen["trans_id"], seen["rev_id"], item_type="ot",
                    status="deferred", ot_schedule_day_id=str(full_day),
                ), actor=CLINICAL, background_tasks=None)
            assert exc.value.detail["code"] == "NO_CLINICAL_DAY_AVAILABLE"
            assert "Call the admin" in exc.value.detail["message"]
        run_camp(monkeypatch, body)

    def test_one_full_day_while_another_is_free_is_a_plain_refusal(self, monkeypatch):
        async def body(database):
            seen = await seen_patient(database, fixed_power=None)
            full_day = ObjectId()
            await database.ot_schedule_days.insert_many([
                {"_id": full_day, "camp_id": seen["camp_id"], "day_date": day(4),
                 "venue": "OT Theatre", "seat_limit": 1, "seats_taken": 1},
                {"camp_id": seen["camp_id"], "day_date": day(11),
                 "venue": "OT Theatre", "seat_limit": 1, "seats_taken": 0},
            ])
            with pytest.raises(HTTPException) as exc:
                await record_fulfilment(fulfil(
                    seen["trans_id"], seen["rev_id"], item_type="ot",
                    status="deferred", ot_schedule_day_id=str(full_day),
                ), actor=CLINICAL, background_tasks=None)
            assert exc.value.detail["code"] == "DAY_FULL"
            assert exc.value.detail["message"] == "OT day is full or not found"
        run_camp(monkeypatch, body)


class TestFindingAnExistingBooking:
    def test_a_no_match_scan_can_be_followed_by_a_phone_search(self, monkeypatch):
        async def body(database):
            _camp_id, (day_id,) = await seed_camp(database)
            reg = await register(day_id, full_name="Sunita Devi", phone="9876500001", manual_entry=True)
            out = await name_search("9876500001", actor=ACTOR)
            assert [r["reg_no"] for r in out["results"]] == [reg["reg_no"]]
        run_camp(monkeypatch, body)
