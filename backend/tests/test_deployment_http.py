import re
import uuid
from urllib.parse import urljoin

import pytest

from conftest import API


def test_built_spa_deep_links_and_hashed_asset_caching(anon):
    origin = API.removesuffix("/api")
    index = anon.get(f"{origin}/", timeout=30)
    assert index.status_code == 200
    assert '<div id="root"></div>' in index.text
    assert "no-cache" in index.headers.get("Cache-Control", "")
    for path in ("/desk", "/clinical", "/team", "/analytics", "/self-register"):
        page = anon.get(f"{origin}{path}", timeout=30)
        assert page.status_code == 200, path
        assert page.text == index.text, path
    scripts = re.findall(r'<script\b[^>]*\bsrc=["\']([^"\']+\.js)["\']', index.text)
    assert scripts, "The built HTML must load a JavaScript asset"
    script_path = scripts[0]
    assert re.search(r'[.-][A-Za-z0-9_-]{8,}\.js$', script_path), script_path
    script = anon.get(urljoin(f"{origin}/", script_path), timeout=30)
    assert script.status_code == 200
    assert "javascript" in script.headers.get("Content-Type", "")
    assert script.content
    assert "immutable" in script.headers.get("Cache-Control", "")
    assert "max-age=" in script.headers.get("Cache-Control", "")
    assert script.headers.get("ETag")


@pytest.mark.parametrize("path,status", [("/health", 200), ("/auth/me", 401), ("/missing-deployment-route", 404)])
def test_api_success_and_error_responses_keep_security_headers(anon, path, status):
    response = anon.get(f"{API}{path}", timeout=30)
    assert response.status_code == status
    assert "no-store" in response.headers.get("Cache-Control", "")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"


def test_authenticated_kpis_are_not_cached(admin):
    response = admin.get(f"{API}/kpis", timeout=30)
    assert response.status_code == 200
    assert isinstance(response.json(), dict)
    assert "no-store" in response.headers.get("Cache-Control", "")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"


def test_nginx_preserves_distinct_client_rate_limit_buckets(anon):
    tag = uuid.uuid4().hex[:8]
    first_ip = f"2001:db8:{tag[:4]}:{tag[4:]}::1"
    second_ip = f"2001:db8:{tag[:4]}:{tag[4:]}::2"
    payload = {
        "full_name": "Deployment rate-limit probe",
        "age": 40,
        "camp_day_id": "000000000000000000000000",
        "qr_payload": "not-an-aadhaar-qr",
    }
    for attempt in range(300):
        response = anon.post(f"{API}/self-register", json=payload, headers={"X-Forwarded-For": first_ip}, timeout=30)
        assert response.status_code == 400, (attempt, response.status_code)
        assert response.json()["detail"] == "Aadhaar QR could not be decoded"
    limited = anon.post(f"{API}/self-register", json=payload, headers={"X-Forwarded-For": first_ip}, timeout=30)
    assert limited.status_code == 429
    other_client = anon.post(f"{API}/self-register", json=payload, headers={"X-Forwarded-For": second_ip}, timeout=30)
    assert other_client.status_code == 400
    assert other_client.json()["detail"] == "Aadhaar QR could not be decoded"
