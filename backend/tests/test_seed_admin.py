import pytest

from conftest import run_db
from security import verify_pin
from server import seed_admin


def test_seed_admin_creates_when_missing(monkeypatch):
    monkeypatch.setenv("ADMIN_BOOTSTRAP_PIN", "8642")

    async def run(database):
        await seed_admin()
        users = await database.users.find({}).to_list(None)
        assert len(users) == 1
        doc = users[0]
        assert doc["name"] == "admin"
        assert doc["name_normalized"] == "admin"
        assert doc["role"] == "admin"
        assert doc["must_change_pin"] is True
        assert verify_pin("8642", doc["pin_hash"])
        assert not verify_pin("1234", doc["pin_hash"])

    run_db(run)


def test_seed_admin_refuses_missing_or_known_pin(monkeypatch):
    async def run(database):
        monkeypatch.delenv("ADMIN_BOOTSTRAP_PIN", raising=False)
        with pytest.raises(RuntimeError):
            await seed_admin()
        monkeypatch.setenv("ADMIN_BOOTSTRAP_PIN", "1234")
        with pytest.raises(RuntimeError):
            await seed_admin()
        assert await database.users.count_documents({}) == 0

    run_db(run)


def test_seed_admin_leaves_existing_unchanged(monkeypatch):
    monkeypatch.setenv("ADMIN_BOOTSTRAP_PIN", "8642")
    existing = {"name": "admin", "name_normalized": "admin", "pin_hash": "not-a-real-hash", "role": "admin"}

    async def run(database):
        await database.users.insert_one(existing)
        await seed_admin()
        assert await database.users.find({}).to_list(None) == [existing]

    run_db(run)
