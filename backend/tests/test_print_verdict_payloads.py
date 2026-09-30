"""The desk payloads that reach PatientRow, ArrivedCard and Lookalikes carry the Print verdict, computed once per request."""

from uuid import uuid4

import pytest
from bson import ObjectId
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

import printing
import routes_camps
import routes_registration
from conftest import CommandLog
from models import NoCardBody, PrintWindowBody, QrLookupBody, ScanBody, ScanConfirmBody
from routes_desk import arrive, lookup, preview_prescription, print_prescription, record_no_card_print, scan, scan_confirm
from routes_registration import name_search
from seed import ACTOR, ADMIN, CARD, TOMORROW, patient_doc, register, run_camp, seed_camp

VERDICT_KEYS = {"allowed", "code", "stage"}
SCANNED = dict(full_name="Sunita Devi", gender="F", dob="1975-06-14", aadhaar_last4="1234", aadhaar_scanned=True)


async def _matches(database, registration):
    stored = await database.patients.find_one({"_id": ObjectId(registration["id"])})
    camp = await database.camps.find_one({"is_active": True})
    _days, state = await printing.load(database, camp)
    assert set(registration["print"]) == VERDICT_KEYS
    assert registration["print"] == printing.verdict(stored, state)


async def _lookup(day_id):
    booked = await register(day_id, full_name="Kamla Bai", age=62, phone="9876500011")
    return [(await lookup(QrLookupBody(value=str(booked["reg_no"])), actor=ACTOR))["registration"]]


async def _search(day_id):
    await register(day_id, full_name="Kamla Bai", age=62, phone="9876500011")
    await register(day_id, full_name="Kamla Devi", age=40, phone="9876500012", at_door=True)
    results = (await name_search("Kamla", actor=ACTOR))["results"]
    assert len(results) == 2
    return results


async def _scan(day_id):
    await register(day_id, **SCANNED)
    out = await scan(ScanBody(payload=CARD), actor=ACTOR)
    assert out["outcome"] == "arrived"
    return [out["registration"]]


async def _scan_confirm(day_id):
    manual = await register(day_id, full_name="Sunita Devi", age=51, aadhaar_last4="1234")
    out = await scan_confirm(ScanConfirmBody(patient_id=manual["id"], payload=CARD), actor=ACTOR)
    assert out["outcome"] == "arrived"
    return [out["registration"]]


async def _no_card_recorded(day_id):
    booked = await register(day_id, full_name="Kamla Bai", age=62, phone="9876500011")
    return [(await record_no_card_print(NoCardBody(patient_id=booked["id"], reason="no_card"), actor=ACTOR))["registration"]]


async def _no_card_already_arrived(day_id):
    walk_in = await register(day_id, full_name="Kamla Bai", age=62, phone="9876500011", at_door=True)
    return [(await record_no_card_print(NoCardBody(patient_id=walk_in["id"], reason="no_card"), actor=ACTOR))["registration"]]


async def _register_created(day_id):
    return [await register(day_id, full_name="Kamla Bai", age=62, phone="9876500011")]


async def _register_at_the_door(day_id):
    return [await register(day_id, full_name="Kamla Bai", age=62, phone="9876500011", at_door=True)]


async def _register_replayed(day_id):
    request_id = str(uuid4())
    fields = dict(full_name="Kamla Bai", age=62, phone="9876500011", registration_request_id=request_id)
    first = await register(day_id, **fields)
    again = await register(day_id, **fields)
    assert again["id"] == first["id"]
    return [first, again]


async def _register_overwrite(day_id):
    manual = await register(day_id, manual_entry=True, full_name="Sunita Devi", age=51, aadhaar_last4="1234", dob="1975-06-14", gender="F")
    overwritten = await register(day_id, aadhaar_scanned=True, qr_payload=CARD)
    assert overwritten["id"] == manual["id"]
    return [overwritten]


async def _register_lookalikes(day_id):
    await register(day_id, full_name="Ram Kumar", age=60, phone="9876500011")
    with pytest.raises(HTTPException) as exc:
        await register(day_id, full_name="kumar RAM", age=62, phone="9876500012")
    assert exc.value.detail["code"] == "LOOKALIKES"
    return exc.value.detail["registrations"]


