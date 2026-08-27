import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

os.environ.setdefault("ADMIN_EMAIL", "admin@snpcamps.org")
os.environ.setdefault("ADMIN_PASSWORD", "AdminCamp@2026")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "snp_camps")

from server import seed_admin


def test_seed_admin_strips_email_whitespace():
    db = MagicMock()
    db.users.find_one = AsyncMock(return_value=None)
    db.users.insert_one = AsyncMock()
    db.users.update_one = AsyncMock()
    os.environ["ADMIN_EMAIL"] = "  admin@snpcamps.org  "
    try:
        with patch("server.get_db", return_value=db):
            asyncio.run(seed_admin())
    finally:
        os.environ["ADMIN_EMAIL"] = "admin@snpcamps.org"
    doc = db.users.insert_one.await_args.args[0]
    assert doc["email"] == "admin@snpcamps.org"


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
    assert doc["email"] == "admin@snpcamps.org"
    assert doc["role"] == "admin"
    assert doc["password_hash"]


def test_seed_admin_leaves_existing_unchanged():
    existing = {
        "email": "admin@snpcamps.org",
        "password_hash": "not-a-real-hash",
        "role": "admin",
    }
    db = MagicMock()
    db.users.find_one = AsyncMock(return_value=existing)
    db.users.insert_one = AsyncMock()
    db.users.update_one = AsyncMock()
    os.environ["ADMIN_PASSWORD"] = "DifferentPass@999"
    try:
        with patch("server.get_db", return_value=db):
            asyncio.run(seed_admin())
    finally:
        os.environ["ADMIN_PASSWORD"] = "AdminCamp@2026"
    db.users.insert_one.assert_not_called()
    db.users.update_one.assert_not_called()
