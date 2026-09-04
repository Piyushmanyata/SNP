"""Volunteer roster, On-desk volunteer header, attribution, leaderboard by roster name."""
import asyncio
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

import pytest
from bson import ObjectId
from fastapi import HTTPException
from fastapi.testclient import TestClient

import db as db_module
import routes_auth
import routes_clinical
import routes_desk
import routes_registration
import routes_reports
import routes_roster
import routes_staff
import security
import server as server_mod
from models import RegisterBody, RosterBulkBody, ScanBody
from routes_registration import desk_register
from routes_desk import scan
from routes_reports import leaderboard
from routes_roster import bulk_add, disable_entry, list_roster
from security import hash_password
from test_adversarial_challenger import setup_mock_db
from test_camp_lifecycle import CARD, _Request, _mock, _seed_camp

PASS = "DeskRoster1!"
ADMIN = {"_id": ObjectId(), "role": "admin"}
TEAM_LEAD = {"_id": ObjectId(), "role": "team_lead", "email": "lead@snpcamps.org"}
VOLUNTEER = {"_id": ObjectId(), "role": "volunteer", "email": "desk1@snpcamps.org"}
CLINICAL = {"_id": ObjectId(), "role": "clinical_desk_operator", "email": "rx1@snpcamps.org"}


def _async_noop():
    async def _inner(*_a, **_k):
        return None
    return _inner


def _patch_db(monkeypatch, mock_db):
    mock_db = mock_db or setup_mock_db(monkeypatch)
    for mod in (
        db_module, routes_staff, routes_auth, routes_clinical, routes_reports,
        routes_roster, routes_desk, routes_registration, security,
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
        "email": actor.get("email") or f"{actor['role']}@snpcamps.org",
        "password_hash": hash_password(PASS),
        "name": extra.pop("name", actor["role"]),
        "role": actor["role"],
        "disabled_at": None,
        **extra,
    }
    await mock_db.users.insert_one(doc)
    return doc


def _auth(actor):
    token = security.create_access_token(str(actor["_id"]), actor.get("email") or "x@snpcamps.org")
    return {"Authorization": f"Bearer {token}"}


