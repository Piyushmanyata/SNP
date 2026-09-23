import asyncio
import time
import os
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "snp_test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("COOKIE_SECURE", "false")

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

import db as db_module
import routes_auth
import routes_staff
import security
import server as server_mod
from security import hash_pin
from fastapi import HTTPException, Request, Response
from models import LoginBody
from test_adversarial_challenger import setup_mock_db


def _patch_db(monkeypatch, mock_db):
    for mod in (db_module, routes_staff, routes_auth, security):
        monkeypatch.setattr(mod, "get_db", lambda: mock_db)
    return mock_db


def _client(monkeypatch, mock_db):
    monkeypatch.setattr(server_mod, "init_indexes", lambda: asyncio.sleep(0))
    monkeypatch.setattr(server_mod, "seed_admin", lambda: asyncio.sleep(0))
    _patch_db(monkeypatch, mock_db)
    server_mod.app.router.on_startup.clear()
    return TestClient(server_mod.app, raise_server_exceptions=True)


def test_login_and_pin_change_flow(monkeypatch):
    async def run():
        mock_db = setup_mock_db(monkeypatch)
        _patch_db(monkeypatch, mock_db)
        uid = ObjectId()
        user = {
            "_id": uid,
            "name": "Ramesh Kumar",
            "name_normalized": "ramesh kumar",
            "pin_hash": hash_pin("1234"),
            "must_change_pin": True,
            "role": "volunteer",
            "disabled_at": None,
        }
        await mock_db.users.insert_one(user)

        client = _client(monkeypatch, mock_db)

        # 1. Invalid PIN -> 401
        res = client.post("/api/auth/login", json={"name": "Ramesh Kumar", "pin": "0000"})
        assert res.status_code == 401

        # 2. Correct PIN -> 200, must_change_pin is True
        res = client.post("/api/auth/login", json={"name": "Ramesh Kumar", "pin": "1234"})
        assert res.status_code == 200
        data = res.json()
        assert "refresh_token" not in res.cookies
        assert data["user"]["must_change_pin"] is True
        token = data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 3. Change PIN with non-4-digit -> 400
        res = client.post("/api/auth/change-pin", json={"current_pin": "1234", "new_pin": "123"}, headers=headers)
        assert res.status_code == 422 or res.status_code == 400

        # 4. Change PIN successfully
        res = client.post("/api/auth/change-pin", json={"current_pin": "1234", "new_pin": "5678"}, headers=headers)
        assert res.status_code == 200
        assert "refresh_token" not in res.cookies
        assert res.json()["user"]["must_change_pin"] is False

        # 5. Old PIN 1234 now fails
        res = client.post("/api/auth/login", json={"name": "Ramesh Kumar", "pin": "1234"})
        assert res.status_code == 401

        # 6. New PIN 5678 succeeds
        res = client.post("/api/auth/login", json={"name": "Ramesh Kumar", "pin": "5678"})
        assert res.status_code == 200
        assert res.json()["user"]["must_change_pin"] is False

        client.cookies.set("refresh_token", "legacy", domain="testserver.local", path="/")
        assert client.post("/api/auth/logout").status_code == 200
        assert "refresh_token" not in client.cookies

    asyncio.run(run())


def test_changing_pin_invalidates_other_sessions_and_keeps_current_session(monkeypatch):
    mock_db = setup_mock_db(monkeypatch)
    client = _client(monkeypatch, mock_db)
    asyncio.run(mock_db.users.insert_one({
        "name": "Operator", "name_normalized": "operator", "role": "clinical_desk_operator",
        "pin_hash": hash_pin("5678"), "must_change_pin": False,
    }))
    login = client.post("/api/auth/login", json={"name": "Operator", "pin": "5678"})
    previous_token = login.json()["access_token"]
    changed = client.post("/api/auth/change-pin", json={"current_pin": "5678", "new_pin": "2468"})
    assert changed.status_code == 200
    assert client.get("/api/auth/me").status_code == 200
    client.cookies.clear()
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {previous_token}"}).status_code == 401


def test_simultaneous_wrong_logins_share_a_five_attempt_budget(monkeypatch):
    async def run():
        mock_db = setup_mock_db(monkeypatch)
        _patch_db(monkeypatch, mock_db)
        await mock_db.users.insert_one({
            "name": "Operator", "name_normalized": "operator", "role": "volunteer",
            "pin_hash": "hash", "must_change_pin": False,
        })
        verified = []

        def wrong_pin(*args):
            verified.append(True)
            time.sleep(0.03)
            return False

        monkeypatch.setattr(routes_auth, "verify_pin", wrong_pin)
        request = Request({"type": "http", "method": "POST", "path": "/api/auth/login", "headers": []})
        results = await asyncio.gather(*[
            routes_auth.login(LoginBody(name="Operator", pin="0000"), request, Response()) for _ in range(12)
        ], return_exceptions=True)
        assert len(verified) == 5
        assert sum(result.status_code == 429 for result in results) == 7
    asyncio.run(run())


def test_disable_staff_keeps_an_enabled_admin(monkeypatch):
    async def run():
        mock_db = setup_mock_db(monkeypatch)
        _patch_db(monkeypatch, mock_db)
        first = {"_id": ObjectId(), "name": "A", "name_normalized": "a", "role": "admin", "disabled_at": None}
        second = {"_id": ObjectId(), "name": "B", "name_normalized": "b", "role": "admin", "disabled_at": None}
        await mock_db.users.insert_one(first)
        await mock_db.users.insert_one(second)

        with pytest.raises(HTTPException) as own:
            await routes_staff.disable_staff(str(first["_id"]), first)
        assert own.value.status_code == 409
        assert own.value.detail["code"] == "CANNOT_DISABLE_SELF"

        await mock_db.users.update_one({"_id": first["_id"]}, {"$set": {"disabled_at": security.now_utc()}})
        with pytest.raises(HTTPException) as last:
            await routes_staff.disable_staff(str(second["_id"]), first)
        assert last.value.status_code == 409
        assert last.value.detail["code"] == "LAST_ADMIN"
        assert (await mock_db.users.find_one({"_id": second["_id"]}))["disabled_at"] is None

        await mock_db.users.update_one({"_id": first["_id"]}, {"$set": {"disabled_at": None}})
        assert await routes_staff.disable_staff(str(second["_id"]), first) == {"ok": True}
        assert (await mock_db.users.find_one({"_id": second["_id"]}))["disabled_at"] is not None
    asyncio.run(run())
