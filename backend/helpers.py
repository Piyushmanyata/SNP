import os
import re
import hmac
import hashlib
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
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


def now_ist() -> datetime:
    return datetime.now(IST)


def today_ist_str() -> str:
    return now_ist().strftime("%Y-%m-%d")


def next_ist_midnight(now: datetime | None = None):
    ist = as_utc(now or now_utc()).astimezone(IST)
    nxt = ist.date() + timedelta(days=1)
    return datetime(nxt.year, nxt.month, nxt.day, tzinfo=IST).astimezone(timezone.utc)


HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def parse_hhmm(value: str | None) -> str:
    raw = (value or "").strip()
    if not HHMM_RE.fullmatch(raw):
        raise ValueError("Times must be HH:MM")
    return raw


def ist_local_instant(day_date: str, hhmm: str) -> datetime:
    hour, minute = map(int, hhmm.split(":"))
    return datetime.strptime(day_date, "%Y-%m-%d").replace(
        hour=hour, minute=minute, second=0, microsecond=0, tzinfo=IST,
    )


def tomorrow_ist_str() -> str:
    return (date.fromisoformat(today_ist_str()) + timedelta(days=1)).isoformat()


def ist_day_bounds(day_str: str) -> tuple[datetime, datetime]:
    start_ist = datetime.strptime(day_str, "%Y-%m-%d").replace(tzinfo=IST)
    end_ist = start_ist + timedelta(days=1)
    return start_ist.astimezone(timezone.utc), end_ist.astimezone(timezone.utc)


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


# Crockford base32 without I, L, O and U: a volunteer reading a code aloud
# cannot turn it into a different valid one. Uppercase and digits only, so
# "SNP:" plus a code encodes in QR alphanumeric mode — a 21x21 symbol.
PATIENT_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
PATIENT_CODE_LENGTH = 8


def new_patient_code() -> str:
    return "".join(secrets.choice(PATIENT_CODE_ALPHABET) for _ in range(PATIENT_CODE_LENGTH))


def parse_patient_identifier(raw_value: str) -> str:
    """A scanned QR, a pasted URL or a typed registration number, reduced to the identifier."""
    val = str(raw_value or "").strip()
    if val[:4].lower() == "snp:":
        val = val[4:]
    if "/p/" in val:
        val = val.split("/p/")[-1]
    return val.upper()


# ---- labellers (never render raw enums) ----

STATUS_LABELS = {"registered": "Registered", "arrived": "Arrived", "seen": "Seen", "waiting": "Registered"}
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