class TestRosterBulkAndList:
    def test_bulk_add_creates_and_skips(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _patch_db(monkeypatch, mock_db)
            camp_id, _days = await _seed_camp(mock_db)
            first = await bulk_add(RosterBulkBody(
                camp_id=str(camp_id), names=["Ramesh Kumar", "Sita", "  ", "ramesh kumar"],
            ), actor=ADMIN)
            assert [e["name"] for e in first["entries"]] == ["Ramesh Kumar", "Sita"]
            assert first["skipped"] == ["ramesh kumar"]
            second = await bulk_add(RosterBulkBody(
                camp_id=str(camp_id), names=["Sita", "Anita"],
            ), actor=ADMIN)
            assert [e["name"] for e in second["entries"]] == ["Anita"]
            assert second["skipped"] == ["Sita"]
        asyncio.run(run())

    def test_empty_names_is_refused(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _patch_db(monkeypatch, mock_db)
            camp_id, _days = await _seed_camp(mock_db)
            with pytest.raises(HTTPException) as exc:
                await bulk_add(RosterBulkBody(camp_id=str(camp_id), names=[]), actor=ADMIN)
            assert exc.value.status_code == 400
            assert exc.value.detail == "No names given"
        asyncio.run(run())

    def test_disabled_hidden_unless_include_disabled(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _patch_db(monkeypatch, mock_db)
            camp_id, _days = await _seed_camp(mock_db)
            created = await bulk_add(RosterBulkBody(
                camp_id=str(camp_id), names=["Active Name", "Gone Name"],
            ), actor=ADMIN)
            gone = next(e for e in created["entries"] if e["name"] == "Gone Name")
            await disable_entry(gone["id"], actor=ADMIN)
            listed = await list_roster(actor=ADMIN)
            assert [e["name"] for e in listed["entries"]] == ["Active Name"]
            all_rows = await list_roster(include_disabled=True, actor=ADMIN)
            names = [e["name"] for e in all_rows["entries"]]
            assert names == ["Active Name", "Gone Name"]
            gone_row = next(e for e in all_rows["entries"] if e["name"] == "Gone Name")
            assert gone_row["disabled_at"]
        asyncio.run(run())


class TestOnDeskVolunteerHeader:
    def test_volunteer_without_roster_header_is_428_required(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            await _seed_camp(mock_db)
            await _user(mock_db, VOLUNTEER, name="Desk 1")
            client = _client(monkeypatch, mock_db)
            r = client.post(
                "/api/desk/scan",
                json={"payload": CARD},
                headers=_auth(VOLUNTEER),
            )
            assert r.status_code == 428
            assert r.json()["detail"]["code"] == "ROSTER_REQUIRED"
        asyncio.run(run())

    def test_disabled_roster_id_is_428_invalid(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _patch_db(monkeypatch, mock_db)
            camp_id, _days = await _seed_camp(mock_db)
            await _user(mock_db, VOLUNTEER, name="Desk 1")
            created = await bulk_add(RosterBulkBody(
                camp_id=str(camp_id), names=["Disabled Vol"],
            ), actor=ADMIN)
            entry_id = created["entries"][0]["id"]
            await disable_entry(entry_id, actor=ADMIN)
            client = _client(monkeypatch, mock_db)
            headers = {**_auth(VOLUNTEER), "X-Roster-Id": entry_id}
            r = client.post("/api/desk/scan", json={"payload": CARD}, headers=headers)
            assert r.status_code == 428
            assert r.json()["detail"]["code"] == "ROSTER_INVALID"
        asyncio.run(run())

    def test_team_lead_without_header_is_not_refused(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            await _seed_camp(mock_db)
            await _user(mock_db, TEAM_LEAD, name="Lead")
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

    def test_clinical_operator_without_header_is_428_required(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            await _seed_camp(mock_db)
            await _user(mock_db, CLINICAL, name="Rx 1", line="rx")
            client = _client(monkeypatch, mock_db)
            r = client.post(
                "/api/clinical/transcription",
                json={"patient_id": str(ObjectId()), "diagnosis_options": []},
                headers=_auth(CLINICAL),
            )
            assert r.status_code == 428
            assert r.json()["detail"]["code"] == "ROSTER_REQUIRED"
        asyncio.run(run())

    def test_print_without_header_is_428_required(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            await _seed_camp(mock_db)
            await _user(mock_db, VOLUNTEER, name="Desk 1")
            client = _client(monkeypatch, mock_db)
            r = client.post(
                f"/api/desk/print/{ObjectId()}",
                headers=_auth(VOLUNTEER),
            )
            assert r.status_code == 428
            assert r.json()["detail"]["code"] == "ROSTER_REQUIRED"
        asyncio.run(run())

    def test_foreign_camp_roster_id_is_428_invalid(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _patch_db(monkeypatch, mock_db)
            camp_id, _days = await _seed_camp(mock_db)
            await _user(mock_db, VOLUNTEER, name="Desk 1")
            other = ObjectId()
            await mock_db.roster.insert_one({
                "_id": other, "camp_id": ObjectId(), "name": "Foreign",
                "name_normalized": "foreign", "disabled_at": None,
            })
            client = _client(monkeypatch, mock_db)
            headers = {**_auth(VOLUNTEER), "X-Roster-Id": str(other)}
            r = client.post("/api/desk/scan", json={"payload": CARD}, headers=headers)
            assert r.status_code == 428
            assert r.json()["detail"]["code"] == "ROSTER_INVALID"
        asyncio.run(run())


class TestAttributionAndLeaderboard:
    def test_desk_register_writes_created_roster_id(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _patch_db(monkeypatch, mock_db)
            camp_id, (day_id,) = await _seed_camp(mock_db)
            created = await bulk_add(RosterBulkBody(
                camp_id=str(camp_id), names=["Registrar"],
            ), actor=ADMIN)
            roster = await mock_db.roster.find_one({"_id": ObjectId(created["entries"][0]["id"])})
            result = await desk_register(RegisterBody(
                full_name="Sunita Devi", age=51, phone="9876500001",
                camp_day_id=str(day_id),
            ), _Request(), actor=VOLUNTEER, roster=roster)
            stored = await mock_db.patients.find_one(
                {"_id": ObjectId(result["registration"]["id"])},
            )
            assert stored["created_roster_id"] == str(roster["_id"])
            assert result["registration"]["created_roster_id"] == str(roster["_id"])
        asyncio.run(run())

    def test_scan_writes_arrived_roster_id(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _patch_db(monkeypatch, mock_db)
            camp_id, (day_id,) = await _seed_camp(mock_db)
            created = await bulk_add(RosterBulkBody(
                camp_id=str(camp_id), names=["Door Vol"],
            ), actor=ADMIN)
            roster = await mock_db.roster.find_one({"_id": ObjectId(created["entries"][0]["id"])})
            await desk_register(RegisterBody(
                full_name="Sunita Devi", gender="F", dob="1975-06-14",
                aadhaar_last4="1234", aadhaar_scanned=True, age=51,
                phone="9876500001", camp_day_id=str(day_id),
            ), _Request(), actor=VOLUNTEER, roster=roster)
            out = await scan(ScanBody(payload=CARD), actor=VOLUNTEER, roster=roster)
            assert out["outcome"] == "arrived"
            stored = await mock_db.patients.find_one(
                {"_id": ObjectId(out["registration"]["id"])},
            )
            assert stored["arrived_roster_id"] == str(roster["_id"])
            assert out["registration"]["arrived_roster_id"] == str(roster["_id"])
        asyncio.run(run())

    def test_leaderboard_counts_per_name_including_disabled_and_has_no_team_leads(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _patch_db(monkeypatch, mock_db)
            camp_id, (day_id,) = await _seed_camp(mock_db)
            await bulk_add(RosterBulkBody(
                camp_id=str(camp_id), names=["Anita", "Ramesh"],
            ), actor=ADMIN)
            anita = await mock_db.roster.find_one({"name": "Anita"})
            ramesh = await mock_db.roster.find_one({"name": "Ramesh"})
            await desk_register(RegisterBody(
                full_name="Sunita Devi", age=51, phone="9876500001",
                camp_day_id=str(day_id),
            ), _Request(), actor=VOLUNTEER, roster=anita)
            await desk_register(RegisterBody(
                full_name="Sunita Devi", gender="F", dob="1975-06-14",
                aadhaar_last4="1234", aadhaar_scanned=True, age=51,
                phone="9876500002", camp_day_id=str(day_id),
            ), _Request(), actor=VOLUNTEER, roster=ramesh)
            await scan(ScanBody(payload=CARD), actor=VOLUNTEER, roster=ramesh)
            await disable_entry(str(anita["_id"]), actor=ADMIN)
            board = await leaderboard(actor=ADMIN)
            assert "team_leads" not in board
            by_name = {row["name"]: row for row in board["volunteers"]}
            assert set(by_name) == {"Anita", "Ramesh"}
            assert by_name["Anita"]["registrations"] == 1
            assert by_name["Anita"]["arrivals"] == 0
            assert by_name["Anita"]["points"] == 1
            assert by_name["Ramesh"]["registrations"] == 1
            assert by_name["Ramesh"]["arrivals"] == 1
            assert by_name["Ramesh"]["points"] == 2
            assert board["volunteers"][0]["name"] == "Ramesh"
        asyncio.run(run())
