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


def test_public_manual_review_forces_truthful_provenance_and_preserves_replay(public_client):
    client, day_id = public_client
    body = {
        'full_name': 'Reviewed Patient', 'age': 45, 'gender': 'F', 'phone': '9876543210',
        'camp_day_id': day_id, 'aadhaar_last4': '1234', 'aadhaar_scanned': True,
        'manual_entry': False, 'is_self_registered': False, 'registration_request_id': 'review-1',
    }
    response = client.post('/api/self-register', json=body)
    assert response.status_code == 200, response.text
    patient = response.json()['registration']
    assert patient['manual_entry'] is True
    assert patient['aadhaar_scanned'] is False
    assert patient['identity_recheck_required'] is True
    assert patient['is_self_registered'] is True
    assert patient['person_id'] is None
    retry = client.post('/api/self-register', json=body)
    assert retry.status_code == 200, retry.text
    assert retry.json()['receipt']['reg_no'] == response.json()['receipt']['reg_no']
    duplicate = client.post('/api/self-register', json={**body, 'registration_request_id': 'review-2'})
    assert duplicate.status_code == 409
    assert 'registration' not in duplicate.json()['detail']


@pytest.mark.parametrize('fields', [
    {'full_name': ' '}, {'age': -1}, {'age': 131}, {'dob': '2030-13-42'},
    {'dob': '2999-01-01'}, {'dob': '1980-01-01', 'age': 12}, {'aadhaar_last4': '123456781234'},
    {'dob': '19800101'}, {'dob': '1980-W01-1'},
])
def test_public_manual_fields_are_validated_before_registration(public_client, fields):
    client, day_id = public_client
    body = {'full_name': 'Reviewed Patient', 'age': 45, 'phone': '9876543210', 'camp_day_id': day_id, **fields}
    response = client.post('/api/self-register', json=body)
    assert response.status_code == 400, response.text


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
        asyncio.run(desk_register(body, _Request(), actor=ACTOR))
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
