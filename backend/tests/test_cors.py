import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient

from server import cors_origin_list, app


def test_star_cors_origins_are_dropped_when_credentials_are_used():
    assert cors_origin_list("*") == []
    assert cors_origin_list(None) == []
    assert cors_origin_list("") == []
    assert cors_origin_list("*,https://evil.example") == ["https://evil.example"]
    assert cors_origin_list("http://localhost:3000, * ,http://127.0.0.1:3000") == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    assert cors_origin_list("https://camps.example.org") == ["https://camps.example.org"]


def test_unlisted_rfc1918_and_public_origins_are_not_credentialed():
    client = TestClient(app)
    for origin in (
        "http://10.0.0.8:3000",
        "http://192.168.1.50:9999",
        "http://172.16.1.4:3000",
        "https://evil.example",
    ):
        r = client.options(
            "/api/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert r.headers.get("access-control-allow-origin") != origin
