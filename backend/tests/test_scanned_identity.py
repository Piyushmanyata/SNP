import pytest
from bson import ObjectId
from fastapi import HTTPException

import helpers
from models import QrLookupBody, RegisterBody
from routes_desk import lookup
from routes_registration import desk_register
from seed import ACTOR, Request, run_camp, seed_camp
from test_aadhaar_unit import SAMPLE, build_secure_qr

LEGACY_CARD = ('<PrintLetterBarcodeData name="Sunita Devi" gender="F" dob="1975-06-14" '
               'uid="123456781234" street="12 Station Road Sikar"/>')
SECURE_CARD = build_secure_qr(SAMPLE)
UNKNOWN_ROOT = ('<anything name="Not Aadhaar" gender="F" dob="1975-06-14" '
                'uid="123456781234" street="12 Station Road Sikar"/>')
TRUNCATED = '<PrintLetterBarcodeData name="Sunita Devi" gender="F" dob="1975-06-14" uid="12345678'
FUTURE_DOB = ('<PrintLetterBarcodeData name="Sunita Devi" gender="F" dob="2099-06-14" '
              'uid="123456781234" street="12 Station Road Sikar"/>')
BAD_UID = ('<PrintLetterBarcodeData name="Sunita Devi" gender="F" dob="1975-06-14" '
           'uid="12345" street="12 Station Road Sikar"/>')


async def _register(day_id, **fields):
    body = RegisterBody(
        full_name=fields.pop("full_name", "Sunita Devi"),
        age=fields.pop("age", 51),
        phone=fields.pop("phone", "9876500001"),
        camp_day_id=str(day_id),
        **fields,
    )
    return await desk_register(body, Request(), actor=ACTOR, background_tasks=None)


async def _assert_nothing_written(database, day_id):
    assert await database.patients.count_documents({}) == 0
    assert await database.persons.count_documents({}) == 0
    day = await database.camp_days.find_one({"_id": day_id})
    assert not day.get("booked")


class TestStaffScannedIdentityIsServerDerived:
    def test_scanned_claim_without_qr_payload_is_rejected(self, monkeypatch):
        async def run(database):
            _camp_id, (day_id,) = await seed_camp(database)
            with pytest.raises(HTTPException) as exc:
                await _register(day_id, gender="F", dob="1975-06-14",
                                aadhaar_last4="1234", aadhaar_scanned=True)
            assert exc.value.status_code == 400
            assert exc.value.detail["code"] == "AADHAAR_QR_REQUIRED"
            await _assert_nothing_written(database, day_id)
        run_camp(monkeypatch, run)

    def test_tampered_identity_fields_are_replaced_by_the_card(self, monkeypatch):
        async def run(database):
            _camp_id, (day_id,) = await seed_camp(database)
            result = await _register(
                day_id, full_name="Attacker Name", gender="M", dob="1999-01-01",
                age=26, address="Somewhere Else", aadhaar_last4="9999",
                aadhaar_scanned=True, qr_payload=LEGACY_CARD,
            )
            stored = await database.patients.find_one(
                {"_id": ObjectId(result["registration"]["id"])},
            )
            assert stored["full_name"] == "Sunita Devi"
            assert stored["gender"] == "F"
            assert stored["dob"] == "1975-06-14"
            assert stored["aadhaar_last4"] == "1234"
            assert stored["address"] == "12 Station Road Sikar"
            assert stored["age"] == helpers.age_from_dob("1975-06-14")
            assert stored["aadhaar_scanned"] is True
            assert stored["manual_entry"] is False
        run_camp(monkeypatch, run)

    def test_manual_claim_cannot_be_smuggled_in_with_a_card(self, monkeypatch):
        async def run(database):
            _camp_id, (day_id,) = await seed_camp(database)
            result = await _register(
                day_id, aadhaar_scanned=True, qr_payload=LEGACY_CARD,
                manual_entry=True, manual_exception=True,
            )
            stored = await database.patients.find_one(
                {"_id": ObjectId(result["registration"]["id"])},
            )
            assert stored["manual_entry"] is False
            assert stored["manual_exception"] is None
            assert stored["identity_recheck_required"] is False
        run_camp(monkeypatch, run)

    @pytest.mark.parametrize("payload", [LEGACY_CARD, SECURE_CARD])
    def test_valid_cards_still_register(self, monkeypatch, payload):
        async def run(database):
            _camp_id, (day_id,) = await seed_camp(database)
            result = await _register(day_id, aadhaar_scanned=True, qr_payload=payload)
            assert result["created"] is True
            assert result["registration"]["aadhaar_scanned"] is True
            assert await database.patients.count_documents({}) == 1
            assert await database.persons.count_documents({}) == 1
        run_camp(monkeypatch, run)

    @pytest.mark.parametrize("payload", [
        UNKNOWN_ROOT, TRUNCATED, FUTURE_DOB, BAD_UID, "", "not a card at all",
    ])
    def test_unreadable_cards_write_nothing(self, monkeypatch, payload):
        async def run(database):
            _camp_id, (day_id,) = await seed_camp(database)
            with pytest.raises(HTTPException) as exc:
                await _register(day_id, aadhaar_scanned=True, qr_payload=payload)
            assert exc.value.status_code == 400
            assert exc.value.detail["code"] == "AADHAAR_QR_REQUIRED"
            await _assert_nothing_written(database, day_id)
        run_camp(monkeypatch, run)

    def test_manual_registration_is_still_accepted(self, monkeypatch):
        async def run(database):
            _camp_id, (day_id,) = await seed_camp(database)
            result = await _register(
                day_id, manual_entry=True, manual_reason="Card not readable",
                )
            stored = await database.patients.find_one(
                {"_id": ObjectId(result["registration"]["id"])},
            )
            assert result["created"] is True
            assert stored["aadhaar_scanned"] is False
            assert stored["manual_entry"] is True
            assert stored["identity_recheck_required"] is True
        run_camp(monkeypatch, run)


class TestDeskNumericLookupBound:
    def test_oversized_numeric_lookup_is_a_client_error(self, monkeypatch):
        async def run(database):
            await seed_camp(database)
            with pytest.raises(HTTPException) as exc:
                await lookup(QrLookupBody(value="9" * 400), actor=ACTOR)
            assert exc.value.status_code == 400
        run_camp(monkeypatch, run)

    def test_non_decimal_digits_do_not_reach_the_int_conversion(self, monkeypatch):
        async def run(database):
            await seed_camp(database)
            with pytest.raises(HTTPException) as exc:
                await lookup(QrLookupBody(value="²²²"), actor=ACTOR)
            assert exc.value.status_code == 404
        run_camp(monkeypatch, run)

    def test_ordinary_registration_number_still_resolves(self, monkeypatch):
        async def run(database):
            _camp_id, (day_id,) = await seed_camp(database)
            result = await _register(day_id, aadhaar_scanned=True, qr_payload=LEGACY_CARD)
            reg_no = result["registration"]["reg_no"]
            found = await lookup(QrLookupBody(value=str(reg_no)), actor=ACTOR)
            assert found["registration"]["id"] == result["registration"]["id"]
        run_camp(monkeypatch, run)
