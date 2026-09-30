"""Printing: the Print window and Operating day, the Print verdict with its atomic filter, and the Sheet stamp (ADR 0101)."""

import hmac
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from fastapi import HTTPException
from pymongo.asynchronous.database import AsyncDatabase

from helpers import IST, api_error, as_utc, iso, now_ist, now_utc
from security import sign

_MESSAGES = {
    "ALREADY_SEEN": "The doctor has already seen this patient. The prescription cannot be printed again.",
    "NOT_ARRIVED": "Scan the patient in at the door before printing.",
    "PRINT_WINDOW_CLOSED": "The print window is closed.",
    "NEEDS_DOOR_SCAN": "Scan this patient's Aadhaar card at the door, or record a No-card print.",
}


def error(code: str) -> HTTPException:
    return api_error(409, code, _MESSAGES[code])


def resolve(camp: Optional[dict], days: Iterable[dict], now: Optional[datetime] = None) -> Dict[str, Any]:
    """The printing state: whether the Print window is open, and which camp day is the Operating day."""
    now = as_utc(now or now_utc())
    today = now.astimezone(IST).strftime("%Y-%m-%d")
    days = list(days or [])
    override = (camp or {}).get("print_override") or {}
    expires = override.get("expires_at")
    if expires and as_utc(expires) <= now:
        override = {}
    mode = override.get("mode")
    selected = override.get("day_id")
    operating = None
    if mode == "disable":
        printing_open = False
    elif mode == "enable" and selected is not None:
        operating = next((d for d in days if str(d["_id"]) == str(selected)), None)
        printing_open = operating is not None
    else:
        operating = next((d for d in days if d.get("day_date") == today), None)
        printing_open = operating is not None
        mode = "automatic"
    return {
        "printing_open": printing_open,
        "operating_day_id": str(operating["_id"]) if operating else None,
        "operating_day_date": operating.get("day_date") if operating else None,
        "mode": mode or "automatic",
        "override_expires_at": iso(override.get("expires_at")) if override.get("mode") else None,
        "server_time": iso(now),
    }


async def load(db: AsyncDatabase, camp: dict) -> tuple[list[dict], Dict[str, Any]]:
    """The camp's days, sorted by date, and the printing state, from one read."""
    days = await db.camp_days.find({"camp_id": camp["_id"]}).sort("day_date", 1).to_list(100)
    return days, resolve(camp, days)


def operates(state: dict, day: dict) -> bool:
    return state.get("operating_day_id") == str(day["_id"])


def require_open(state: dict) -> None:
    if not state.get("printing_open"):
        raise error("PRINT_WINDOW_CLOSED")


def require_not_seen(patient: dict) -> None:
    if patient.get("queue_status") == "seen":
        raise error("ALREADY_SEEN")


def _signature(patient: dict, fetched_ms: str) -> str:
    return sign("sheet-stamp", "|".join((str(patient["_id"]), fetched_ms)))


def sign_sheet(patient: dict, state: dict) -> str:
    """Signs the moment a first-print sheet left the server while the Print window was open (ADR 0093)."""
    require_open(state)
    fetched_ms = str(int(now_utc().timestamp() * 1000))
    return f"{fetched_ms}.{_signature(patient, fetched_ms)}"


def _fresh(patient: dict, stamp: Optional[str]) -> bool:
    fetched_ms, _, signature = (stamp or "").partition(".")
    if not fetched_ms.isdecimal() or not hmac.compare_digest(signature.encode(), _signature(patient, fetched_ms).encode()):
        return False
    fetched = datetime.fromtimestamp(int(fetched_ms) / 1000, timezone.utc)
    return fetched.astimezone(IST).date() == now_ist().date()


def _refusal_code(patient: dict, state: dict, sheet_stamp: Optional[str], arriving: bool) -> Optional[str]:
    if patient.get("queue_status") == "seen":
        return "ALREADY_SEEN"
    if not arriving and not patient.get("arrived_at"):
        return "NOT_ARRIVED"
    if patient.get("printed_at"):
        return None
    if not state.get("printing_open") and not _fresh(patient, sheet_stamp):
        return "PRINT_WINDOW_CLOSED"
    if patient.get("identity_recheck_required"):
        return "NEEDS_DOOR_SCAN"
    return None


def refusal(patient: dict, state: dict, sheet_stamp: Optional[str] = None) -> Optional[HTTPException]:
    """Why the print endpoints refuse this patient now, or None. A fresh Sheet stamp skips the closed window, never the rest."""
    code = _refusal_code(patient, state, sheet_stamp, arriving=False)
    return error(code) if code else None


def _stage(patient: dict) -> str:
    if patient.get("queue_status") == "seen":
        return "seen"
    if patient.get("printed_at"):
        return "printed"
    if patient.get("arrived_at"):
        return "arrived"
    return "booked"


def verdict(patient: dict, state: dict) -> Dict[str, Any]:
    """Whether the desk Print action would be accepted now: it arrives an unarrived booking that has a No-card print."""
    code = _refusal_code(patient, state, None, arriving=bool(patient.get("no_card_print")))
    if code == "NOT_ARRIVED":
        code = "NEEDS_DOOR_SCAN"
    return {"allowed": code is None, "code": code, "stage": _stage(patient)}


def first_print_filter(patient_id: Any) -> Dict[str, Any]:
    """The verdict's rules about the patient document as a query, for the atomic write of printed_at."""
    return {
        "_id": patient_id,
        "printed_at": None,
        "arrived_at": {"$ne": None},
        "queue_status": {"$ne": "seen"},
        "identity_recheck_required": {"$ne": True},
    }
