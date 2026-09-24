import asyncio
import time

import pytest
from bson import ObjectId
from fastapi import HTTPException, Request, Response

import routes_auth
import routes_staff
from conftest import run_db
from models import LoginBody
from security import hash_pin
from seed import NOW, asgi_client, user_doc


def test_login_and_pin_change_flow(monkeypatch):
    async def run(database):
        await database.users.insert_one(user_doc(
            "Ramesh Kumar", pin_hash=hash_pin("1234"), must_change_pin=True,
        ))

        async with asgi_client() as client:
            res = await client.post("/api/auth/login", json={"name": "Ramesh Kumar", "pin": "0000"})
            assert res.status_code == 401

            res = await client.post("/api/auth/login", json={"name": "Ramesh Kumar", "pin": "1234"})
            assert res.status_code == 200
            data = res.json()
            assert set(res.cookies) == {"access_token"} and "access_token" not in data
            assert data["user"]["must_change_pin"] is True

            res = await client.post("/api/auth/change-pin", json={"current_pin": "1234", "new_pin": "123"})
            assert res.status_code == 422 or res.status_code == 400

            res = await client.post("/api/auth/change-pin", json={"current_pin": "1234", "new_pin": "2580"})
            assert res.status_code == 200
            assert res.json()["user"]["must_change_pin"] is False

            res = await client.post("/api/auth/login", json={"name": "Ramesh Kumar", "pin": "1234"})
            assert res.status_code == 401

            res = await client.post("/api/auth/login", json={"name": "Ramesh Kumar", "pin": "2580"})
            assert res.status_code == 200
            assert res.json()["user"]["must_change_pin"] is False

            assert (await client.post("/api/auth/logout")).status_code == 200
            assert "access_token" not in client.cookies

    run_db(run)


def test_changing_pin_invalidates_other_sessions_and_keeps_current_session(monkeypatch):
    async def run(database):
        await database.users.insert_one(user_doc(
            "Operator", "clinical_desk_operator", pin_hash=hash_pin("5678"), must_change_pin=False,
        ))
        async with asgi_client() as client:
            login = await client.post("/api/auth/login", json={"name": "Operator", "pin": "5678"})
            previous_token = login.cookies["access_token"]
            changed = await client.post("/api/auth/change-pin", json={"current_pin": "5678", "new_pin": "2468"})
            assert changed.status_code == 200
            assert (await client.get("/api/auth/me")).status_code == 200
            client.cookies.clear()
            stale = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {previous_token}"})
            assert stale.status_code == 401

    run_db(run)


def test_simultaneous_wrong_logins_share_a_five_attempt_budget(monkeypatch):
    verified = []

    def wrong_pin(*args):
        verified.append(True)
        time.sleep(0.03)
        return False

    monkeypatch.setattr(routes_auth, "verify_pin", wrong_pin)

    async def run(database):
        await database.users.insert_one(user_doc("Operator", pin_hash="hash", must_change_pin=False))
        request = Request({"type": "http", "method": "POST", "path": "/api/auth/login", "headers": []})
        results = await asyncio.gather(*[
            routes_auth.login(LoginBody(name="Operator", pin="0000"), request, Response()) for _ in range(12)
        ], return_exceptions=True)
        assert len(verified) == 5
        assert sum(result.status_code == 429 for result in results) == 7
        assert (await database.login_attempts.find_one({"identifier": "name:operator"}))["count"] == 5

    run_db(run)


def test_disable_staff_keeps_an_enabled_admin():
    async def run(database):
        first = user_doc("A", "admin", _id=ObjectId())
        second = user_doc("B", "admin", _id=ObjectId())
        await database.users.insert_many([first, second])

        with pytest.raises(HTTPException) as own:
            await routes_staff.disable_staff(str(first["_id"]), first)
        assert own.value.status_code == 409
        assert own.value.detail["code"] == "CANNOT_DISABLE_SELF"

        await database.users.update_one({"_id": first["_id"]}, {"$set": {"disabled_at": NOW}})
        with pytest.raises(HTTPException) as last:
            await routes_staff.disable_staff(str(second["_id"]), first)
        assert last.value.status_code == 409
        assert last.value.detail["code"] == "LAST_ADMIN"
        assert (await database.users.find_one({"_id": second["_id"]}))["disabled_at"] is None

        await database.users.update_one({"_id": first["_id"]}, {"$set": {"disabled_at": None}})
        assert await routes_staff.disable_staff(str(second["_id"]), first) == {"ok": True}
        assert (await database.users.find_one({"_id": second["_id"]}))["disabled_at"] is not None

    run_db(run)
