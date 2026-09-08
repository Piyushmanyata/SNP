import asyncio

import pytest
from bson import ObjectId
from fastapi import FastAPI
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
