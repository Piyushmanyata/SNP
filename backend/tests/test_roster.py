"""Roster API is unregistered; new records attribute authenticated user ids only."""
import asyncio
import inspect
import os
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "snp_test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("AADHAAR_HASH_PEPPER", "test-pepper")
os.environ.setdefault("COOKIE_SECURE", "false")

from bson import ObjectId
from fastapi.testclient import TestClient

import db as db_module
import routes_auth
import routes_clinical
import routes_desk
import routes_registration
import routes_reports
import routes_staff
import security
import server as server_mod
from db import init_indexes
from models import FulfilmentBody, RegisterBody, ScanBody
from routes_clinical import record_fulfilment
from routes_desk import print_prescription, scan
from routes_registration import desk_register
from routes_reports import leaderboard
from security import hash_pin
from test_adversarial_challenger import MEDICINE, setup_mock_db
from test_camp_lifecycle import CARD, _Request, _mock, _seed_camp, _seen_patient_with_transcription

VOLUNTEER = {"_id": ObjectId(), "role": "volunteer", "name": "Desk 1"}
TEAM_LEAD = {"_id": ObjectId(), "role": "team_lead", "name": "Lead"}
ADMIN = {"_id": ObjectId(), "role": "admin", "name": "admin"}
CLINICAL = {"_id": ObjectId(), "role": "clinical_desk_operator", "name": "Rx 1"}


def _async_noop():
    async def _inner(*_a, **_k):
        return None
    return _inner


def _patch_db(monkeypatch, mock_db):
    mock_db = mock_db or setup_mock_db(monkeypatch)
    for mod in (
        db_module, routes_staff, routes_auth, routes_clinical, routes_reports,
        routes_desk, routes_registration, security,
    ):
        monkeypatch.setattr(mod, "get_db", lambda: mock_db)
    return mock_db


def _client(monkeypatch, mock_db):
    monkeypatch.setattr(server_mod, "init_indexes", _async_noop())
    monkeypatch.setattr(server_mod, "seed_admin", _async_noop())
    _patch_db(monkeypatch, mock_db)
    server_mod.app.router.on_startup.clear()
    return TestClient(server_mod.app, raise_server_exceptions=True)


async def _user(mock_db, actor, **extra):
    doc = {
        "_id": actor["_id"],
        "name": extra.pop("name", actor.get("name", actor["role"])),
        "pin_hash": hash_pin("2468"),
        "role": actor["role"],
        "disabled_at": None,
        **extra,
    }
    await mock_db.users.insert_one(doc)
    return doc


def _auth(actor):
    token = security.create_access_token(str(actor["_id"]), actor.get("name") or actor["role"], actor["role"])
    return {"Authorization": f"Bearer {token}"}


