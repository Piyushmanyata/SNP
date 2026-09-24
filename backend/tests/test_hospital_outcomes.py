"""Hospital outcomes, the line rules, Clinical find, Displayed dates and the Hospital export."""
import csv
import io
import re

import pytest
from bson import ObjectId
from fastapi import HTTPException

import routes_clinical
import sms
from models import CorrectionBody
from routes_clinical import (
    add_correction, clinical_lookup, clinical_search, complete_prescription, get_slip, record_fulfilment,
)
from routes_reports import _empty_board, export_camp_records
from seed import FIXED_POWER, MEDICINE, day, patient_doc, recorder, run_camp
from test_camp_operations_matrix import (
    ADMIN, CLINICAL, OT_DATE, RX, _complete_body, _issue_body, _printed_patient, _register_printed,
)


def _dmy(iso_date):
    y, m, d = iso_date.split("-")
    return f"{d}-{m}-{y}"


def _lines(lines, outcome="iol_surgery", eye="R", **extra):
    data = {"prescribed_lines": lines}
    if "medicine" not in lines:
        data["prescribed_medicine_ids"] = []
    if "specs_fixed" in lines:
        data.update(fixed_power_r=FIXED_POWER, fixed_power_l=FIXED_POWER)
    if "specs_made" in lines:
        data["specs_measurements"] = RX
    if "ot" in lines:
        data["ot_outcome"] = outcome
        if outcome == "iol_surgery":
            data["ot_eye"] = eye
    data.update(extra)
    return data


async def _complete(patient, op="complete", **content):
    return await complete_prescription(_complete_body(patient["_id"], op, **content), actor=CLINICAL)


async def _ot_day(db, camp_id, seat_limit=5):
    day_id = ObjectId()
    await db.ot_schedule_days.insert_one({
        "_id": day_id, "camp_id": camp_id, "day_date": OT_DATE,
        "venue": "Bajaj Hospital", "seat_limit": seat_limit, "seats_taken": 0,
    })
    return day_id


async def _record(done, op, status, day_id=None):
    extra = {"item_type": "ot", "status": status}
    if day_id:
        extra["ot_schedule_day_id"] = str(day_id)
    body = _issue_body(
        done["transcription"]["id"], done["revision"]["id"],
        done["registration"]["clinical_generation"], op, **extra,
    )
    return await record_fulfilment(body, actor=CLINICAL, background_tasks=None)


def _refusal(exc):
    return exc.value.status_code, exc.value.detail


async def _csv_rows(camp_id):
    resp = await export_camp_records(camp_id=str(camp_id), actor=ADMIN)
    chunks = []
    async for chunk in resp.body_iterator:
        chunks.append(chunk if isinstance(chunk, str) else chunk.decode())
    return list(csv.DictReader(io.StringIO("".join(chunks))))


