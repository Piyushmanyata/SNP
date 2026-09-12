import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import pytest
from bson import ObjectId
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import routes_registration
from test_adversarial_challenger import setup_mock_db


@pytest.fixture
def public_client(monkeypatch):
    db = setup_mock_db(monkeypatch)
    camp_id, day_id = ObjectId(), ObjectId()

    async def seed():
        await db.camps.insert_one({'_id': camp_id, 'is_active': True, 'name': 'Test Camp', 'venue': 'Test Hall'})
        await db.camp_days.insert_one({'_id': day_id, 'camp_id': camp_id, 'day_date': '2030-01-01', 'seat_limit': 10, 'booked': 0})

    async def no_sms(*args, **kwargs):
        pass

    asyncio.run(seed())
    monkeypatch.setattr(routes_registration.sms, 'send_patient_sms', no_sms)
    routes_registration._rl.clear()
    app = FastAPI()
    app.include_router(routes_registration.router)
    with TestClient(app) as client:
        yield client, str(day_id)


def test_public_registration_without_a_readable_qr_is_refused(public_client):
    client, day_id = public_client
    body = {
        'full_name': 'Reviewed Patient', 'age': 45, 'gender': 'F', 'phone': '9876543210',
        'camp_day_id': day_id, 'aadhaar_last4': '1234', 'aadhaar_scanned': True,
        'manual_entry': False, 'is_self_registered': False, 'registration_request_id': 'review-1',
    }
    response = client.post('/api/self-register', json=body)
    assert response.status_code == 400, response.text
    assert response.json()['detail']['code'] == 'AADHAAR_QR_REQUIRED'


@pytest.mark.parametrize('fields', [
    {}, {'qr_payload': ''}, {'qr_payload': 'not-an-aadhaar-qr'},
    {'aadhaar_scanned': True, 'manual_entry': False, 'manual_exception': True},
    {'dob': '1980-01-01', 'aadhaar_last4': '1234', 'gender': 'F'},
])
def test_no_client_flag_mints_a_public_registration_without_a_qr(public_client, fields):
    client, day_id = public_client
    body = {'full_name': 'Reviewed Patient', 'age': 45, 'phone': '9876543210', 'camp_day_id': day_id, **fields}
    response = client.post('/api/self-register', json=body)
    assert response.status_code == 400, response.text
    assert response.json()['detail']['code'] == 'AADHAAR_QR_REQUIRED'


@pytest.mark.parametrize('fields', [
    {'dob': '19800101'}, {'dob': '14/06/1975'}, {'dob': 'Year of Birth 1975'},
    {'dob': '2999-01-01'}, {'dob': '2030-13-42'}, {'age': None, 'dob': None},
])
def test_desk_reviewed_details_reject_unstorable_dates_of_birth(monkeypatch, fields):
    from models import RegisterBody
    from routes_registration import desk_register
    from test_camp_lifecycle import ACTOR, _Request

    setup_mock_db(monkeypatch)
    body = RegisterBody(
        full_name='Reviewed Patient', phone='9876500001', manual_entry=True,
        camp_day_id=str(ObjectId()), age=fields.get('age', 45), dob=fields.get('dob'),
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(desk_register(body, _Request(), actor=ACTOR, background_tasks=None))
    assert error.value.status_code == 400


@pytest.mark.parametrize('dob,expected_age', [('1975', 2026 - 1975), ('1975-06-14', None)])
def test_desk_reviewed_year_only_birth_year_is_accepted_and_dates_age(monkeypatch, dob, expected_age):
    from models import RegisterBody
    from routes_registration import _validate_manual_identity
    from helpers import now_utc

    body = RegisterBody(full_name='Reviewed Patient', phone='9876500001', manual_entry=True,
                        camp_day_id=str(ObjectId()), age=None, dob=dob)
    _validate_manual_identity(body, now_utc())
    assert body.dob == dob
    assert body.age is not None and 0 <= body.age <= 130
