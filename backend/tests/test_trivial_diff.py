"""Trivial diff: silent Aadhaar overwrite + Arrival vs Mismatch review."""
from xml.etree.ElementTree import Element, tostring

from bson import ObjectId

from models import ScanBody
from routes_desk import _material_diff, print_prescription, scan
from seed import ACTOR, register, run_camp, seed_camp

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


async def _manual(day_id, **fields):
    return await register(day_id, manual_entry=True, **fields)


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


class TestCardClearsTheIdentityHold:
    def test_a_door_scan_that_overwrites_a_manual_entry_can_print(self, monkeypatch):
        async def run(database):
            _camp_id, (day_id,) = await seed_camp(database)
            reg = await _manual(day_id, aadhaar_last4="1234", dob=CARD_DOB, gender="F")
            assert reg["identity_recheck_required"] is True
            out = await scan(ScanBody(payload=payload()), actor=ACTOR)
            assert out["overwritten"] is True
            assert out["registration"]["identity_recheck_required"] is False
            printed = await print_prescription(reg["id"], actor=ACTOR)
            assert printed["registration"]["printed_at"]
        run_camp(monkeypatch, run)

    def test_a_desk_registration_that_overwrites_a_manual_entry_clears_the_hold(self, monkeypatch):
        async def run(database):
            _camp_id, (day_id,) = await seed_camp(database)
            reg = await _manual(day_id, aadhaar_last4="1234", dob=CARD_DOB, gender="F")
            again = await register(day_id, aadhaar_scanned=True, qr_payload=payload())
            assert again["id"] == reg["id"]
            stored = await database.patients.find_one({"_id": ObjectId(reg["id"])})
            assert stored["aadhaar_scanned"] is True
            assert stored["identity_recheck_required"] is False
        run_camp(monkeypatch, run)


