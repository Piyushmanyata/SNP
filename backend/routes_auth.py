import asyncio
import os
from datetime import timedelta
from typing import Any, Dict, Literal
from fastapi import APIRouter, Request, Response, HTTPException, Depends
from pymongo.errors import DuplicateKeyError
from db import get_db
from models import LoginBody, ChangePinBody
from helpers import now_utc, as_utc, normalize_name
from security import (
    verify_pin,
    hash_pin,
    validate_pin_policy,
    create_access_token,
    serialize_user,
    get_current_user,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

MAX_ATTEMPTS = 5
LOCK_MINUTES = 15


async def _claim_pin_attempt(db, identifier: str) -> None:
    now = now_utc()
    attempt = await db.login_attempts.find_one({"identifier": identifier})
    if not attempt:
        try:
            await db.login_attempts.insert_one({
                "identifier": identifier, "count": 0, "locked_until": now + timedelta(minutes=LOCK_MINUTES),
            })
        except DuplicateKeyError:
            pass
    elif not attempt.get("locked_until") or as_utc(attempt["locked_until"]) <= now:
        await db.login_attempts.update_one(
            {"_id": attempt["_id"], "locked_until": attempt.get("locked_until")},
            {"$set": {"count": 0, "locked_until": now + timedelta(minutes=LOCK_MINUTES)}},
        )
    claimed = await db.login_attempts.find_one_and_update(
        {"identifier": identifier, "count": {"$lt": MAX_ATTEMPTS}}, {"$inc": {"count": 1}},
        return_document=True,
    )
    if not claimed:
        raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")


def _cookie_samesite() -> Literal["lax", "strict", "none"]:
    value = os.environ.get("COOKIE_SAMESITE", "lax")
    if value == "lax":
        return "lax"
    if value == "strict":
        return "strict"
    if value == "none":
        return "none"
    raise ValueError("COOKIE_SAMESITE must be lax, strict, or none")


def set_auth_cookie(response: Response, access: str) -> None:
    secure = os.environ.get("COOKIE_SECURE", "true").lower() == "true"
    samesite = _cookie_samesite()
    response.set_cookie("access_token", access, httponly=True, secure=secure,
                        samesite=samesite, max_age=43200, path="/")


@router.post("/login")
async def login(body: LoginBody, request: Request, response: Response) -> Dict[str, Any]:
    db = get_db()
    name_norm = normalize_name(body.name)
    identifier = f"name:{name_norm}"

    await _claim_pin_attempt(db, identifier)

    user = await db.users.find_one({"name_normalized": name_norm})
    user_hash = (user.get("pin_hash") or user.get("password_hash")) if user else None
    if not user or not user_hash or not await asyncio.to_thread(verify_pin, body.pin, user_hash):
        raise HTTPException(status_code=401, detail="Invalid name or PIN")

    if user.get("disabled_at"):
        raise HTTPException(status_code=403, detail="Account disabled")

    await db.login_attempts.delete_one({"identifier": identifier})
    uid = str(user["_id"])
    access = create_access_token(uid, user.get("name") or name_norm, user.get("role", ""), user.get("session_version", 0))
    set_auth_cookie(response, access)
    return {"user": serialize_user(user), "access_token": access}


@router.post("/change-pin")
async def change_pin(body: ChangePinBody, response: Response, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    err = validate_pin_policy(body.new_pin)
    if err:
        raise HTTPException(status_code=400, detail=err)
    db = get_db()
    identifier = f"change-pin:{user['_id']}"
    await _claim_pin_attempt(db, identifier)
    current_hash = user.get("pin_hash") or user.get("password_hash")
    if not current_hash or not await asyncio.to_thread(verify_pin, body.current_pin, current_hash):
        raise HTTPException(status_code=400, detail="Current PIN is incorrect")
    new_hash = await asyncio.to_thread(hash_pin, body.new_pin)
    hash_field = "pin_hash" if user.get("pin_hash") else "password_hash"
    updated = await db.users.find_one_and_update(
        {"_id": user["_id"], hash_field: current_hash},
        {"$set": {"pin_hash": new_hash, "must_change_pin": False}, "$unset": {"password_hash": ""},
         "$inc": {"session_version": 1}},
        return_document=True,
    )
    if not updated:
        raise HTTPException(status_code=409, detail="PIN changed in another session; sign in again")
    user = updated
    await db.login_attempts.delete_one({"identifier": identifier})
    access = create_access_token(str(user["_id"]), user.get("name", ""), user["role"], user["session_version"])
    set_auth_cookie(response, access)
    return {"ok": True, "user": serialize_user(user), "access_token": access}


@router.post("/logout")
async def logout(response: Response, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    secure = os.environ.get("COOKIE_SECURE", "true").lower() == "true"
    samesite = _cookie_samesite()
    response.delete_cookie("access_token", path="/", secure=secure, httponly=True, samesite=samesite)
    response.delete_cookie("refresh_token", path="/", secure=secure, httponly=True, samesite=samesite)
    return {"ok": True}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    return {"user": serialize_user(user)}
