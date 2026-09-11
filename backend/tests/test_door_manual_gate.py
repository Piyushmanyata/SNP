"""Manual entry at the door is an admin decision that lapses with the camp day."""
import os
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "snp_test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("AADHAAR_HASH_PEPPER", "test-pepper")

from routes_camps import door_manual_open  # noqa: E402


def test_a_camp_whose_admin_never_opened_the_gate_is_shut():
    assert door_manual_open({}, today="2026-09-11") is False
    assert door_manual_open({"door_manual_date": None}, today="2026-09-11") is False


def test_no_active_camp_is_a_shut_gate():
    assert door_manual_open(None, today="2026-09-11") is False


def test_the_gate_is_open_on_the_day_an_admin_opened_it():
    assert door_manual_open({"door_manual_date": "2026-09-11"}, today="2026-09-11") is True


def test_the_gate_shuts_itself_when_the_camp_day_ends():
    assert door_manual_open({"door_manual_date": "2026-09-11"}, today="2026-09-12") is False


def test_a_gate_opened_for_a_later_day_is_not_open_today():
    assert door_manual_open({"door_manual_date": "2026-09-12"}, today="2026-09-11") is False