class TestRosterUnregistered:
    def test_roster_routes_are_not_registered(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            await _user(mock_db, ADMIN)
            client = _client(monkeypatch, mock_db)
            headers = _auth(ADMIN)
            listed = client.get("/api/roster", headers=headers)
            created = client.post(
                "/api/roster",
                json={"camp_id": str(ObjectId()), "names": ["Ramesh"]},
                headers=headers,
            )
            disabled = client.patch(f"/api/roster/{ObjectId()}/disable", headers=headers)
            enabled = client.patch(f"/api/roster/{ObjectId()}/enable", headers=headers)
            assert listed.status_code == 404
            assert created.status_code == 404
            assert disabled.status_code == 404
            assert enabled.status_code == 404
        asyncio.run(run())

    def test_init_indexes_does_not_create_roster_index(self):
        assert "roster.create_index" not in inspect.getsource(init_indexes)


class TestOnDeskVolunteerHeader:
    def test_volunteer_without_roster_header_is_not_refused(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            await _seed_camp(mock_db)
            await _user(mock_db, VOLUNTEER)
            client = _client(monkeypatch, mock_db)
            r = client.post(
                "/api/desk/scan",
                json={"payload": CARD},
                headers=_auth(VOLUNTEER),
            )
            assert r.status_code != 428
            assert r.status_code == 200
        asyncio.run(run())

    def test_team_lead_without_header_is_not_refused(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            await _seed_camp(mock_db)
            await _user(mock_db, TEAM_LEAD)
            client = _client(monkeypatch, mock_db)
            r = client.post(
                "/api/desk/scan",
                json={"payload": CARD},
                headers=_auth(TEAM_LEAD),
            )
            assert r.status_code != 428
            assert r.status_code == 200
            assert r.json()["outcome"] == "no_match"
        asyncio.run(run())


class TestAuthenticatedAttribution:
    def test_desk_register_writes_created_by_not_roster_id(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _patch_db(monkeypatch, mock_db)
            camp_id, (day_id,) = await _seed_camp(mock_db)
            result = await desk_register(RegisterBody(
                full_name="Sunita Devi", age=51, phone="9876500001",
                camp_day_id=str(day_id),
            ), _Request(), actor=VOLUNTEER)
            stored = await mock_db.patients.find_one(
                {"_id": ObjectId(result["registration"]["id"])},
            )
            assert stored["created_by"] == str(VOLUNTEER["_id"])
            assert "created_roster_id" not in stored
            assert "created_roster_id" not in result["registration"]
        asyncio.run(run())

    def test_scan_writes_arrived_by_not_roster_id(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _patch_db(monkeypatch, mock_db)
            camp_id, (day_id,) = await _seed_camp(mock_db)
            await desk_register(RegisterBody(
                full_name="Sunita Devi", gender="F", dob="1975-06-14",
                aadhaar_last4="1234", aadhaar_scanned=True, age=51,
                phone="9876500001", camp_day_id=str(day_id),
            ), _Request(), actor=VOLUNTEER)
            out = await scan(ScanBody(payload=CARD), actor=VOLUNTEER)
            assert out["outcome"] == "arrived"
            stored = await mock_db.patients.find_one(
                {"_id": ObjectId(out["registration"]["id"])},
            )
            assert stored["arrived_by"] == str(VOLUNTEER["_id"])
            assert "arrived_roster_id" not in stored
            assert "arrived_roster_id" not in out["registration"]
        asyncio.run(run())

    def test_print_and_seen_attribute_authenticated_user_not_roster(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _patch_db(monkeypatch, mock_db)
            camp_id, (day_id,) = await _seed_camp(mock_db)
            registered = await desk_register(RegisterBody(
                full_name="Sunita Devi", gender="F", dob="1975-06-14",
                aadhaar_last4="1234", aadhaar_scanned=True, age=51,
                phone="9876500001", camp_day_id=str(day_id),
            ), _Request(), actor=VOLUNTEER)
            await scan(ScanBody(payload=CARD), actor=VOLUNTEER)
            printed = await print_prescription(registered["registration"]["id"], actor=VOLUNTEER)
            stored = await mock_db.patients.find_one(
                {"_id": ObjectId(registered["registration"]["id"])},
            )
            assert stored["checked_in_by"] == str(VOLUNTEER["_id"])
            assert stored.get("seen_by") is None
            assert "printed_roster_id" not in stored
            assert "created_roster_id" not in printed["registration"]
        asyncio.run(run())

    def test_clinical_fulfilment_attributes_created_by_not_roster_id(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _patch_db(monkeypatch, mock_db)
            _camp_id, _patient_id, trans_id = await _seen_patient_with_transcription(mock_db)
            result = await record_fulfilment(
                FulfilmentBody(
                    transcription_id=str(trans_id),
                    item_type="medicine",
                    status="fulfilled",
                    paper_reviewed=True,
                    reviewed_revision_id=str(mock_db.last_rev_id),
                    reviewed_generation=1,
                    operation_id=str(ObjectId()),
                    medicine_outcomes=[{"medicine_id": MEDICINE["medicine_id"], "given": True}],
                ),
                actor=CLINICAL,
            )
            stored = await mock_db.fulfilments.find_one(
                {"_id": ObjectId(result["fulfilment"]["id"])},
            )
            assert stored["created_by"] == str(CLINICAL["_id"])
            assert stored.get("roster_id") is None
        asyncio.run(run())

    def test_leaderboard_counts_authenticated_ids_and_ignores_legacy_roster_fields(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _patch_db(monkeypatch, mock_db)
            camp_id, (day_id,) = await _seed_camp(mock_db)
            anita_id = ObjectId()
            ramesh_id = ObjectId()
            ghost_id = ObjectId()
            await mock_db.users.insert_one({
                "_id": anita_id, "name": "Anita", "role": "volunteer", "disabled_at": None,
            })
            await mock_db.users.insert_one({
                "_id": ramesh_id, "name": "Ramesh", "role": "volunteer", "disabled_at": None,
            })
            anita_user = {"_id": anita_id, "role": "volunteer"}
            ramesh_user = {"_id": ramesh_id, "role": "volunteer"}

            await desk_register(RegisterBody(
                full_name="Sunita Devi", age=51, phone="9876500001",
                camp_day_id=str(day_id),
            ), _Request(), actor=anita_user)
            await desk_register(RegisterBody(
                full_name="Sunita Devi", gender="F", dob="1975-06-14",
                aadhaar_last4="1234", aadhaar_scanned=True, age=51,
                phone="9876500002", camp_day_id=str(day_id),
            ), _Request(), actor=ramesh_user)
            await scan(ScanBody(payload=CARD), actor=ramesh_user)
            await mock_db.patients.insert_one({
                "camp_id": camp_id,
                "created_roster_id": str(anita_id),
                "arrived_roster_id": str(ramesh_id),
                "created_by": str(ghost_id),
            })
            board = await leaderboard(actor=ADMIN)
            by_name = {row["name"]: row for row in board["volunteers"]}
            assert by_name["Anita"]["registrations"] == 1
            assert by_name["Anita"]["points"] == 0
            assert by_name["Ramesh"]["registrations"] == 1
            assert by_name["Ramesh"]["points"] == 0
        asyncio.run(run())
