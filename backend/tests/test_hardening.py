"""Regressions for the hardening pass: decode limits, malformed ids, seat accounting.

Each test names the failure it prevents, not the code it covers.
"""
import asyncio
import gzip
import io
import os
import sys
import zlib
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "snp_test")
os.environ.setdefault("AADHAAR_HASH_PEPPER", "test-pepper")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("ADMIN_EMAIL", "admin@example.org")
os.environ.setdefault("ADMIN_PASSWORD", "TestAdmin@2026x")

import pytest
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

import helpers
import routes_desk
import routes_registration
import server
import sms
from aadhaar import MAX_DECOMPRESSED_BYTES, MAX_SECURE_QR_DIGITS, _decompress, decode_aadhaar
from models import FulfilmentBody
from routes_clinical import _deferred_day_id
from routes_staff import enable_staff
from test_adversarial_challenger import setup_mock_db

ACTOR = {"_id": ObjectId(), "role": "volunteer"}
CARD = '<PrintLetterBarcodeData name="Sunita Devi" gender="F" dob="1975-06-14" uid="123456781234" street="12 Station Road Sikar"/>'


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
        async def run():
            mock_db = setup_mock_db(monkeypatch)
            monkeypatch.setattr(routes_desk, "get_db", lambda: mock_db)
            camp_id = ObjectId()
            day_id = ObjectId()
            await mock_db.camps.insert_one({"_id": camp_id, "is_active": True, "venue": "V"})
            await mock_db.camp_days.insert_one({
                "_id": day_id, "camp_id": camp_id, "day_date": helpers.today_ist_str(),
                "seat_limit": 50, "booked": 0,
            })
            manual_id = ObjectId()
            await mock_db.patients.insert_one({
                "_id": manual_id, "camp_id": camp_id, "camp_day_id": ObjectId(),
                "reg_no": 1, "full_name": "Sunita", "manual_entry": True,
                "queue_status": "registered", "patient_qr": "qr-1",
            })
            holder_id = ObjectId()
            await mock_db.patients.insert_one({
                "_id": holder_id, "camp_id": camp_id, "camp_day_id": ObjectId(),
                "reg_no": 2, "full_name": "Sunita Devi", "aadhaar_scanned": True,
                "queue_status": "arrived", "patient_qr": "qr-2",
            })

            async def clashing_update(query, update):
                raise DuplicateKeyError("person_id_1_camp_id_1 dup key")

            async def person_holder(query):
                if "person_id" in query:
                    return await mock_db.patients.find_one({"_id": holder_id})
                return await original_find_one(query)

            original_find_one = mock_db.patients.find_one
            monkeypatch.setattr(mock_db.patients, "update_one", clashing_update)
            monkeypatch.setattr(mock_db.patients, "find_one", person_holder)

            with pytest.raises(HTTPException) as exc:
                await routes_desk.scan_confirm(
                    routes_desk.ScanConfirmBody(patient_id=str(manual_id), payload=CARD),
                    actor=ACTOR,
                )
            assert exc.value.status_code == 409
            assert exc.value.detail["code"] == "DUPLICATE_IN_CAMP"
            assert exc.value.detail["registration"]["reg_no"] == 2

        asyncio.run(run())

    def test_enabling_a_staff_member_that_does_not_exist_is_a_404(self, monkeypatch):
        async def run():
            mock_db = setup_mock_db(monkeypatch)
            import routes_staff
            monkeypatch.setattr(routes_staff, "get_db", lambda: mock_db)

            class _NoMatch:
                matched_count = 0

            async def no_match(query, update):
                return _NoMatch()

            monkeypatch.setattr(mock_db.users, "update_one", no_match)
            with pytest.raises(HTTPException) as exc:
                await enable_staff(str(ObjectId()), actor={"_id": ObjectId(), "role": "admin"})
            assert exc.value.status_code == 404

        asyncio.run(run())


# --------------------------------------------------------------------------
# The public board is polled from every idle login screen
# --------------------------------------------------------------------------

