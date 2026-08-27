import os
import re
import hmac
import hashlib
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# ---- time helpers ----

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime | None) -> datetime | None:
    """Mongo returns naive UTC datetimes; normalise to tz-aware UTC for safe compares."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    return as_utc(dt).isoformat() if dt else None


def today_ist_str() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


# ---- normalization ----

def normalize_name(name: str) -> str:
    if not name:
        return ""
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9\u0900-\u097F\u0980-\u09FF ]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if len(digits) >= 10:
        digits = digits[-10:]
    return digits


def is_dummy_phone(phone: str) -> bool:
    """Reject repeated-digit dummy phones like 9999999999 / 1111111111."""
    if not phone or len(phone) != 10:
        return True
    return len(set(phone)) <= 1


# ---- HMAC person key ----

def person_key(last4: str, name: str, dob: str, gender: str) -> str:
    pepper = os.environ.get("AADHAAR_HASH_PEPPER", "dev_secret_aadhaar_pepper").encode()
    material = f"{last4}|{normalize_name(name)}|{dob or ''}|{(gender or '').lower()}".encode()
    return hmac.new(pepper, material, hashlib.sha256).hexdigest()


def new_uuid() -> str:
    return str(uuid.uuid4())


# ---- labellers (never render raw enums) ----

STATUS_LABELS = {"registered": "Registered", "seen": "Seen", "waiting": "Registered"}
ROLE_LABELS = {
    "admin": "Admin",
    "team_lead": "Team Lead",
    "volunteer": "Volunteer",
    "clinical_desk_operator": "Clinical Desk Operator",
    "patient": "Patient",
}
GENDER_LABELS = {"M": "Male", "F": "Female", "O": "Other", "male": "Male", "female": "Female"}

DIAGNOSIS_OPTIONS = [
    "Cataract",
    "Refractive Error",
    "Conjunctivitis",
    "Glaucoma",
    "Diabetic Retinopathy",
    "Pterygium",
    "Dry Eye",
    "Corneal Ulcer",
    "Squint",
    "Presbyopia",
]


def age_from_dob(dob: str) -> int | None:
    try:
        d = datetime.strptime(dob, "%Y-%m-%d")
        today = datetime.now(IST)
        return today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    except Exception:
        return None