class TestPrescriptionLineRules:
    @pytest.mark.parametrize("lines,outcome", [
        (["medicine", "specs_fixed"], None),
        (["medicine", "specs_made"], None),
        (["medicine", "ot"], "iol_surgery"),
        (["specs_fixed", "ot"], "referral"),
        (["specs_made", "ot"], "referral"),
        (["medicine", "specs_made", "ot"], "referral"),
    ])
    def test_allowed_combinations_complete(self, monkeypatch, lines, outcome):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)
            done = await _complete(patient, **_lines(lines, outcome=outcome))
            assert done["revision"]["prescribed_lines"] == lines
            assert done["revision"]["ot_outcome"] == outcome
        run_camp(monkeypatch, run)

    @pytest.mark.parametrize("lines,outcome,named", [
        (["specs_fixed", "specs_made"], None, ["Fixed-power specs", "Spectacles to be made"]),
        (["specs_fixed", "ot"], "iol_surgery", ["Fixed-power specs", "IOL surgery"]),
        (["medicine", "specs_made", "ot"], "iol_surgery", ["Spectacles to be made", "IOL surgery"]),
        (["specs_fixed", "specs_made", "ot"], "iol_surgery",
         ["Fixed-power specs", "Spectacles to be made", "IOL surgery"]),
    ])
    def test_clashing_lines_are_refused_by_name(self, monkeypatch, lines, outcome, named):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)
            with pytest.raises(HTTPException) as exc:
                await _complete(patient, **_lines(lines, outcome=outcome))
            status, detail = _refusal(exc)
            assert status == 400
            assert detail["code"] == "incomplete_prescription"
            for label in named:
                assert label in detail["fields"]["prescribed_lines"]
            assert await db.prescription_revisions.count_documents({}) == 0
        run_camp(monkeypatch, run)

    @pytest.mark.parametrize("content,field", [
        ({"prescribed_lines": ["ot"], "ot_eye": "R"}, "ot_outcome"),
        ({"prescribed_lines": ["ot"], "ot_outcome": "cataract", "ot_eye": "R"}, "ot_outcome"),
        ({"prescribed_lines": ["ot"], "ot_outcome": "iol_surgery"}, "ot_eye"),
        ({"prescribed_lines": ["ot"], "ot_outcome": "iol_surgery", "ot_eye": "B"}, "ot_eye"),
        ({"prescribed_lines": ["ot"], "ot_outcome": "iol_surgery", "ot_eye": "both"}, "ot_eye"),
        ({"prescribed_lines": ["ot"], "ot_outcome": "referral", "ot_eye": "L"}, "ot_eye"),
        ({"prescribed_lines": ["medicine"], "ot_outcome": "referral"}, "ot_outcome"),
        ({"prescribed_lines": ["medicine"], "ot_eye": "R"}, "ot_eye"),
        ({"prescribed_lines": ["ot"], "ot_procedure": "Cataract Surgery", "ot_eye": "R"}, "ot_outcome"),
    ])
    def test_hospital_outcome_and_eye_are_enforced(self, monkeypatch, content, field):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)
            if content["prescribed_lines"] == ["ot"]:
                content.setdefault("prescribed_medicine_ids", [])
            with pytest.raises(HTTPException) as exc:
                await _complete(patient, **content)
            status, detail = _refusal(exc)
            assert status == 400
            assert detail["code"] == "incomplete_prescription"
            assert field in detail["fields"]
        run_camp(monkeypatch, run)

    def test_iol_surgery_stores_one_eye_and_no_procedure(self, monkeypatch):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)
            done = await _complete(patient, **_lines(
                ["ot"], eye="left", ot_outcome="iol_surgery", ot_notes="Right eye also prescribed",
            ))
            stored = await db.prescription_revisions.find_one({"_id": ObjectId(done["revision"]["id"])})
            assert stored["ot_eye"] == "L"
            assert stored["ot_outcome"] == "iol_surgery"
            assert stored["ot_notes"] == "Right eye also prescribed"
            assert "ot_procedure" not in stored
            assert "ot_procedure" not in done["revision"]
        run_camp(monkeypatch, run)

    def test_referral_goes_with_either_specs_line_and_stores_no_eye(self, monkeypatch):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)
            done = await _complete(patient, **_lines(["specs_fixed", "ot"], outcome="referral"))
            assert done["revision"]["ot_eye"] is None
            assert done["transcription"]["ot_outcome"] == "referral"
        run_camp(monkeypatch, run)

    def test_correction_applies_the_same_rules_and_lets_a_declined_patient_have_spectacles(self, monkeypatch):
        async def run(db):
            camp_id, _day, patient = await _printed_patient(db)
            done = await _complete(patient, **_lines(["medicine", "ot"]))
            await _record(done, "decline", "declined")
            with pytest.raises(HTTPException) as exc:
                await add_correction(CorrectionBody(
                    patient_id=str(patient["_id"]), reason="Patient wants spectacles",
                    expected_generation=1, operation_id="corr-clash", full_transcription_confirmed=True,
                    prescribed_lines=["medicine", "specs_made", "ot"], specs_measurements=RX,
                    prescribed_medicine_ids=[MEDICINE["medicine_id"]],
                ), actor=CLINICAL)
            assert exc.value.detail["fields"]["prescribed_lines"].count("IOL surgery") == 1
            with pytest.raises(HTTPException) as exc:
                await add_correction(CorrectionBody(
                    patient_id=str(patient["_id"]), reason="Patient wants spectacles",
                    expected_generation=1, operation_id="corr-stale-outcome", full_transcription_confirmed=True,
                    prescribed_lines=["medicine", "specs_made"], specs_measurements=RX,
                    prescribed_medicine_ids=[MEDICINE["medicine_id"]],
                ), actor=CLINICAL)
            assert "ot_outcome" in exc.value.detail["fields"]
            with pytest.raises(HTTPException) as exc:
                await add_correction(CorrectionBody(
                    patient_id=str(patient["_id"]), reason="Both eyes written",
                    expected_generation=1, operation_id="corr-both", full_transcription_confirmed=True,
                    prescribed_lines=["medicine", "ot"], ot_outcome="iol_surgery", ot_eye="B",
                    prescribed_medicine_ids=[MEDICINE["medicine_id"]],
                ), actor=CLINICAL)
            assert "ot_eye" in exc.value.detail["fields"]
            corrected = await add_correction(CorrectionBody(
                patient_id=str(patient["_id"]), reason="Patient declined IOL surgery and wants spectacles",
                expected_generation=1, operation_id="corr-ok", full_transcription_confirmed=True,
                prescribed_lines=["medicine", "specs_made"], specs_measurements=RX,
                prescribed_medicine_ids=[MEDICINE["medicine_id"]], ot_outcome=None, ot_eye=None,
            ), actor=CLINICAL)
            assert corrected["revision"]["prescribed_lines"] == ["medicine", "specs_made"]
            assert corrected["revision"]["ot_outcome"] is None
        run_camp(monkeypatch, run)


