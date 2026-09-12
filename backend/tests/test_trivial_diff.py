"""Trivial diff: silent Aadhaar overwrite + Arrival vs Mismatch review."""
import asyncio
import os
import sys
from pathlib import Path
from xml.etree.ElementTree import Element, tostring

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "snp_test")
os.environ.setdefault("AADHAAR_HASH_PEPPER", "test-pepper")

from bson import ObjectId

from models import RegisterBody, ScanBody
from routes_desk import _material_diff, scan
from routes_registration import desk_register
from test_camp_lifecycle import ACTOR, _Request, _mock, _seed_camp

CARD_NAME = "Sunita Devi"
CARD_GENDER = "F"
CARD_DOB = "1975-06-14"
CARD_UID = "123456781234"
CARD_ADDR = "12 Station Road Sikar"


def payload(name=CARD_NAME, gender=CARD_GENDER, dob=CARD_DOB, uid=CARD_UID, address=CARD_ADDR):
    return tostring(Element("PrintLetterBarcodeData", name=name, gender=gender, dob=dob, uid=uid, street=address), encoding="unicode")


def card_dict(**over):
    base = {
        "full_name": CARD_NAME,
        "age": 51,
        "gender": CARD_GENDER,
        "dob": CARD_DOB,
        "aadhaar_last4": "1234",
        "address": CARD_ADDR,
    }
    base.update(over)
    return base


async def _manual(day_id, phone="9876500001", **fields):
    body = RegisterBody(
        full_name=fields.pop("full_name", CARD_NAME),
        age=fields.pop("age", 51),
        phone=fields.pop("phone", phone),
        camp_day_id=str(day_id),
        manual_entry=True,
        **fields,
    )
    result = await desk_register(body, _Request(), actor=ACTOR, background_tasks=None)
    return result["registration"]


def _assert_silent(out, stored, expected_name=CARD_NAME):
    assert out["outcome"] == "arrived"
    assert out["overwritten"] is True
    assert stored["full_name"] == expected_name
    assert stored["aadhaar_scanned"] is True
    assert stored["arrived_at"] is not None
    assert stored["manual_entry"] is False


class TestMaterialDiffUnit:
    def test_empty_stored_is_trivial(self):
        assert _material_diff(card_dict(), {
            "full_name": "", "age": None, "gender": "", "dob": None,
            "aadhaar_last4": "", "address": None,
        }) == []

    def test_address_is_always_trivial(self):
        assert _material_diff(card_dict(), {
            **card_dict(), "address": "a different village",
        }) == []

    def test_name_case_spacing_and_token_order_are_trivial(self):
        assert _material_diff(card_dict(full_name="Ramesh Kumar"), {
            **card_dict(), "full_name": "ramesh  kumar.",
        }) == []
        assert _material_diff(card_dict(full_name="Ramesh Kumar"), {
            **card_dict(), "full_name": "Kumar Ramesh",
        }) == []

    def test_name_material_when_tokens_differ(self):
        diff = _material_diff(card_dict(full_name="Sunita Devi"), {
            **card_dict(), "full_name": "Ramesh Kumar",
        })
        assert [d["field"] for d in diff] == ["full_name"]

    def test_age_within_one_year_is_trivial_else_material(self):
        assert _material_diff(card_dict(age=51), {**card_dict(), "age": 50}) == []
        assert _material_diff(card_dict(age=51), {**card_dict(), "age": 52}) == []
        diff = _material_diff(card_dict(age=51), {**card_dict(), "age": 49})
        assert [d["field"] for d in diff] == ["age"]

    def test_gender_first_char_trivial_else_material(self):
        assert _material_diff(card_dict(gender="F"), {**card_dict(), "gender": "female"}) == []
        assert _material_diff(card_dict(gender="M"), {**card_dict(), "gender": "m"}) == []
        diff = _material_diff(card_dict(gender="F"), {**card_dict(), "gender": "M"})
        assert [d["field"] for d in diff] == ["gender"]

    def test_dob_and_last4_strip_equal_else_material(self):
        assert _material_diff(card_dict(dob="1975-06-14"), {
            **card_dict(), "dob": " 1975-06-14 ",
        }) == []
        assert _material_diff(card_dict(), {**card_dict(), "aadhaar_last4": "1234"}) == []
        diff = _material_diff(card_dict(dob="1975-06-14"), {
            **card_dict(), "dob": "1970-01-01",
        })
        assert [d["field"] for d in diff] == ["dob"]
        diff = _material_diff(card_dict(), {**card_dict(), "aadhaar_last4": "9999"})
        assert [d["field"] for d in diff] == ["aadhaar_last4"]


