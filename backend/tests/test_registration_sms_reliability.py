import pytest
from bson import ObjectId
from fastapi import HTTPException
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.errors import DuplicateKeyError

import routes_clinical
import routes_desk
import routes_registration
import msg91
from models import RegisterBody
from seed import send_patient_sms, CLINICAL, TOMORROW, patient_doc, run_camp, seed_camp


def _fail_ledger_updates(monkeypatch, failing):
    real = AsyncCollection.update_one

    async def update_one(self, filter, update, *args, **kwargs):
        if self.name == "reminder_ledger" and failing(update):
            raise RuntimeError("ledger unavailable")
        return await real(self, filter, update, *args, **kwargs)

    monkeypatch.setattr(AsyncCollection, "update_one", update_one)


@pytest.mark.parametrize("entry", ["e6d9244e-8d6f-40c1-8753-5717cda5d38e", "SNP:E6D9244E-8D6F-40C1-8753-5717CDA5D38E"])
def test_legacy_patient_qr_resolves_at_desk_and_clinical_lookup(monkeypatch, entry):
    async def run(database):
        camp_id, (day_id,) = await seed_camp(database)
        patient_id = ObjectId()
        await database.patients.insert_one(patient_doc(
            _id=patient_id, camp_id=camp_id, camp_day_id=day_id,
            patient_qr="e6d9244e-8d6f-40c1-8753-5717cda5d38e", queue_status="registered",
        ))
        patient = await routes_desk._resolve(entry)
        assert patient and patient["_id"] == patient_id
        with pytest.raises(HTTPException) as exc:
            await routes_clinical.clinical_lookup({"value": entry}, CLINICAL)
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "NOT_ARRIVED"

    run_camp(monkeypatch, run)


@pytest.mark.parametrize("key", ["patient_qr", "reg_no"])
def test_registration_retries_only_patient_code_collisions(monkeypatch, key):
    codes = iter(["AAAAAAAA", "BBBBBBBB"])
    issued = []

    def next_code():
        issued.append(next(codes))
        return issued[-1]

    monkeypatch.setattr(routes_registration, "new_patient_code", next_code)

    async def run(database):
        camp_id, (day_id,) = await seed_camp(database)
        await database.counters.insert_one({"_id": "reg_no", "seq": 41})
        taken = {"patient_qr": "AAAAAAAA", "reg_no": 42}
        await database.patients.insert_one(patient_doc(camp_id=ObjectId(), **{key: taken[key]}))
        body = RegisterBody(full_name="Patient", age=40, camp_day_id=str(day_id), manual_reason="no_card")
        if key == "patient_qr":
            patient, created = await routes_registration._create_registration(body, None, False, None)
            assert created and patient["patient_qr"] == "BBBBBBBB"
            assert issued == ["AAAAAAAA", "BBBBBBBB"]
            assert (await database.camp_days.find_one({"_id": day_id}))["booked"] == 1
            assert await database.patients.count_documents({"camp_id": camp_id}) == 1
        else:
            with pytest.raises(DuplicateKeyError):
                await routes_registration._create_registration(body, None, False, None)
            assert issued == ["AAAAAAAA"]
            assert (await database.camp_days.find_one({"_id": day_id}))["booked"] == 0

    run_camp(monkeypatch, run)


async def _patient_of_a_numbered_camp(database):
    camp_id = ObjectId()
    await database.camps.insert_one({"_id": camp_id, "name": "C", "venue": "Hall", "camp_number": 162})
    return {"_id": ObjectId(), "camp_id": camp_id, "phone": "9876543210", "reg_no": 42}


@pytest.mark.parametrize("provider_succeeds", [True, False])
def test_sms_ledger_failure_does_not_escape_or_resend_an_accepted_message(monkeypatch, provider_succeeds, sms_provider):
    sms_provider.switch_on()
    calls = []

    def send(*args):
        calls.append(args)
        if not provider_succeeds:
            raise msg91.Unsent("connection refused")
        return "accepted"

    sms_provider.outcome = send
    _fail_ledger_updates(monkeypatch, lambda update: True)

    async def run(database):
        patient = await _patient_of_a_numbered_camp(database)
        assert await send_patient_sms(database, patient, "registration", TOMORROW, "Hall") is provider_succeeds
        assert not await send_patient_sms(database, patient, "registration", TOMORROW, "Hall")
        assert len(calls) == 1
        assert (await database.reminder_ledger.find_one({}))["status"] == "pending"

    run_camp(monkeypatch, run)


def test_accepted_sms_is_not_marked_failed_when_receipt_persistence_fails(monkeypatch, sms_provider):
    sms_provider.switch_on()
    calls = []
    sms_provider.outcome = lambda *args: calls.append(args) or "accepted"
    _fail_ledger_updates(monkeypatch, lambda update: update["$set"]["status"] == "sent")

    async def run(database):
        patient = await _patient_of_a_numbered_camp(database)
        assert await send_patient_sms(database, patient, "registration", TOMORROW, "Hall")
        assert not await send_patient_sms(database, patient, "registration", TOMORROW, "Hall")
        assert len(calls) == 1
        assert (await database.reminder_ledger.find_one({}))["status"] == "pending"

    run_camp(monkeypatch, run)