class TestHospitalStation:
    def test_scheduling_takes_a_seat_prints_a_token_and_sends_the_ot_token_sms(self, monkeypatch):
        async def run(db):
            camp_id, _day, patient = await _printed_patient(db)
            sent = recorder(monkeypatch)
            done = await _complete(patient, **_lines(["ot"], eye="L"), bp="130/85", blood_sugar="140")
            day_id = await _ot_day(db, camp_id)
            out = await _record(done, "schedule", "deferred", day_id)
            assert out["fulfilment"]["status"] == "deferred"
            assert (await db.ot_schedule_days.find_one({"_id": day_id}))["seats_taken"] == 1
            assert [s["type"] for s in sent] == ["ot_token"]
            token = await get_slip(out["slip"]["id"], actor=CLINICAL)
            assert token["slip"]["ot_eye"] == "L"
            assert token["slip"]["bp"] == "130/85"
            assert token["slip"]["blood_sugar"] == "140"
            assert "राशन कार्ड" in token["slip"]["instructions"]
            assert "वोटर" not in token["slip"]["instructions"]
        run_camp(monkeypatch, run)

    def test_declined_takes_nothing_and_sends_nothing(self, monkeypatch):
        async def run(db):
            camp_id, _day, patient = await _printed_patient(db)
            sent = recorder(monkeypatch)
            done = await _complete(patient, **_lines(["ot"]))
            day_id = await _ot_day(db, camp_id)
            out = await _record(done, "decline", "declined")
            assert out["fulfilment"]["status"] == "declined"
            assert out["slip"] is None
            assert out["fulfilment"]["ot_schedule_day_id"] is None
            assert (await db.ot_schedule_days.find_one({"_id": day_id}))["seats_taken"] == 0
            assert await db.deferred_slips.count_documents({}) == 0
            assert sent == []
        run_camp(monkeypatch, run)

    def test_declined_after_scheduling_releases_the_seat_once_and_cancels_the_token(self, monkeypatch):
        async def run(db):
            camp_id, _day, patient = await _printed_patient(db)
            sent = recorder(monkeypatch)
            done = await _complete(patient, **_lines(["ot"]))
            day_id = await _ot_day(db, camp_id)
            await _record(done, "schedule", "deferred", day_id)
            declined = await _record(done, "decline", "declined")
            assert declined["fulfilment"]["status"] == "declined"
            assert (await db.ot_schedule_days.find_one({"_id": day_id}))["seats_taken"] == 0
            assert await db.deferred_slips.count_documents({"active": True}) == 0
            assert await _record(done, "decline", "declined") == declined
            await _record(done, "decline-again", "declined")
            assert (await db.ot_schedule_days.find_one({"_id": day_id}))["seats_taken"] == 0
            assert [s["type"] for s in sent] == ["ot_token"]
        run_camp(monkeypatch, run)

    @pytest.mark.parametrize("change", [
        {"prescribed_lines": ["ot"], "ot_outcome": "referral", "ot_eye": None},
        {"prescribed_lines": ["medicine"], "ot_outcome": None, "ot_eye": None,
         "prescribed_medicine_ids": [MEDICINE["medicine_id"]]},
    ])
    def test_a_scheduled_iol_surgery_cannot_be_corrected_away_until_it_is_declined(self, monkeypatch, change):
        async def run(db):
            camp_id, _day, patient = await _printed_patient(db)
            done = await _complete(patient, **_lines(["ot"]))
            day_id = await _ot_day(db, camp_id)
            await _record(done, "schedule", "deferred", day_id)
            body = dict(
                patient_id=str(patient["_id"]), reason="Doctor wrote referral", expected_generation=1,
                operation_id="corr-away", full_transcription_confirmed=True, **change,
            )
            with pytest.raises(HTTPException) as exc:
                await add_correction(CorrectionBody(**body), actor=CLINICAL)
            status_code, detail = _refusal(exc)
            assert status_code == 409
            assert detail["code"] == "surgery_scheduled"
            assert (await db.ot_schedule_days.find_one({"_id": day_id}))["seats_taken"] == 1
            await _record(done, "decline", "declined")
            corrected = await add_correction(CorrectionBody(**{**body, "operation_id": "corr-after"}), actor=CLINICAL)
            assert corrected["revision"]["prescribed_lines"] == change["prescribed_lines"]
        run_camp(monkeypatch, run)

    def test_a_surgery_scheduled_while_a_correction_is_prepared_still_blocks_it(self, monkeypatch):
        async def run(db):
            camp_id, _day, patient = await _printed_patient(db)
            done = await _complete(patient, **_lines(["ot"]))
            day_id = await _ot_day(db, camp_id)
            original = routes_clinical.in_transaction

            async def schedule_first(write):
                monkeypatch.setattr(routes_clinical, "in_transaction", original)
                await _record(done, "schedule", "deferred", day_id)
                return await original(write)

            monkeypatch.setattr(routes_clinical, "in_transaction", schedule_first)
            body = CorrectionBody(
                patient_id=str(patient["_id"]), reason="Doctor wrote referral", expected_generation=1,
                operation_id="corr-race", full_transcription_confirmed=True,
                prescribed_lines=["ot"], ot_outcome="referral", ot_eye=None,
            )
            with pytest.raises(HTTPException) as exc:
                await add_correction(body, actor=CLINICAL)
            assert _refusal(exc)[1]["code"] == "surgery_scheduled"
            current = await db.patients.find_one({"_id": patient["_id"]})
            assert str(current["committed_revision_id"]) == done["revision"]["id"]
        run_camp(monkeypatch, run)

    @pytest.mark.parametrize("status", ["deferred", "declined"])
    def test_a_referral_cannot_be_recorded_at_the_station(self, monkeypatch, status):
        async def run(db):
            camp_id, _day, patient = await _printed_patient(db)
            sent = recorder(monkeypatch)
            done = await _complete(patient, **_lines(["ot"], outcome="referral"))
            day_id = await _ot_day(db, camp_id)
            with pytest.raises(HTTPException) as exc:
                await _record(done, "referral", status, day_id if status == "deferred" else None)
            status_code, detail = _refusal(exc)
            assert status_code == 409
            assert detail["code"] == "hospital_referral"
            assert (await db.ot_schedule_days.find_one({"_id": day_id}))["seats_taken"] == 0
            assert await db.fulfilments.count_documents({}) == 0
            assert sent == []
        run_camp(monkeypatch, run)

    def test_fulfilled_is_not_a_hospital_outcome(self, monkeypatch):
        async def run(db):
            _camp, _day, patient = await _printed_patient(db)
            done = await _complete(patient, **_lines(["ot"]))
            with pytest.raises(HTTPException) as exc:
                await _record(done, "fulfilled", "fulfilled")
            assert exc.value.status_code == 400
        run_camp(monkeypatch, run)


