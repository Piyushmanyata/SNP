import re
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from server import LAN_ORIGIN_REGEX


def test_cors_regex_allows_rfc1918_frontend_origins():
    rx = re.compile(LAN_ORIGIN_REGEX)
    assert rx.match("http://172.20.10.2:3000")
    assert rx.match("http://192.168.1.50:3000")
    assert rx.match("http://10.0.0.8:3000")
    assert rx.match("http://localhost:3000")
    assert rx.match("http://127.0.0.1:3000")


def test_cors_regex_rejects_public_internet_origins():
    rx = re.compile(LAN_ORIGIN_REGEX)
    assert not rx.match("https://evil.example:3000")
    assert not rx.match("http://8.8.8.8:3000")