class TestScanTrivialAndMaterial:
    def test_name_case_checks_in_silently(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _camp_id, (day_id,) = await _seed_camp(mock_db)
            reg = await _manual(day_id, full_name="ramesh kumar", aadhaar_last4="1234",
                                dob=CARD_DOB, gender="F")
            out = await scan(ScanBody(payload=payload(name="Ramesh Kumar")), actor=ACTOR)
            stored = await mock_db.patients.find_one({"_id": ObjectId(reg["id"])})
            _assert_silent(out, stored, expected_name="Ramesh Kumar")
        asyncio.run(run())

    def test_name_token_order_checks_in_silently(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _camp_id, (day_id,) = await _seed_camp(mock_db)
            reg = await _manual(day_id, full_name="Kumar Ramesh", aadhaar_last4="1234",
                                dob=CARD_DOB, gender="F")
            out = await scan(ScanBody(payload=payload(name="Ramesh Kumar")), actor=ACTOR)
            stored = await mock_db.patients.find_one({"_id": ObjectId(reg["id"])})
            _assert_silent(out, stored, expected_name="Ramesh Kumar")
        asyncio.run(run())

    def test_material_name_is_mismatch_review(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _camp_id, (day_id,) = await _seed_camp(mock_db)
            await _manual(day_id, full_name="Ramesh Kumar", aadhaar_last4="1234",
                          dob=CARD_DOB, gender="F", age=51)
            out = await scan(ScanBody(payload=payload()), actor=ACTOR)
            assert out["outcome"] == "mismatch_review"
            assert [d["field"] for d in out["diff"]] == ["full_name"]
            stored = await mock_db.patients.find_one({"_id": ObjectId(out["registration"]["id"])})
            assert stored["full_name"] == "Ramesh Kumar"
            assert stored["arrived_at"] is None
        asyncio.run(run())

    def test_age_within_one_year_checks_in_silently(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _camp_id, (day_id,) = await _seed_camp(mock_db)
            reg = await _manual(day_id, age=50, aadhaar_last4="1234", dob=CARD_DOB, gender="F")
            out = await scan(ScanBody(payload=payload()), actor=ACTOR)
            stored = await mock_db.patients.find_one({"_id": ObjectId(reg["id"])})
            _assert_silent(out, stored)
            assert stored["age"] == 51
        asyncio.run(run())

    def test_age_two_years_apart_is_mismatch_review(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _camp_id, (day_id,) = await _seed_camp(mock_db)
            await _manual(day_id, age=48, aadhaar_last4="1234", dob=CARD_DOB, gender="F")
            out = await scan(ScanBody(payload=payload()), actor=ACTOR)
            assert out["outcome"] == "mismatch_review"
            assert [d["field"] for d in out["diff"]] == ["age"]
        asyncio.run(run())

    def test_gender_case_checks_in_silently(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _camp_id, (day_id,) = await _seed_camp(mock_db)
            reg = await _manual(day_id, gender="female", aadhaar_last4="1234", dob=CARD_DOB)
            out = await scan(ScanBody(payload=payload()), actor=ACTOR)
            stored = await mock_db.patients.find_one({"_id": ObjectId(reg["id"])})
            _assert_silent(out, stored)
            assert stored["gender"] == "F"
        asyncio.run(run())

    def test_different_gender_is_mismatch_review(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _camp_id, (day_id,) = await _seed_camp(mock_db)
            await _manual(day_id, gender="M", aadhaar_last4="1234", dob=CARD_DOB)
            out = await scan(ScanBody(payload=payload()), actor=ACTOR)
            assert out["outcome"] == "mismatch_review"
            assert [d["field"] for d in out["diff"]] == ["gender"]
        asyncio.run(run())

    def test_different_dob_is_mismatch_review(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _camp_id, (day_id,) = await _seed_camp(mock_db)
            await _manual(day_id, aadhaar_last4="1234", dob="1970-01-01", gender="F")
            out = await scan(ScanBody(payload=payload()), actor=ACTOR)
            assert out["outcome"] == "mismatch_review"
            assert [d["field"] for d in out["diff"]] == ["dob"]
        asyncio.run(run())

    def test_empty_and_address_differences_check_in_silently(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _camp_id, (day_id,) = await _seed_camp(mock_db)
            reg = await _manual(day_id, aadhaar_last4="1234", dob=CARD_DOB, address="village")
            out = await scan(ScanBody(payload=payload()), actor=ACTOR)
            stored = await mock_db.patients.find_one({"_id": ObjectId(reg["id"])})
            _assert_silent(out, stored)
            assert stored["address"] == CARD_ADDR
            assert stored["gender"] == "F"
        asyncio.run(run())

    def test_two_manual_matches_stay_ambiguous(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            camp_id, (day_id,) = await _seed_camp(mock_db)
            a = await _manual(day_id, aadhaar_last4="1234", dob=CARD_DOB)
            await mock_db.patients.insert_one({
                "_id": ObjectId(), "camp_id": camp_id, "camp_day_id": day_id, "reg_no": 999,
                "full_name": CARD_NAME, "full_name_normalized": "sunita devi",
                "age": 51, "aadhaar_last4": "1234", "dob": CARD_DOB,
                "aadhaar_scanned": False, "manual_entry": True,
                "queue_status": "registered", "arrived_at": None, "patient_qr": "dup-qr",
            })
            out = await scan(ScanBody(payload=payload()), actor=ACTOR)
            assert out["outcome"] == "ambiguous"
            assert {r["reg_no"] for r in out["registrations"]} == {a["reg_no"], 999}
        asyncio.run(run())