class TestScanTrivialAndMaterial:
    def test_name_case_checks_in_silently(self, monkeypatch):
        async def run(database):
            _camp_id, (day_id,) = await seed_camp(database)
            reg = await _manual(day_id, full_name="ramesh kumar", aadhaar_last4="1234",
                                dob=CARD_DOB, gender="F")
            out = await scan(ScanBody(payload=payload(name="Ramesh Kumar")), actor=ACTOR)
            stored = await database.patients.find_one({"_id": ObjectId(reg["id"])})
            _assert_silent(out, stored, expected_name="Ramesh Kumar")
        run_camp(monkeypatch, run)

    def test_name_token_order_checks_in_silently(self, monkeypatch):
        async def run(database):
            _camp_id, (day_id,) = await seed_camp(database)
            reg = await _manual(day_id, full_name="Kumar Ramesh", aadhaar_last4="1234",
                                dob=CARD_DOB, gender="F")
            out = await scan(ScanBody(payload=payload(name="Ramesh Kumar")), actor=ACTOR)
            stored = await database.patients.find_one({"_id": ObjectId(reg["id"])})
            _assert_silent(out, stored, expected_name="Ramesh Kumar")
        run_camp(monkeypatch, run)

    def test_material_name_is_mismatch_review(self, monkeypatch):
        async def run(database):
            _camp_id, (day_id,) = await seed_camp(database)
            await _manual(day_id, full_name="Ramesh Kumar", aadhaar_last4="1234",
                          dob=CARD_DOB, gender="F", age=51)
            out = await scan(ScanBody(payload=payload()), actor=ACTOR)
            assert out["outcome"] == "mismatch_review"
            assert [d["field"] for d in out["diff"]] == ["full_name"]
            stored = await database.patients.find_one({"_id": ObjectId(out["registration"]["id"])})
            assert stored["full_name"] == "Ramesh Kumar"
            assert stored["arrived_at"] is None
        run_camp(monkeypatch, run)

    def test_age_within_one_year_checks_in_silently(self, monkeypatch):
        async def run(database):
            _camp_id, (day_id,) = await seed_camp(database)
            reg = await _manual(day_id, age=50, aadhaar_last4="1234", dob=CARD_DOB, gender="F")
            out = await scan(ScanBody(payload=payload()), actor=ACTOR)
            stored = await database.patients.find_one({"_id": ObjectId(reg["id"])})
            _assert_silent(out, stored)
            assert stored["age"] == 51
        run_camp(monkeypatch, run)

    def test_age_two_years_apart_is_mismatch_review(self, monkeypatch):
        async def run(database):
            _camp_id, (day_id,) = await seed_camp(database)
            await _manual(day_id, age=48, aadhaar_last4="1234", dob=CARD_DOB, gender="F")
            out = await scan(ScanBody(payload=payload()), actor=ACTOR)
            assert out["outcome"] == "mismatch_review"
            assert [d["field"] for d in out["diff"]] == ["age"]
        run_camp(monkeypatch, run)

    def test_gender_case_checks_in_silently(self, monkeypatch):
        async def run(database):
            _camp_id, (day_id,) = await seed_camp(database)
            reg = await _manual(day_id, gender="female", aadhaar_last4="1234", dob=CARD_DOB)
            out = await scan(ScanBody(payload=payload()), actor=ACTOR)
            stored = await database.patients.find_one({"_id": ObjectId(reg["id"])})
            _assert_silent(out, stored)
            assert stored["gender"] == "F"
        run_camp(monkeypatch, run)

    def test_different_gender_is_mismatch_review(self, monkeypatch):
        async def run(database):
            _camp_id, (day_id,) = await seed_camp(database)
            await _manual(day_id, gender="M", aadhaar_last4="1234", dob=CARD_DOB)
            out = await scan(ScanBody(payload=payload()), actor=ACTOR)
            assert out["outcome"] == "mismatch_review"
            assert [d["field"] for d in out["diff"]] == ["gender"]
        run_camp(monkeypatch, run)

    def test_different_dob_is_mismatch_review(self, monkeypatch):
        async def run(database):
            _camp_id, (day_id,) = await seed_camp(database)
            await _manual(day_id, aadhaar_last4="1234", dob="1970-01-01", gender="F")
            out = await scan(ScanBody(payload=payload()), actor=ACTOR)
            assert out["outcome"] == "mismatch_review"
            assert [d["field"] for d in out["diff"]] == ["dob"]
        run_camp(monkeypatch, run)

    def test_empty_and_address_differences_check_in_silently(self, monkeypatch):
        async def run(database):
            _camp_id, (day_id,) = await seed_camp(database)
            reg = await _manual(day_id, aadhaar_last4="1234", dob=CARD_DOB, address="village")
            out = await scan(ScanBody(payload=payload()), actor=ACTOR)
            stored = await database.patients.find_one({"_id": ObjectId(reg["id"])})
            _assert_silent(out, stored)
            assert stored["address"] == CARD_ADDR
            assert stored["gender"] == "F"
        run_camp(monkeypatch, run)

    def test_two_manual_matches_stay_ambiguous(self, monkeypatch):
        async def run(database):
            camp_id, (day_id,) = await seed_camp(database)
            a = await _manual(day_id, aadhaar_last4="1234", dob=CARD_DOB)
            await database.patients.insert_one({
                "camp_id": camp_id, "camp_day_id": day_id, "reg_no": 999,
                "full_name": CARD_NAME, "full_name_normalized": "sunita devi",
                "age": 51, "aadhaar_last4": "1234", "dob": CARD_DOB,
                "aadhaar_scanned": False, "manual_entry": True,
                "queue_status": "registered", "arrived_at": None, "patient_qr": "dup-qr",
            })
            out = await scan(ScanBody(payload=payload()), actor=ACTOR)
            assert out["outcome"] == "ambiguous"
            assert {r["reg_no"] for r in out["registrations"]} == {a["reg_no"], 999}
        run_camp(monkeypatch, run)
