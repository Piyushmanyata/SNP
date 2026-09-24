import os
import secrets
import jwt
import bcrypt
from datetime import timedelta
from typing import Callable, Any
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Request, Depends
from db import get_db
from helpers import now_utc, api_error

JWT_ALGORITHM = "HS256"


def hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_pin(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _secret() -> str:
    return os.environ["JWT_SECRET"]


def create_access_token(user_id: str, name: str = "", role: str = "", session_version: int = 0) -> str:
    payload = {
        "sub": user_id,
        "name": name,
        "role": role,
        "exp": now_utc() + timedelta(hours=12),
        "type": "access",
        "session_version": session_version,
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def pin_length(role: str) -> int:
    return 6 if role in ("admin", "team_lead") else 4


def validate_pin_policy(pin: str, role: str) -> str | None:
    length = pin_length(role)
    if len(pin) != length or not pin.isascii() or not pin.isdigit():
        return f"PIN must be exactly {length} digits."
    if len(set(pin)) == 1 or pin in "0123456789" or pin in "9876543210":
        return "Choose a PIN that is not one digit repeated or a straight run like 1234."
    return None


def temporary_pin(role: str) -> str:
    length = pin_length(role)
    while True:
        pin = f"{secrets.randbelow(10 ** length):0{length}d}"
        if validate_pin_policy(pin, role) is None:
            return pin


def serialize_user(user: dict) -> dict:
    return {
        "id": str(user["_id"]),
        "name": user.get("name"),
        "role": user["role"],
        "pin_length": pin_length(user["role"]),
        "phone": user.get("phone"),
        "team_lead_id": user.get("team_lead_id"),
        "line": user.get("line"),
        "must_change_pin": bool(user.get("must_change_pin", False)),
        "disabled_at": user["disabled_at"].isoformat() if user.get("disabled_at") else None,
    }


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise api_error(401, "NOT_AUTHENTICATED", 'Not authenticated')
    try:
        payload = jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise api_error(401, "INVALID_TOKEN_TYPE", 'Invalid token type')
        user_id = ObjectId(payload["sub"])
    except jwt.ExpiredSignatureError:
        raise api_error(401, "TOKEN_EXPIRED", 'Token expired')
    except jwt.InvalidTokenError:
        raise api_error(401, "INVALID_TOKEN", 'Invalid token')
    except (KeyError, InvalidId, TypeError, ValueError):
        raise api_error(401, "INVALID_TOKEN", 'Invalid token')
    db = get_db()
    user = await db.users.find_one({"_id": user_id})
    if not user:
        raise api_error(401, "USER_NOT_FOUND", 'User not found')
    if payload.get("session_version", 0) != user.get("session_version", 0):
        raise api_error(401, "SESSION_EXPIRED_SIGN_IN_AGAIN", 'Session expired; sign in again')
    if user.get("disabled_at"):
        raise api_error(403, "ACCOUNT_DISABLED", 'Account disabled')
    if user.get("must_change_pin"):
        path = request.url.path.rstrip("/") or "/"
        allowed = {"/api/auth/me", "/api/auth/change-pin", "/api/auth/logout"}
        if path not in allowed:
            raise api_error(403, "PIN_CHANGE_REQUIRED", 'PIN_CHANGE_REQUIRED')
    return user


def require_roles(*roles: str) -> Callable[..., Any]:
    async def dep(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise api_error(403, "INSUFFICIENT_PERMISSIONS", 'Insufficient permissions')
        return user
    return dep


# role predicate dependencies
require_admin = require_roles("admin")
require_staff = require_roles("admin", "team_lead", "volunteer")
require_clinical = require_roles("clinical_desk_operator")
require_any = require_roles("admin", "team_lead", "volunteer", "clinical_desk_operator")
require_lead = require_roles("admin", "team_lead")
