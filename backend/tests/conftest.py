import os
import re
from pathlib import Path

import pytest
try:
    import requests
except ImportError:
    requests = None
from dotenv import dotenv_values

_root = Path(__file__).resolve().parents[2]
_fe_env_path = Path("/app/frontend/.env") if Path("/app/frontend/.env").exists() else _root / "frontend" / ".env"
frontend_env = dotenv_values(str(_fe_env_path)) if _fe_env_path.exists() else {}
_base = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL") or "http://localhost:8000"
BASE_URL = _base.rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def admin_credentials():
    p = Path("/app/memory/test_credentials.md") if Path("/app/memory/test_credentials.md").exists() else _root / "memory" / "test_credentials.md"
    if not p.exists():
        pytest.skip("test_credentials.md missing")
    content = p.read_text(encoding="utf-8")
    email = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?email(?:\*\*)?\s*:\s*`?([^`\s]+)', content)
    pwd = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?password(?:\*\*)?\s*:\s*`?([^`\s]+)', content)
    if not email or not pwd:
        pytest.skip("credentials missing")
    return {"email": email.group(1), "password": pwd.group(1)}


@pytest.fixture(scope="session")
def admin_token(admin_credentials):
    if requests is None:
        pytest.skip("requests not installed")
    r = requests.post(f"{API}/auth/login", json=admin_credentials, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="session")
def admin(admin_token):
    if requests is None:
        pytest.skip("requests not installed")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def anon():
    if requests is None:
        pytest.skip("requests not installed")
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s
