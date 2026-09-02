import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from dotenv import load_dotenv
load_dotenv()

from bson.errors import InvalidId
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from db import get_db, init_indexes
from security import hash_password
from helpers import now_utc

import routes_auth
import routes_staff
import routes_camps
import routes_registration
import routes_desk
import routes_clinical
import routes_reports
import routes_templates
import routes_reminders


async def seed_admin() -> None:
    db = get_db()
    email = os.environ["ADMIN_EMAIL"].lower().strip()
    password = os.environ["ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": email})
    if existing is None:
        await db.users.insert_one({
            "email": email, "password_hash": hash_password(password),
            "name": "Camp Administrator", "role": "admin", "phone": None,
            "team_lead_id": None, "disabled_at": None, "created_at": now_utc(),
        })


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await init_indexes()
    await seed_admin()
    yield


app = FastAPI(title="SNP Camps API", lifespan=lifespan)


@app.exception_handler(InvalidId)
async def invalid_id_handler(request: Request, exc: InvalidId) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": "Malformed identifier"})

LAN_ORIGIN_REGEX = (
    r"^https?://("
    r"localhost|"
    r"127\.0\.0\.1|"
    r"\[::1\]|"
    r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"192\.168\.\d{1,3}\.\d{1,3}|"
    r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}"
    r")(:\d+)?$"
)

def cors_origin_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [o.strip() for o in raw.split(",") if o.strip() and o.strip() != "*"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origin_list(os.environ.get("CORS_ORIGINS")),
    allow_origin_regex=LAN_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_auth.router)
app.include_router(routes_staff.router)
app.include_router(routes_camps.router)
app.include_router(routes_registration.router)
app.include_router(routes_desk.router)
app.include_router(routes_clinical.router)
app.include_router(routes_reports.router)
app.include_router(routes_templates.router)
app.include_router(routes_reminders.router)
