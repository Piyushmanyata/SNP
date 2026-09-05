import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

os.environ["ADMIN_BOOTSTRAP_PIN"] = "8642"
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "snp_camps")

from server import seed_admin


from security import verify_pin


def test_seed_admin_creates_when_missing():
    db = MagicMock()
    db.users.find_one = AsyncMock(return_value=None)
    db.users.insert_one = AsyncMock()
    db.users.update_one = AsyncMock()
    with patch("server.get_db", return_value=db):
        asyncio.run(seed_admin())
    db.users.insert_one.assert_awaited_once()
    db.users.update_one.assert_not_called()
    doc = db.users.insert_one.await_args.args[0]
    assert doc["name"] == "admin"
    assert doc["name_normalized"] == "admin"
    assert doc["role"] == "admin"
    assert doc["must_change_pin"] is True
    assert verify_pin("8642", doc["pin_hash"])
    assert not verify_pin("1234", doc["pin_hash"])


def test_seed_admin_refuses_missing_or_known_pin(monkeypatch):
    db = MagicMock()
    db.users.find_one = AsyncMock(return_value=None)
    db.users.insert_one = AsyncMock()
    with patch("server.get_db", return_value=db):
        monkeypatch.delenv("ADMIN_BOOTSTRAP_PIN", raising=False)
        try:
            asyncio.run(seed_admin())
            raise AssertionError("expected missing pin to fail")
        except RuntimeError:
            pass
        monkeypatch.setenv("ADMIN_BOOTSTRAP_PIN", "1234")
        try:
            asyncio.run(seed_admin())
            raise AssertionError("expected known pin to fail")
        except RuntimeError:
            pass
    db.users.insert_one.assert_not_called()


def test_seed_admin_leaves_existing_unchanged():
    existing = {
        "name": "admin",
        "name_normalized": "admin",
        "pin_hash": "not-a-real-hash",
        "role": "admin",
    }
    db = MagicMock()
    db.users.find_one = AsyncMock(return_value=existing)
    db.users.insert_one = AsyncMock()
    db.users.update_one = AsyncMock()
    with patch("server.get_db", return_value=db):
        asyncio.run(seed_admin())
    db.users.insert_one.assert_not_called()
    db.users.update_one.assert_not_called()
