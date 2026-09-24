import pytest
from bson import ObjectId
from fastapi import HTTPException, Request, Response

import routes_auth
import routes_staff
from conftest import run_db
from models import CreateStaffBody, LoginBody
from security import hash_pin, validate_pin_policy
from seed import asgi_client, bearer, user_doc

ADMIN = {"_id": ObjectId(), "role": "admin", "name": "Admin"}
LEAD = {"_id": ObjectId(), "role": "team_lead", "name": "Lead"}


def _request(source="203.0.113.7"):
    return Request({"type": "http", "method": "POST", "path": "/api/auth/login", "headers": [], "client": (source, 1)})


async def _login(name, pin, source="203.0.113.7"):
    return await routes_auth.login(LoginBody(name=name, pin=pin), _request(source), Response())


async def _refused(name, pin, source="203.0.113.7"):
    with pytest.raises(HTTPException) as exc:
        await _login(name, pin, source)
    return exc.value.status_code


@pytest.mark.parametrize("pin, role, ok", [
    ("2580", "volunteer", True),
    ("2580", "clinical_desk_operator", True),
    ("258014", "admin", True),
    ("258014", "team_lead", True),
    ("2580", "admin", False),
    ("2580", "team_lead", False),
    ("258014", "volunteer", False),
    ("25a0", "volunteer", False),
    ("٢٥٨٠", "volunteer", False),
    ("1234", "volunteer", False),
    ("4321", "volunteer", False),
    ("7777", "volunteer", False),
    ("123456", "admin", False),
    ("000000", "team_lead", False),
    ("987654", "admin", False),
])
def test_pin_policy_is_by_role_and_refuses_guessable_pins(pin, role, ok):
    assert (validate_pin_policy(pin, role) is None) is ok


def test_created_staff_get_distinct_one_time_pins_of_their_role_length():
    async def run(database):
        pins = {}
        for name, role in [("V One", "volunteer"), ("V Two", "volunteer"), ("Op", "clinical_desk_operator"),
                           ("TL", "team_lead"), ("Ad", "admin")]:
            created = await routes_staff.create_staff(CreateStaffBody(name=name, role=role), actor=ADMIN)
            pins[name] = created["temporary_pin"]
            assert validate_pin_policy(created["temporary_pin"], role) is None
            assert created["staff"]["must_change_pin"] is True
        assert len(set(pins.values())) == 5
        assert [len(pins[n]) for n in ("V One", "Op", "TL", "Ad")] == [4, 4, 6, 6]
        listed = await routes_staff.list_staff(actor=ADMIN)
        assert all("temporary_pin" not in s for s in listed["staff"])
        stored = await database.users.find_one({"name": "V One"})
        assert pins["V One"] not in str(stored)
        assert (await _login("V One", pins["V One"]))["user"]["must_change_pin"] is True

    run_db(run)


def test_first_sign_in_owns_the_account_only_after_a_personal_pin(monkeypatch):
    async def run(database):
        created = await routes_staff.create_staff(CreateStaffBody(name="Lead Two", role="team_lead"), actor=ADMIN)
        temp = created["temporary_pin"]
        async with asgi_client() as client:
            assert (await client.post("/api/auth/login", json={"name": "Lead Two", "pin": temp})).status_code == 200
            assert (await client.get("/api/staff")).status_code == 403
            for new_pin, reason in [(temp, "same"), ("2580", "short"), ("111111", "weak")]:
                refused = await client.post("/api/auth/change-pin", json={"current_pin": temp, "new_pin": new_pin})
                assert refused.status_code == 400, reason
            changed = await client.post("/api/auth/change-pin", json={"current_pin": temp, "new_pin": "258014"})
            assert changed.status_code == 200, changed.text
            assert (await client.get("/api/staff")).status_code == 200
            assert (await client.post("/api/auth/login", json={"name": "Lead Two", "pin": temp})).status_code == 401

    run_db(run)


def test_reset_gives_a_new_one_time_pin_ends_old_sessions_and_clears_the_lockout(monkeypatch):
    async def run(database):
        await database.users.insert_one(user_doc(LEAD["name"], "team_lead", _id=LEAD["_id"], pin_hash=hash_pin("258014")))
        created = await routes_staff.create_staff(CreateStaffBody(name="Vol", role="volunteer"), actor=LEAD)
        vol_id = created["staff"]["id"]
        await database.users.update_one({"_id": ObjectId(vol_id)}, {"$set": {"pin_hash": hash_pin("2580"), "must_change_pin": False}})
        async with asgi_client() as client:
            old_token = (await client.post("/api/auth/login", json={"name": "Vol", "pin": "2580"})).cookies["access_token"]
        for _ in range(5):
            assert await _refused("Vol", "9051") == 401
        assert await _refused("Vol", "2580") == 429

        reset = await routes_staff.reset_staff_pin(vol_id, actor=LEAD)
        new_pin = reset["temporary_pin"]
        assert new_pin not in (created["temporary_pin"], "2580")
        assert "1234" not in str(reset)

        async with asgi_client() as client:
            assert (await client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_token}"})).status_code == 401
        assert await _refused("Vol", "2580") == 401
        assert (await _login("Vol", new_pin))["user"]["must_change_pin"] is True
        audit = await database.staff_audit.find_one({"action": "reset_pin"})
        assert audit["target_id"] == vol_id and audit["actor_id"] == str(LEAD["_id"])

    run_db(run)


