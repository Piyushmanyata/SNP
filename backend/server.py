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
from security import hash_pin
from helpers import now_utc

import routes_auth
import routes_staff
import routes_camps
import routes_registration
import routes_desk
import routes_catalogue
import routes_clinical
import routes_reports
import routes_templates
import routes_reminders


async def seed_admin() -> None:
    db = get_db()
    existing = await db.users.find_one({"name_normalized": "admin"})
    if existing is not None:
        return
    pin = (os.environ.get("ADMIN_BOOTSTRAP_PIN") or "").strip()
    if not pin or len(pin) != 4 or not pin.isdigit():
        raise RuntimeError("ADMIN_BOOTSTRAP_PIN must be a 4-digit PIN")
    if pin == "1234":
        raise RuntimeError("ADMIN_BOOTSTRAP_PIN cannot be the repository-known PIN")
    await db.users.insert_one({
        "name": "admin",
        "name_normalized": "admin",
        "pin_hash": hash_pin(pin),
        "role": "admin",
        "must_change_pin": True,
        "phone": None,
        "team_lead_id": None,
        "disabled_at": None,
        "created_at": now_utc(),
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

def cors_origin_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [o.strip() for o in raw.split(",") if o.strip() and o.strip() != "*"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origin_list(os.environ.get("CORS_ORIGINS")),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_auth.router)
app.include_router(routes_staff.router)
app.include_router(routes_camps.router)
app.include_router(routes_registration.router)
app.include_router(routes_desk.router)
app.include_router(routes_catalogue.router)
app.include_router(routes_clinical.router)
app.include_router(routes_reports.router)
app.include_router(routes_templates.router)
app.include_router(routes_reminders.router)