class TestClinicalFind:
    def test_lookup_refuses_another_camps_reg_no_and_patient_code(self, monkeypatch):
        async def run(db):
            old_camp, _day, old = await _printed_patient(db)
            await db.camps.update_one({"_id": old_camp}, {"$set": {"is_active": False}})
            await db.patients.update_one({"_id": old["_id"]}, {"$set": {"reg_no": 999}})
            _camp, _day, current = await _printed_patient(db, full_name="Ram Prasad")
            for value in ("999", f"snp:{old['patient_qr']}"):
                with pytest.raises(HTTPException) as exc:
                    await clinical_lookup({"value": value}, actor=CLINICAL)
                assert exc.value.status_code == 404
            found = await clinical_lookup({"value": f"SNP:{current['patient_qr']}"}, actor=CLINICAL)
            assert found["registration"]["id"] == str(current["_id"])
        run_camp(monkeypatch, run)

    def test_name_search_lists_only_arrived_and_printed_patients_of_the_active_camp(self, monkeypatch):
        async def run(db):
            camp_id, day_id, first = await _printed_patient(db, full_name="Sunita Devi", phone="9876512345")
            not_arrived = await _register_printed(
                day_id, arrived=False, printed=False, full_name="Sunita Kumari", age=40, phone="9876500002",
            )
            not_printed = await _register_printed(day_id, printed=False, full_name="Sunita Rani", age=40, phone="9876500003")
            await db.patients.insert_one(patient_doc(
                camp_id=ObjectId(), full_name="Sunita Other",
                full_name_normalized="sunita other", arrived_at=first["arrived_at"],
                printed_at=first["printed_at"], phone="9876500004",
            ))
            out = await clinical_search(q="  SUNITA  d", actor=CLINICAL)
            assert out["results"] == [{
                "id": str(first["_id"]), "reg_no": first["reg_no"], "full_name": "Sunita Devi",
                "age": first["age"], "gender_label": "-", "phone_last4": "2345",
            }]
            assert (await clinical_search(q="sunita k", actor=CLINICAL))["results"] == []
            assert (await clinical_search(q="sunita r", actor=CLINICAL))["results"] == []
            assert (await clinical_search(q="sunita o", actor=CLINICAL))["results"] == []
            for i in range(21):
                await _register_printed(day_id, full_name=f"Sunita Bai {chr(97 + i)}", age=40, phone=f"98765{i:05d}")
            results = (await clinical_search(q="Sunita", actor=CLINICAL))["results"]
            assert len(results) == 20
            assert not {not_arrived, not_printed} & {r["id"] for r in results}
            for row in results:
                assert set(row) == {"id", "reg_no", "full_name", "age", "gender_label", "phone_last4"}
                assert re.fullmatch(r"\d{4}", row["phone_last4"])
        run_camp(monkeypatch, run)

    def test_a_long_digit_payload_finds_nobody(self, monkeypatch):
        async def run(db):
            await _printed_patient(db)
            with pytest.raises(HTTPException) as exc:
                await clinical_lookup({"value": "2567820190301120000123456789"}, actor=CLINICAL)
            assert exc.value.status_code == 404
        run_camp(monkeypatch, run)

    @pytest.mark.parametrize("role", ["volunteer", "team_lead", "admin"])
    def test_name_search_refuses_other_roles(self, monkeypatch, role):
        async def run(db):
            with pytest.raises(HTTPException) as exc:
                await clinical_search(q="Sunita", actor={"_id": ObjectId(), "role": role})
            assert exc.value.status_code == 403
        run_camp(monkeypatch, run)


