import pytest
from bson import ObjectId
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

import routes_registration
from conftest import run_db
from helpers import now_utc
from models import RegisterBody
from routes_registration import _validate_manual_identity, desk_register
from seed import ACTOR, TOMORROW, Request, recorder, run_camp, seed_camp


def _self_register(monkeypatch, **fields):
    sent = recorder(monkeypatch)
    routes_registration._rl.clear()
    app = FastAPI()
    app.include_router(routes_registration.router)

    async def body(database):
        _camp_id, (day_id,) = await seed_camp(database, days=(TOMORROW,))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.post("/api/self-register", json={
                'full_name': 'Reviewed Patient', 'age': 45, 'phone': '9876543210', 'camp_day_id': str(day_id),
                **fields,
            })
        assert await database.patients.count_documents({}) == 0
        assert sent == []
        return response

    return run_camp(monkeypatch, body)


def test_public_registration_without_a_readable_qr_is_refused(monkeypatch):
    response = _self_register(
        monkeypatch, gender='F', aadhaar_last4='1234', aadhaar_scanned=True,
        manual_entry=False, is_self_registered=False, registration_request_id='8f14e45f-ceea-4671-a1d2-5a2b3c4d5e6f',
    )
    assert response.status_code == 400, response.text
    assert response.json()['detail']['code'] == 'AADHAAR_QR_REQUIRED'


@pytest.mark.parametrize('fields', [
    {}, {'qr_payload': ''}, {'qr_payload': 'not-an-aadhaar-qr'},
    {'aadhaar_scanned': True, 'manual_entry': False, 'manual_exception': True},
    {'dob': '1980-01-01', 'aadhaar_last4': '1234', 'gender': 'F'},
])
def test_no_client_flag_mints_a_public_registration_without_a_qr(monkeypatch, fields):
    response = _self_register(monkeypatch, **fields)
    assert response.status_code == 400, response.text
    assert response.json()['detail']['code'] == 'AADHAAR_QR_REQUIRED'


@pytest.mark.parametrize('fields', [
    {'dob': '19800101'}, {'dob': '14/06/1975'}, {'dob': 'Year of Birth 1975'},
    {'dob': '2999-01-01'}, {'dob': '2030-13-42'}, {'age': None, 'dob': None},
])
def test_desk_reviewed_details_reject_unstorable_dates_of_birth(fields):
    body = RegisterBody(
        full_name='Reviewed Patient', phone='9876500001', manual_entry=True,
        camp_day_id=str(ObjectId()), age=fields.get('age', 45), dob=fields.get('dob'),
    )

    async def run(database):
        with pytest.raises(HTTPException) as error:
            await desk_register(body, Request(), actor=ACTOR, background_tasks=None)
        assert error.value.status_code == 400
        assert await database.patients.count_documents({}) == 0

    run_db(run)


@pytest.mark.parametrize('dob,stored', [('1975', '1975-01-01'), ('1975-06-14', '1975-06-14')])
def test_desk_reviewed_year_only_birth_year_is_accepted_and_dates_age(dob, stored):
    body = RegisterBody(full_name='Reviewed Patient', phone='9876500001', manual_entry=True, gender='F',
                        camp_day_id=str(ObjectId()), age=None, dob=dob)
    _validate_manual_identity(body, now_utc())
    assert body.dob == stored
    assert body.age is not None and 0 <= body.age <= 130