SCENARIOS = {
    "lookup": _lookup,
    "search": _search,
    "scan": _scan,
    "scan_confirm": _scan_confirm,
    "no_card_recorded": _no_card_recorded,
    "no_card_already_arrived": _no_card_already_arrived,
    "register_created": _register_created,
    "register_at_the_door": _register_at_the_door,
    "register_replayed": _register_replayed,
    "register_overwrite": _register_overwrite,
    "register_lookalikes": _register_lookalikes,
}


@pytest.mark.parametrize("source", SCENARIOS)
def test_desk_registration_payloads_carry_a_matching_verdict(monkeypatch, source):
    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database)
        registrations = await SCENARIOS[source](day_id)
        assert registrations
        for registration in registrations:
            await _matches(database, registration)

    run_camp(monkeypatch, run)


def test_arrive_and_print_payloads_carry_no_verdict(monkeypatch):
    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database)
        booked = await register(day_id, full_name="Kamla Bai", age=62, phone="9876500011")
        await record_no_card_print(NoCardBody(patient_id=booked["id"], reason="no_card"), actor=ACTOR)
        arrived = await arrive(booked["id"], actor=ACTOR)
        preview = await preview_prescription(booked["id"], actor=ACTOR)
        printed = await print_prescription(booked["id"], actor=ACTOR)
        assert arrived["prescription"] and printed["registration"]["printed_at"]
        for payload in (arrived, preview, printed):
            assert "print" not in payload["registration"]

    run_camp(monkeypatch, run)


def test_scan_outcomes_the_desk_does_not_render_as_rows_carry_no_verdict(monkeypatch):
    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database)
        await register(day_id, full_name="Sunita Devi", age=48, aadhaar_last4="1234", dob="1975-06-14", gender="F")
        out = await scan(ScanBody(payload=CARD), actor=ACTOR)
        assert out["outcome"] == "mismatch_review"
        assert "print" not in out["registration"]

    run_camp(monkeypatch, run)


def test_search_reads_camp_days_once_for_many_rows(monkeypatch):
    log = CommandLog()

    def camp_day_reads():
        reads = [c for c in log.commands if c == ("find", "camp_days")]
        log.commands.clear()
        return len(reads)

    async def run(database):
        camp_id, (day_id,) = await seed_camp(database)
        await database.patients.insert_many([
            patient_doc(
                camp_id=camp_id, camp_day_id=day_id, queue_status="registered", full_name=f"Kamla {i}",
                full_name_normalized=f"kamla n{i}", phone_normalized="9876500001",
            )
            for i in range(25)
        ])
        camp_day_reads()
        by_name = (await name_search("Kamla", actor=ACTOR))["results"]
        assert len(by_name) == 25 and all(set(r["print"]) == VERDICT_KEYS for r in by_name)
        assert camp_day_reads() == 1
        by_phone = (await name_search("9876500001", actor=ACTOR))["results"]
        assert len(by_phone) == 25 and all("print" in r for r in by_phone)
        assert camp_day_reads() == 1
        assert (await name_search("Zzz", actor=ACTOR))["results"] == []
        assert camp_day_reads() == 0
        with pytest.raises(HTTPException) as exc:
            await lookup(QrLookupBody(value="999999"), actor=ACTOR)
        assert exc.value.status_code == 404
        assert camp_day_reads() == 0

    run_camp(monkeypatch, run, listener=log)


def test_self_register_carries_no_verdict(monkeypatch):
    app = FastAPI()
    app.include_router(routes_registration.router)

    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database, days=(TOMORROW,))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.post("/api/self-register", json={
                "full_name": "Sunita Devi", "age": 51, "phone": "9876543210", "camp_day_id": str(day_id),
                "aadhaar_scanned": True, "qr_payload": CARD,
            })
        assert response.status_code == 200, response.text
        assert "print" not in response.json()["registration"]

    run_camp(monkeypatch, run)


def test_a_door_scan_with_the_window_closed_afterwards_reports_it(monkeypatch):
    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database)
        booked = await register(day_id, **SCANNED)
        arrived = (await scan(ScanBody(payload=CARD), actor=ACTOR))["registration"]
        assert arrived["print"] == {"allowed": True, "code": None, "stage": "arrived"}

        await routes_camps.toggle_print_window(str(day_id), PrintWindowBody(mode="disable"), actor=ADMIN)
        found = (await lookup(QrLookupBody(value=str(booked["reg_no"])), actor=ACTOR))["registration"]
        assert found["print"] == {"allowed": False, "code": "PRINT_WINDOW_CLOSED", "stage": "arrived"}

    run_camp(monkeypatch, run)
