import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

app = FastAPI(title="SNP Camps API")

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

origins = os.environ.get("CORS_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if origins == "*" else [o.strip() for o in origins.split(",") if o.strip()],
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


async def seed_admin():
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


@app.on_event("startup")
async def startup():
    await init_indexes()
    await seed_admin()
