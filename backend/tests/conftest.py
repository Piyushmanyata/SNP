import asyncio
import importlib
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from pymongo import monitoring

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_MONGO_URL = os.environ.get(
    "SNP_TEST_MONGO_URL", "mongodb://127.0.0.1:27017/?replicaSet=rs0&directConnection=true"
)
FROZEN_IST = "2026-10-05T09:00"
JWT_SIGNED_ON_REAL_CLOCK = "security"


def freeze_clock(monkeypatch, ist=FROZEN_IST):
    importlib.import_module("server")
    import helpers
    frozen = datetime.fromisoformat(ist).replace(tzinfo=ZoneInfo("Asia/Kolkata"))
    fakes = {
        "now_ist": (helpers.now_ist, lambda: frozen),
        "now_utc": (helpers.now_utc, lambda: frozen.astimezone(timezone.utc)),
    }
    for module in list(sys.modules.values()):
        if module.__name__ == JWT_SIGNED_ON_REAL_CLOCK:
            continue
        if Path(getattr(module, "__file__", None) or ".").parent != BACKEND_DIR:
            continue
        for name, (real, fake) in fakes.items():
            if getattr(module, name, None) is real:
                monkeypatch.setattr(module, name, fake)
    return frozen


class CommandLog(monitoring.CommandListener):
    def __init__(self):
        self.commands = []

    def started(self, event):
        self.commands.append((event.command_name, event.command.get(event.command_name)))

    def succeeded(self, event):
        pass

    def failed(self, event):
        pass


def run_db(body, listener=None):
    import db
    from pymongo import AsyncMongoClient

    async def main():
        client = AsyncMongoClient(
            TEST_MONGO_URL, serverSelectionTimeoutMS=5000, event_listeners=[listener] if listener else [],
        )
        name = f"snp_t_{uuid4().hex[:8]}"
        database = client[name]
        db._client, db._db = client, database
        try:
            await db.init_indexes()
            return await body(database)
        finally:
            await client.drop_database(name)
            await client.close()
            db._client = db._db = None

    return asyncio.run(main())


def pytest_configure(config):
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
    os.environ.setdefault("DB_NAME", "snp_test")
    os.environ.setdefault("AADHAAR_HASH_PEPPER", "test-pepper")
    os.environ.setdefault("JWT_SECRET", "test-jwt-secret-of-at-least-32-bytes")
    os.environ.setdefault("COOKIE_SECURE", "false")


try:
    import requests
except ImportError:
    requests = None
from dotenv import dotenv_values

_root = Path(__file__).resolve().parents[2]
_fe_env_path = Path("/app/frontend/.env") if Path("/app/frontend/.env").exists() else _root / "frontend" / ".env"
frontend_env = dotenv_values(str(_fe_env_path)) if _fe_env_path.exists() else {}
_base = os.environ.get("SNP_LIVE_API") or os.environ.get("LIVE_API_URL")
BASE_URL = _base.rstrip("/") if _base else ""
API = f"{BASE_URL}/api" if BASE_URL else ""


def pytest_sessionfinish(session, exitstatus):
    if os.environ.get("SNP_REQUIRE_LIVE_TESTS") == "1":
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter and reporter.stats.get("skipped"):
            reporter.write_line("CI requires zero skipped tests.", red=True)
            session.exitstatus = pytest.ExitCode.TESTS_FAILED


def _require_live_api():
    if not BASE_URL:
        pytest.skip("SNP_LIVE_API is not configured")
    if requests is None:
        pytest.skip("requests not installed")


@pytest.fixture(scope="session")
def admin_credentials():
    _require_live_api()
    if os.environ.get("SNP_TEST_ADMIN_NAME") and os.environ.get("SNP_TEST_ADMIN_PIN"):
        return {"name": os.environ["SNP_TEST_ADMIN_NAME"], "pin": os.environ["SNP_TEST_ADMIN_PIN"]}
    p = Path("/app/memory/test_credentials.md") if Path("/app/memory/test_credentials.md").exists() else _root / "memory" / "test_credentials.md"
    if not p.exists():
        pytest.skip("test_credentials.md missing")
    content = p.read_text(encoding="utf-8")
    name = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?name(?:\*\*)?\s*:\s*`?([^`\s]+)', content)
    pin = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?pin(?:\*\*)?\s*:\s*`?([^`\s]+)', content)
    if not name or not pin:
        pytest.skip("Name/PIN credentials missing")
    return {"name": name.group(1), "pin": pin.group(1)}


@pytest.fixture(scope="session")
def admin_token(admin_credentials):
    _require_live_api()
    r = requests.post(f"{API}/auth/login", json=admin_credentials, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    if r.json()["user"].get("must_change_pin"):
        new_pin = "975310" if admin_credentials["pin"] != "975310" else "864200"
        r = requests.post(f"{API}/auth/change-pin", json={"current_pin": admin_credentials["pin"], "new_pin": new_pin}, headers={"Authorization": f"Bearer {r.json()['access_token']}"}, timeout=30)
        assert r.status_code == 200, r.text
        admin_credentials["pin"] = new_pin
    tok = r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="session")
def admin(admin_token):
    _require_live_api()
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"})
    return s


@pytest.fixture
def anon():
    _require_live_api()
    with requests.Session() as session:
        session.headers.update({"Content-Type": "application/json"})
        yield session