def test_repeated_remote_lockouts_are_visible_to_the_lead():
    async def run(database):
        await database.users.insert_one(user_doc(LEAD["name"], "team_lead", _id=LEAD["_id"]))
        created = await routes_staff.create_staff(CreateStaffBody(name="Target", role="volunteer"), actor=LEAD)
        for source in ("198.51.100.1", "198.51.100.2"):
            await database.login_attempts.delete_many({"identifier": "name:target"})
            for _ in range(5):
                assert await _refused("Target", "9051", source) == 401
        listed = {s["name"]: s for s in (await routes_staff.list_staff(actor=LEAD))["staff"]}
        target = listed["Target"]
        assert target["id"] == created["staff"]["id"]
        assert target["locked_until"] is not None
        assert target["lockouts_24h"] == 2
        assert target["lockout_sources_24h"] == 2
        lockout = await database.login_lockouts.find_one({"name_normalized": "target"})
        assert lockout["source"] in ("198.51.100.1", "198.51.100.2")

    run_db(run)


def test_unlock_recovers_the_account_without_changing_or_revealing_the_pin():
    async def run(database):
        await database.users.insert_one(user_doc(LEAD["name"], "team_lead", _id=LEAD["_id"]))
        other_lead = {"_id": ObjectId(), "role": "team_lead", "name": "Other"}
        volunteer = {"_id": ObjectId(), "role": "volunteer", "name": "Desk"}
        created = await routes_staff.create_staff(CreateStaffBody(name="Mine", role="volunteer"), actor=LEAD)
        vol_id = created["staff"]["id"]
        await database.users.update_one({"_id": ObjectId(vol_id)}, {"$set": {"pin_hash": hash_pin("2580"), "must_change_pin": False}})
        for _ in range(5):
            await _refused("Mine", "9051")
        assert await _refused("Mine", "2580") == 429

        for actor in (other_lead, volunteer):
            with pytest.raises(HTTPException) as exc:
                await routes_staff.unlock_staff(vol_id, actor=actor)
            assert exc.value.status_code == 403
        unlocked = await routes_staff.unlock_staff(vol_id, actor=LEAD)
        assert unlocked == {"ok": True}
        assert (await _login("Mine", "2580"))["user"]["must_change_pin"] is False
        audit = await database.staff_audit.find_one({"action": "unlock"})
        assert audit["target_id"] == vol_id and audit["actor_id"] == str(LEAD["_id"])
        listed = {s["name"]: s for s in (await routes_staff.list_staff(actor=LEAD))["staff"]}
        assert listed["Mine"]["locked_until"] is None
        assert listed["Mine"]["lockouts_24h"] == 1

    run_db(run)


def test_an_unknown_network_cannot_sweep_accounts_but_a_signed_in_venue_cannot_be_shut_out():
    async def run(database):
        names = [f"Vol {i}" for i in range(11)]
        await database.users.insert_many([user_doc(n, pin_hash=hash_pin("2580"), must_change_pin=False) for n in names])
        for name in names[:10]:
            for _ in range(5):
                assert await _refused(name, "9051", "192.0.2.10") == 401
        assert await _refused("Vol 10", "2580", "192.0.2.10") == 429

        venue = "192.0.2.99"
        assert (await _login("Vol 10", "2580", venue))["user"]["name"] == "Vol 10"
        for i in range(60):
            assert await _refused(f"Nobody {i}", "9051", venue) == 401
        assert (await _login("Vol 10", "2580", venue))["user"]["pin_length"] == 4

    run_db(run)


def test_the_per_network_budget_ignores_nothing_before_a_first_sign_in():
    async def run(database):
        await database.users.insert_one(user_doc("Vol", pin_hash=hash_pin("2580"), must_change_pin=False))
        for i in range(50):
            assert await _refused(f"Nobody {i}", "9051", "192.0.2.50") == 401
        assert await _refused("Vol", "2580", "192.0.2.50") == 429

    run_db(run)


def test_staff_tokens_signed_by_a_lead_reach_the_unlock_route(monkeypatch):
    async def run(database):
        await database.users.insert_one(user_doc(LEAD["name"], "team_lead", _id=LEAD["_id"]))
        created = await routes_staff.create_staff(CreateStaffBody(name="Via HTTP", role="volunteer"), actor=LEAD)
        async with asgi_client() as client:
            response = await client.post(f"/api/staff/{created['staff']['id']}/unlock", headers=bearer(LEAD["_id"], "Lead", "team_lead"))
        assert response.status_code == 200, response.text

    run_db(run)
