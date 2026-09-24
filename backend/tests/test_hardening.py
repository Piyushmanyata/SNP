"""Regressions for the hardening pass: decode limits, malformed ids, seat accounting.

Each test names the failure it prevents, not the code it covers.
"""
import asyncio
import gzip
import io
import sys
import zlib

import pytest
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException

import helpers
import routes_camps
import routes_desk
import routes_registration
import server
import sms
from aadhaar import MAX_DECOMPRESSED_BYTES, MAX_SECURE_QR_DIGITS, _decompress, decode_aadhaar
from conftest import CommandLog
from models import FulfilmentBody
from routes_clinical import _deferred_day_id
from routes_staff import enable_staff
from seed import ACTOR, ADMIN, CARD, NOW, TODAY, day, patient_doc, run_camp, seed_camp


def _digits_for(raw: bytes) -> str:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as f:
        f.write(raw)
    return str(int.from_bytes(buf.getvalue(), "big"))


# --------------------------------------------------------------------------
# /api/aadhaar/decode takes unauthenticated input
# --------------------------------------------------------------------------

class TestDecodeLimits:
    def test_an_overlong_digit_string_is_refused_before_the_quadratic_int_parse(self):
        with pytest.raises(ValueError, match="too long"):
            _decompress("9" * (MAX_SECURE_QR_DIGITS + 1))

    def test_an_overlong_payload_is_classified_as_garbage_not_a_crash(self):
        assert decode_aadhaar("9" * (MAX_SECURE_QR_DIGITS + 1))["outcome"] == "garbage"

    def test_the_interpreter_digit_limit_matches_the_gate_it_backs(self):
        assert sys.get_int_max_str_digits() == MAX_SECURE_QR_DIGITS

    def test_a_compression_bomb_cannot_expand_past_the_decode_limit(self):
        bomb = _digits_for(b"\x00" * (MAX_DECOMPRESSED_BYTES * 8))
        assert len(bomb) <= MAX_SECURE_QR_DIGITS
        with pytest.raises(ValueError):
            _decompress(bomb)

    def test_a_truncated_stream_is_still_refused(self):
        payload = zlib.compress(b"\xff".join([b"2", b"9999", b"Aditi"]) * 20)
        truncated = str(int.from_bytes(payload[: len(payload) // 2], "big"))
        with pytest.raises(ValueError):
            _decompress(truncated)

    def test_a_real_secure_qr_still_decodes(self):
        fields = [
            "2", "999920200101120000", "Aditi Rao", "05-11-1992", "F", "D/O S Rao",
            "Bengaluru", "Opp Park", "101", "Indiranagar", "560038", "Indiranagar PO",
            "Karnataka", "100 Feet Rd", "Bengaluru East", "Bengaluru",
        ]
        raw = b"\xff".join(f.encode("ISO-8859-1") for f in fields) + b"\xff" + b"SIG" * 20
        result = decode_aadhaar(_digits_for(raw))
        assert result["outcome"] == "card"
        assert result["data"]["full_name"] == "Aditi Rao"

    def test_the_card_age_is_read_in_IST_like_every_other_age(self):
        dob = "1992-11-05"
        assert decode_aadhaar(_digits_for(
            b"\xff".join([b"2", b"999920200101120000", b"Aditi Rao", b"05-11-1992", b"F"])
            + b"\xff" * 12
        ))["data"]["age"] == helpers.age_from_dob(dob)


# --------------------------------------------------------------------------
# A malformed identifier is a client error
# --------------------------------------------------------------------------

class TestMalformedIdentifiers:
    def test_the_app_answers_a_malformed_object_id_with_400(self):
        assert InvalidId in server.app.exception_handlers
        response = asyncio.run(server.invalid_id_handler(None, InvalidId("not-an-id")))
        assert response.status_code == 400


# --------------------------------------------------------------------------
# Seat accounting
# --------------------------------------------------------------------------

class TestDeferralSeatFields:
    def _body(self, **kw):
        return FulfilmentBody(transcription_id=str(ObjectId()), **kw)

    def test_a_deferred_specs_line_never_records_an_OT_day(self):
        ot_day = str(ObjectId())
        specs_day = str(ObjectId())
        body = self._body(
            item_type="specs_made", status="deferred",
            ot_schedule_day_id=ot_day, specs_collection_day_id=specs_day,
        )
        assert _deferred_day_id(body, "ot") is None
        assert _deferred_day_id(body, "specs_made") == ObjectId(specs_day)

    def test_a_deferred_OT_line_never_records_a_specs_day(self):
        ot_day = str(ObjectId())
        body = self._body(
            item_type="ot", status="deferred",
            ot_schedule_day_id=ot_day, specs_collection_day_id=str(ObjectId()),
        )
        assert _deferred_day_id(body, "specs_made") is None
        assert _deferred_day_id(body, "ot") == ObjectId(ot_day)

    def test_a_line_that_is_not_deferred_books_no_day_at_all(self):
        body = self._body(
            item_type="ot", status="fulfilled", ot_schedule_day_id=str(ObjectId()),
        )
        assert _deferred_day_id(body, "ot") is None
        assert _deferred_day_id(body, "specs_made") is None


# --------------------------------------------------------------------------
# Desk and staff error shapes
# --------------------------------------------------------------------------

class TestConflictsAreNotCrashes:
    def test_confirming_a_card_already_held_in_this_camp_is_a_409(self, monkeypatch):
        async def body(database):
            camp_id, _ = await seed_camp(database)
            person, _ = await routes_registration._resolve_person(await routes_desk._decode_card(CARD))
            manual_id = ObjectId()
            await database.patients.insert_many([
                patient_doc(
                    _id=manual_id, camp_id=camp_id, camp_day_id=ObjectId(),
                    reg_no=1, full_name="Sunita Devi", full_name_normalized="sunita devi",
                    aadhaar_last4="1234", manual_entry=True, person_id=None,
                    queue_status="registered", patient_qr="qr-1",
                ),
                patient_doc(
                    camp_id=camp_id, camp_day_id=ObjectId(),
                    reg_no=2, full_name="Sunita Devi", aadhaar_scanned=True, person_id=person["_id"],
                    queue_status="arrived", patient_qr="qr-2",
                ),
            ])

            with pytest.raises(HTTPException) as exc:
                await routes_desk.scan_confirm(
                    routes_desk.ScanConfirmBody(patient_id=str(manual_id), payload=CARD),
                    actor=ACTOR,
                )
            assert exc.value.status_code == 409
            assert exc.value.detail["code"] == "DUPLICATE_IN_CAMP"
            assert exc.value.detail["registration"]["reg_no"] == 2

        run_camp(monkeypatch, body)

    def test_enabling_a_staff_member_that_does_not_exist_is_a_404(self, monkeypatch):
        async def body(database):
            with pytest.raises(HTTPException) as exc:
                await enable_staff(str(ObjectId()), actor=ADMIN)
            assert exc.value.status_code == 404

        run_camp(monkeypatch, body)

    def test_a_stale_print_does_not_stamp_a_row_that_now_needs_an_identity_recheck(self, monkeypatch):
        async def body(database):
            camp_id, (day_id,) = await seed_camp(database, name="C", venue="V")
            pid = ObjectId()
            row = patient_doc(
                _id=pid, camp_id=camp_id, camp_day_id=day_id, reg_no=1, full_name="P",
                patient_qr="qr-1", queue_status="arrived", arrived_at=NOW, printed_at=None,
            )
            await database.patients.insert_one({**row, "identity_recheck_required": True})

            with pytest.raises(HTTPException) as exc:
                await routes_desk._prescription_payload(database, row, ACTOR, stamp=True)
            assert exc.value.status_code == 409
            assert exc.value.detail["code"] == "PRINT_CONFLICT"
            assert (await database.patients.find_one({"_id": pid}))["printed_at"] is None

            await database.patients.update_one({"_id": pid}, {"$set": {"identity_recheck_required": False}})
            printed = await routes_desk.print_prescription(str(pid), actor=ACTOR)
            assert printed["registration"]["printed_at"]
            reprinted = await routes_desk.print_prescription(str(pid), actor=ACTOR)
            assert reprinted["registration"]["printed_at"] == printed["registration"]["printed_at"]

        run_camp(monkeypatch, body)

    def test_the_desk_does_not_reach_a_registration_from_another_camp(self, monkeypatch):
        async def body(database):
            old_id, pid = ObjectId(), ObjectId()
            await database.camps.insert_many([
                {"name": "A", "venue": "V", "is_active": True},
                {"_id": old_id, "name": "B", "venue": "V", "is_active": False},
            ])
            await database.patients.insert_one(patient_doc(
                _id=pid, camp_id=old_id, camp_day_id=ObjectId(), reg_no=7,
                patient_qr="QR-OLD", queue_status="registered",
            ))

            assert await routes_desk._resolve("7") is None
            assert await routes_desk._resolve("qr-old") is None
            for route in (routes_desk.arrive, routes_desk.print_prescription):
                with pytest.raises(HTTPException) as exc:
                    await route(str(pid), actor=ACTOR)
                assert exc.value.status_code == 409
                assert exc.value.detail["code"] == "WRONG_CAMP"

        run_camp(monkeypatch, body)


# --------------------------------------------------------------------------
# The public board is polled from every idle login screen
# --------------------------------------------------------------------------

class TestPublicOccupancy:
    def test_the_board_counts_every_day_without_a_query_per_day(self, monkeypatch):
        log = CommandLog()

        async def body(database):
            camp_id, (today_id, later_id, empty_id) = await seed_camp(database, days=(TODAY, day(1), day(2)))
            for day_id, limit in ((today_id, 50), (later_id, 30), (empty_id, 20)):
                await database.camp_days.update_one({"_id": day_id}, {"$set": {"seat_limit": limit}})
            for day_id, booked in ((today_id, 3), (later_id, 1)):
                await database.camp_days.update_one({"_id": day_id}, {"$set": {"booked": booked}})

            log.commands.clear()
            board = await routes_camps.active_camp_public()
            assert [name for name, target in log.commands if target == "patients"] == []
            assert board["total_seats"] == 100
            assert board["total_registered"] == 4
            days = {d["day_date"]: d for d in board["days"]}
            assert days[TODAY] == {
                "id": str(today_id), "day_date": TODAY, "is_today": True,
                "registered": 3, "seat_limit": 50, "remaining": 47,
            }
            assert days[day(1)]["remaining"] == 29
            assert days[day(2)]["registered"] == 0
            assert days[day(2)]["is_today"] is False

        run_camp(monkeypatch, body, listener=log)

    def test_an_over_full_day_reports_zero_remaining_not_a_negative(self, monkeypatch):
        async def body(database):
            camp_id, (day_id,) = await seed_camp(database, name="C", venue="V")
            await database.camp_days.update_one({"_id": day_id}, {"$set": {"seat_limit": 1, "booked": 3}})

            board = await routes_camps.active_camp_public()
            assert board["days"][0]["registered"] == 3
            assert board["days"][0]["remaining"] == 0
            assert board["total_registered"] == 3

        run_camp(monkeypatch, body)


# --------------------------------------------------------------------------
# The self-register rate limiter is a long-lived process's memory
# --------------------------------------------------------------------------

class TestRateLimitWindow:
    def test_an_ip_that_stopped_knocking_is_forgotten(self, monkeypatch):
        async def body(database):
            routes_registration._rl.clear()
            routes_registration._rl["10.0.0.1"] = [
                helpers.now_utc() - routes_registration.timedelta(minutes=30)
            ]
            routes_registration._rl["10.0.0.2"] = [helpers.now_utc()]

            class _Request:
                class client:
                    host = "10.0.0.3"

            with pytest.raises(HTTPException):
                await routes_registration.self_register(
                    routes_registration.RegisterBody(camp_day_id=str(ObjectId()), full_name="X"),
                    _Request(),
                    background_tasks=None)
            assert "10.0.0.1" not in routes_registration._rl
            assert routes_registration._rl["10.0.0.2"]
            assert routes_registration._rl["10.0.0.3"]

        run_camp(monkeypatch, body)


# --------------------------------------------------------------------------
# The DLT send must not hold the event loop
# --------------------------------------------------------------------------

class TestSmsDoesNotBlockTheLoop:
    def test_a_slow_provider_leaves_the_loop_free_for_other_work(self, monkeypatch):
        monkeypatch.setattr(sms.msg91, "configured", lambda: True)
        monkeypatch.setenv("MSG91_TEMPLATE_REGISTRATION", "test-flow")

        async def body(database):
            started = asyncio.Event()
            release = asyncio.Event()
            loop = asyncio.get_running_loop()

            def slow_send(message_type, mobile, variables):
                loop.call_soon_threadsafe(started.set)
                asyncio.run_coroutine_threadsafe(release.wait(), loop).result(5)
                return "provider-1"

            monkeypatch.setattr(sms.msg91, "send_dlt_sms", slow_send)
            camp_id = ObjectId()
            await database.camps.insert_one({"_id": camp_id, "name": "Sikar", "venue": "Sikar", "camp_number": 162})
            patient = {"_id": ObjectId(), "camp_id": camp_id, "phone_normalized": "9876500001", "reg_no": 7}
            task = asyncio.create_task(sms.send_patient_sms(database, patient, "registration", TODAY, "Sikar"))
            await asyncio.wait_for(started.wait(), timeout=5)
            await asyncio.sleep(0)
            release.set()
            assert await asyncio.wait_for(task, timeout=5) is True

        run_camp(monkeypatch, body)


def test_csv_formula_cells_are_prefixed():
    from routes_reports import csv_cell
    assert csv_cell("=1+1") == "'=1+1"
    assert csv_cell("+cmd") == "'+cmd"
    assert csv_cell("-2") == "'-2"
    assert csv_cell("@sum") == "'@sum"
    assert csv_cell("\tfoo") == "'\tfoo"
    assert csv_cell("\rfoo") == "'\rfoo"
    assert csv_cell("Sunita") == "Sunita"
    assert csv_cell(None) == ""
