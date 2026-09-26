from uuid import uuid4
import asyncio

import pytest
from bson import ObjectId
from fastapi import HTTPException

from helpers import is_dummy_phone, normalize_name, normalize_phone
from models import RegisterBody
from routes_registration import _create_registration
from seed import run_camp, seed_camp


def _body(day_id, **fields):
    return RegisterBody(camp_day_id=str(day_id), **{"full_name": "Test User", "phone": "9876543210", "age": 30, "manual_reason": "no_card", **fields})


async def _staff_register(body):
    return await _create_registration(body, actor_id=ObjectId(), is_self=False, request=None)


def test_no_active_camp_is_a_409(monkeypatch):
    async def body(database):
        with pytest.raises(HTTPException) as exc:
            await _staff_register(_body(ObjectId()))
        assert exc.value.status_code == 409
        assert exc.value.detail["message"] == "No active camp"

    run_camp(monkeypatch, body)


def test_a_day_outside_the_active_camp_is_a_404(monkeypatch):
    async def body(database):
        await seed_camp(database, days=())
        with pytest.raises(HTTPException) as exc:
            await _staff_register(_body(ObjectId()))
        assert exc.value.status_code == 404
        assert exc.value.detail["message"] == "Camp day not found"

    run_camp(monkeypatch, body)


def test_a_replayed_request_id_returns_the_first_registration_even_concurrently(monkeypatch):
    async def body(database):
        _, (day_id,) = await seed_camp(database)
        request = _body(day_id, full_name="Concurrency User", age=28, registration_request_id=str(uuid4()))
        first, created = await _staff_register(request)
        assert created is True
        replay, created = await _staff_register(request)
        assert created is False
        assert replay["reg_no"] == first["reg_no"]
        for patient, created in await asyncio.gather(*[_staff_register(request) for _ in range(5)]):
            assert created is False
            assert patient["reg_no"] == first["reg_no"]
        assert await database.patients.count_documents({}) == 1

    run_camp(monkeypatch, body)


def test_name_age_phone_duplicate_matches_after_normalising(monkeypatch):
    async def body(database):
        _, (day_id,) = await seed_camp(database)
        await _staff_register(_body(day_id, full_name="Deepak Verma", phone="9876512345", age=38))
        with pytest.raises(HTTPException) as exc:
            await _staff_register(_body(day_id, full_name="  deepak   verma  ", phone="+91-98765-12345", age=38))
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "DUPLICATE_IN_CAMP"
        assert await database.patients.count_documents({}) == 1

    run_camp(monkeypatch, body)


def test_phone_normalization_variations():
    assert normalize_phone("+919876543210") == "9876543210"
    assert normalize_phone("+91-98765-43210") == "9876543210"
    assert normalize_phone("09876543210") == "9876543210"
    assert normalize_phone("98765 43210") == "9876543210"
    assert normalize_phone("98765-43210") == "9876543210"
    assert normalize_phone("(+91) 9876543210") == "9876543210"
    assert normalize_phone("98765") is None
    assert normalize_phone("98765432101") is None
    assert normalize_phone("") is None
    assert normalize_phone(None) is None


def test_dummy_phone_detection():
    assert is_dummy_phone("9999999999") is True
    assert is_dummy_phone("0000000000") is True
    assert is_dummy_phone("1111111111") is True
    assert is_dummy_phone("12345") is True
    assert is_dummy_phone("") is True
    assert is_dummy_phone("9876543210") is False
    assert is_dummy_phone("9811223344") is False


def test_name_normalization_strips_punctuation_and_whitespace():
    assert normalize_name("  Ravi   Kumar  ") == "ravi kumar"
    assert normalize_name("DR.  ANITA   DESHMUKH") == "dr anita deshmukh"
    assert normalize_name("O'Connor-Smith") == "oconnorsmith"
    assert normalize_name("   ") == ""
    assert normalize_name(None) == ""
