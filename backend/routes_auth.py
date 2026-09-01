import os
from datetime import timedelta
from typing import Any, Dict
from fastapi import APIRouter, Request, Response, HTTPException, Depends
from db import get_db
from models import LoginBody
from helpers import now_utc, as_utc
from security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    serialize_user,
    get_current_user,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

MAX_ATTEMPTS = 5
LOCK_MINUTES = 15


def set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    secure = os.environ.get("COOKIE_SECURE", "true").lower() == "true"
    samesite = os.environ.get("COOKIE_SAMESITE", "none")
    response.set_cookie("access_token", access, httponly=True, secure=secure,
                        samesite=samesite, max_age=43200, path="/")
    response.set_cookie("refresh_token", refresh, httponly=True, secure=secure,
                        samesite=samesite, max_age=604800, path="/")


@router.post("/login")
async def login(body: LoginBody, request: Request, response: Response) -> Dict[str, Any]:
    db = get_db()
    email = body.email.lower().strip()
    # proxy-safe: key lockout on email (ingress rotates client IPs)
    identifier = f"email:{email}"

    attempt = await db.login_attempts.find_one({"identifier": identifier})
    if attempt and attempt.get("count", 0) >= MAX_ATTEMPTS:
        locked_until = as_utc(attempt.get("locked_until"))
        if locked_until and locked_until > now_utc():
            raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")

    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password_hash"]):
        await db.login_attempts.update_one(
            {"identifier": identifier},
            {"$inc": {"count": 1}, "$set": {"locked_until": now_utc() + timedelta(minutes=LOCK_MINUTES)}},
            upsert=True,
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if user.get("disabled_at"):
        raise HTTPException(status_code=403, detail="Account disabled")

    await db.login_attempts.delete_one({"identifier": identifier})
    uid = str(user["_id"])
    access = create_access_token(uid, email)
    refresh = create_refresh_token(uid)
    set_auth_cookies(response, access, refresh)
    return {"user": serialize_user(user), "access_token": access}


@router.post("/logout")
async def logout(response: Response, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    secure = os.environ.get("COOKIE_SECURE", "true").lower() == "true"
    samesite = os.environ.get("COOKIE_SAMESITE", "none")
    response.delete_cookie("access_token", path="/", secure=secure, httponly=True, samesite=samesite)
    response.delete_cookie("refresh_token", path="/", secure=secure, httponly=True, samesite=samesite)
    return {"ok": True}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    return {"user": serialize_user(user)}
