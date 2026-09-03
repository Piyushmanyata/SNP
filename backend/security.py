import os
import jwt
import bcrypt
from datetime import timedelta
from typing import Callable, Any
from bson import ObjectId
from fastapi import Request, HTTPException, Depends
from db import get_db
from helpers import now_utc

JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _secret() -> str:
    return os.environ["JWT_SECRET"]


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": now_utc() + timedelta(hours=12),
        "type": "access",
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {"sub": user_id, "exp": now_utc() + timedelta(days=7), "type": "refresh"}
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def validate_password_policy(password: str) -> str | None:
    if len(password) < 12:
        return "Password must be at least 12 characters."
    if not any(c.islower() for c in password):
        return "Password must include a lowercase letter."
    if not any(c.isupper() for c in password):
        return "Password must include an uppercase letter."
    if not any(c.isdigit() for c in password):
        return "Password must include a digit."
    if not any(not c.isalnum() for c in password):
        return "Password must include a symbol."
    return None


def serialize_user(user: dict) -> dict:
    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "name": user.get("name"),
        "role": user["role"],
        "phone": user.get("phone"),
        "team_lead_id": user.get("team_lead_id"),
        "line": user.get("line"),
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
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    db = get_db()
    user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if user.get("disabled_at"):
        raise HTTPException(status_code=403, detail="Account disabled")
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
require_clinical = require_roles("admin", "clinical_desk_operator")
require_any = require_roles("admin", "team_lead", "volunteer", "clinical_desk_operator")


def is_admin(user: dict) -> bool:
    return user["role"] == "admin"