class TestPublicOccupancy:
    def test_the_board_counts_every_day_without_a_query_per_day(self, monkeypatch):
        async def run():
            import routes_camps

            mock_db = setup_mock_db(monkeypatch)
            monkeypatch.setattr(routes_camps, "get_db", lambda: mock_db)
            monkeypatch.setattr(routes_camps, "today_ist_str", lambda: "2026-09-01")
            camp_id = ObjectId()
            await mock_db.camps.insert_one({
                "_id": camp_id, "name": "Sikar Camp", "venue": "Sikar Bhawan", "is_active": True,
            })
            today_id, later_id, empty_id = ObjectId(), ObjectId(), ObjectId()
            for day_id, date, limit in (
                (today_id, "2026-09-01", 50),
                (later_id, "2026-09-02", 30),
                (empty_id, "2026-09-03", 20),
            ):
                await mock_db.camp_days.insert_one({
                    "_id": day_id, "camp_id": camp_id, "day_date": date, "seat_limit": limit,
                })
            for day_id, n in ((today_id, 3), (later_id, 1)):
                for _ in range(n):
                    await mock_db.patients.insert_one({
                        "camp_id": camp_id, "camp_day_id": day_id, "booked_camp_day_id": day_id,
                    })

            calls = {"n": 0}
            original_count = mock_db.patients.count_documents

            async def counted(query):
                calls["n"] += 1
                return await original_count(query)

            monkeypatch.setattr(mock_db.patients, "count_documents", counted)

            board = await routes_camps.active_camp_public()
            assert calls["n"] == 0
            assert board["total_seats"] == 100
            assert board["total_registered"] == 4
            days = {d["day_date"]: d for d in board["days"]}
            assert days["2026-09-01"] == {
                "id": str(today_id), "day_date": "2026-09-01", "is_today": True,
                "registered": 3, "seat_limit": 50, "remaining": 47,
            }
            assert days["2026-09-02"]["remaining"] == 29
            assert days["2026-09-03"]["registered"] == 0
            assert days["2026-09-03"]["is_today"] is False

        asyncio.run(run())

    def test_an_over_full_day_reports_zero_remaining_not_a_negative(self, monkeypatch):
        async def run():
            import routes_camps

            mock_db = setup_mock_db(monkeypatch)
            monkeypatch.setattr(routes_camps, "get_db", lambda: mock_db)
            monkeypatch.setattr(routes_camps, "today_ist_str", lambda: "2026-09-01")
            camp_id, day_id = ObjectId(), ObjectId()
            await mock_db.camps.insert_one({
                "_id": camp_id, "name": "C", "venue": "V", "is_active": True,
            })
            await mock_db.camp_days.insert_one({
                "_id": day_id, "camp_id": camp_id, "day_date": "2026-09-01", "seat_limit": 1,
            })
            for _ in range(3):
                await mock_db.patients.insert_one({
                    "camp_id": camp_id, "camp_day_id": day_id, "booked_camp_day_id": day_id,
                })

            board = await routes_camps.active_camp_public()
            assert board["days"][0]["registered"] == 3
            assert board["days"][0]["remaining"] == 0
            assert board["total_registered"] == 3

        asyncio.run(run())


# --------------------------------------------------------------------------
# The self-register rate limiter is a long-lived process's memory
# --------------------------------------------------------------------------

class TestRateLimitWindow:
    def test_an_ip_that_stopped_knocking_is_forgotten(self, monkeypatch):
        async def run():
            mock_db = setup_mock_db(monkeypatch)
            monkeypatch.setattr(routes_registration, "get_db", lambda: mock_db)
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
                )
            assert "10.0.0.1" not in routes_registration._rl
            assert routes_registration._rl["10.0.0.2"]
            assert routes_registration._rl["10.0.0.3"]

        asyncio.run(run())


# --------------------------------------------------------------------------
# The DLT send must not hold the event loop
# --------------------------------------------------------------------------

class TestSmsDoesNotBlockTheLoop:
    def test_a_slow_provider_leaves_the_loop_free_for_other_work(self, monkeypatch):
        async def run():
            mock_db = setup_mock_db(monkeypatch)
            monkeypatch.setattr(sms.msg91, "configured", lambda: True)
            started = asyncio.Event()
            release = asyncio.Event()
            loop = asyncio.get_running_loop()

            def slow_send(message_type, mobile, reg_no, event_date, venue):
                loop.call_soon_threadsafe(started.set)
                asyncio.run_coroutine_threadsafe(release.wait(), loop).result(5)
                return "provider-1"

            monkeypatch.setattr(sms.msg91, "send_dlt_sms", slow_send)
            patient = {"_id": ObjectId(), "phone_normalized": "9876500001", "reg_no": 7}
            task = asyncio.create_task(
                sms.send_patient_sms(mock_db, patient, "registration", "2026-09-01", "Sikar")
            )
            await asyncio.wait_for(started.wait(), timeout=5)
            # The loop is still answering while the provider call is outstanding.
            await asyncio.sleep(0)
            release.set()
            assert await asyncio.wait_for(task, timeout=5) is True

        asyncio.run(run())


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
