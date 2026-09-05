import os
import jwt
import bcrypt
from datetime import timedelta
from typing import Callable, Any
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Request, HTTPException, Depends
from db import get_db
from helpers import now_utc

JWT_ALGORITHM = "HS256"


def hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_pin(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


hash_password = hash_pin


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


def validate_pin_policy(pin: str) -> str | None:
    if not pin or len(pin) != 4 or not pin.isascii() or not pin.isdigit():
        return "PIN must be exactly 4 digits."
    return None


def serialize_user(user: dict) -> dict:
    return {
        "id": str(user["_id"]),
        "name": user.get("name"),
        "role": user["role"],
        "phone": user.get("phone"),
        "team_lead_id": user.get("team_lead_id"),
        "line": user.get("line"),
        "must_change_pin": bool(user.get("must_change_pin", False)),
        "disabled_at": user.get("disabled_at").isoformat() if user.get("disabled_at") else None,
    }


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = ObjectId(payload["sub"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except (KeyError, InvalidId, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")
    db = get_db()
    user = await db.users.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if payload.get("session_version", 0) != user.get("session_version", 0):
        raise HTTPException(status_code=401, detail="Session expired; sign in again")
    if user.get("disabled_at"):
        raise HTTPException(status_code=403, detail="Account disabled")
    if user.get("must_change_pin"):
        path = request.url.path.rstrip("/") or "/"
        allowed = {"/api/auth/me", "/api/auth/change-pin", "/api/auth/logout"}
        if path not in allowed:
            raise HTTPException(status_code=403, detail="PIN_CHANGE_REQUIRED")
    return user


def require_roles(*roles: str) -> Callable[..., Any]:
    async def dep(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return dep


# role predicate dependencies
require_admin = require_roles("admin")
require_staff = require_roles("admin", "team_lead", "volunteer")
require_clinical = require_roles("clinical_desk_operator")
require_clinical_operator = require_clinical
require_any = require_roles("admin", "team_lead", "volunteer", "clinical_desk_operator")
require_lead = require_roles("admin", "team_lead")


def is_admin(user: dict) -> bool:
    return user["role"] == "admin"