class TestDisplayedDates:
    @pytest.mark.parametrize("message_type", ["registration", "camp", "ot_token", "ot", "specs_token", "specs"])
    def test_every_sms_states_its_date_as_dd_mm_yyyy(self, monkeypatch, message_type):
        async def run(db):
            sent = recorder(monkeypatch)
            camp_id = ObjectId()
            await db.camps.insert_one({"_id": camp_id, "name": "C", "venue": "Hall", "camp_number": 162})
            patient = {"_id": ObjectId(), "camp_id": camp_id, "phone": "9876500001", "reg_no": 7}
            start, end = day(12), day(19)
            assert await sms.send_patient_sms(db, patient, message_type, start, "Hall", "10:00", "17:00", end)
            assert sent[0]["date"] == _dmy(start)
            if message_type.startswith("specs"):
                assert sent[0]["end_date"] == _dmy(end)
            ledger = await db.reminder_ledger.find_one({"patient_id": patient["_id"]})
            if message_type.startswith("specs"):
                assert "10:00 AM से 5:00 PM" in ledger["copy"]
            assert ledger["event_date"] == start
            assert _dmy(start) in ledger["copy"]
            assert start not in ledger["copy"]
        run_camp(monkeypatch, run)

    def test_export_writes_hospital_outcomes_and_dd_mm_yyyy_dates(self, monkeypatch):
        async def run(db):
            recorder(monkeypatch)
            camp_id, day_id, scheduled = await _printed_patient(db, full_name="Sunita Devi")
            camp_day = await db.camp_days.find_one({"_id": day_id})
            declined_id = await _register_printed(day_id, full_name="Ram Prasad", age=40, phone="9876500002")
            referred_id = await _register_printed(day_id, full_name="Kamla Bai", age=40, phone="9876500003")
            none_id = await _register_printed(day_id, full_name="Mohan Lal", age=40, phone="9876500004")
            ot_day = await _ot_day(db, camp_id)
            done = await _complete(scheduled, **_lines(["ot"]))
            await _record(done, "schedule", "deferred", ot_day)
            declined = await _complete({"_id": ObjectId(declined_id)}, "c2", **_lines(["ot"]))
            await _record(declined, "sched-2", "deferred", ot_day)
            await _record(declined, "decline-2", "declined")
            await _complete({"_id": ObjectId(referred_id)}, "c3", **_lines(["specs_made", "ot"], outcome="referral"))
            await _complete({"_id": ObjectId(none_id)}, "c4", **_lines(["medicine"]))
            rows = {row["full_name"]: row for row in await _csv_rows(camp_id)}
            assert [rows[n]["ot"] for n in ("Sunita Devi", "Ram Prasad", "Kamla Bai", "Mohan Lal")] == [
                "scheduled", "declined", "referred", "",
            ]
            assert rows["Sunita Devi"]["ot_day"] == _dmy(OT_DATE)
            assert rows["Sunita Devi"]["ot_venue"] == "Bajaj Hospital"
            for name in ("Ram Prasad", "Kamla Bai", "Mohan Lal"):
                assert rows[name]["ot_day"] == ""
                assert rows[name]["ot_venue"] == ""
            assert rows["Sunita Devi"]["camp_day"] == _dmy(camp_day["day_date"])
            for column in ("registered_at", "arrived_at", "seen_at"):
                assert re.fullmatch(r"\d{2}-\d{2}-\d{4} \d{2}:\d{2}", rows["Sunita Devi"][column])
        run_camp(monkeypatch, run)

    def test_export_writes_the_specs_day_as_dd_mm_yyyy(self, monkeypatch):
        async def run(db):
            recorder(monkeypatch)
            camp_id, _day, patient = await _printed_patient(db)
            done = await _complete(patient, **_lines(["specs_made"]))
            specs_day = ObjectId()
            await db.specs_collection_days.insert_one({
                "_id": specs_day, "camp_id": camp_id, "day_date": day(15),
                "venue": "Optical Desk", "start_time": "10:00", "end_time": "17:00",
            })
            await record_fulfilment(_issue_body(
                done["transcription"]["id"], done["revision"]["id"], 1, "specs",
                item_type="specs_made", status="deferred", specs_collection_day_id=str(specs_day),
            ), actor=CLINICAL, background_tasks=None)
            (row,) = await _csv_rows(camp_id)
            assert row["specs_day"] == _dmy(day(15))
        run_camp(monkeypatch, run)


def test_board_hospital_counts_are_scheduled_and_declined():
    assert _empty_board("now", "no_camp")["fulfilment"]["ot"] == {"deferred": 0, "declined": 0}
