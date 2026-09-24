import json
import logging
import os
import time
import traceback
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Awaitable, Callable
from uuid import uuid4
from dotenv import load_dotenv
load_dotenv()

from bson.errors import InvalidId
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from db import get_db, init_indexes
from security import hash_pin, validate_pin_policy
from helpers import api_error, now_utc

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
import routes_sms


async def seed_admin() -> None:
    db = get_db()
    existing = await db.users.find_one({"name_normalized": "admin"})
    if existing is not None:
        return
    pin = (os.environ.get("ADMIN_BOOTSTRAP_PIN") or "").strip()
    err = validate_pin_policy(pin, "admin")
    if err:
        raise RuntimeError(f"ADMIN_BOOTSTRAP_PIN: {err}")
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

http_log = logging.getLogger("snp.http")
if not http_log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    http_log.addHandler(_handler)
    http_log.setLevel(logging.INFO)
    http_log.propagate = False
SLOW_REQUEST_MS = 1000


async def request_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    request_id = uuid4().hex[:12]
    request.state.request_id = request_id
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        http_log.error(json.dumps({
            "request_id": request_id,
            "error": type(exc).__name__,
            "trace": "".join(traceback.format_tb(exc.__traceback__)),
        }))
        response = JSONResponse(status_code=500, content={"detail": {
            "code": "INTERNAL",
            "message": "Something went wrong. Quote this code to the admin.",
            "request_id": request_id,
        }})
    ms = round((time.perf_counter() - started) * 1000)
    route = request.scope.get("route")
    http_log.log(logging.WARNING if ms > SLOW_REQUEST_MS else logging.INFO, json.dumps({
        "request_id": request_id,
        "method": request.method,
        "path": getattr(route, "path", "unmatched"),
        "status": response.status_code,
        "ms": ms,
    }))
    response.headers["X-Request-ID"] = request_id
    return response


app.middleware("http")(request_context)


def _error_body(exc) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(InvalidId)
async def invalid_id_handler(request: Request, exc: InvalidId) -> JSONResponse:
    return _error_body(api_error(400, "INVALID_ID", "That id is not valid."))


@app.exception_handler(RequestValidationError)
async def invalid_input_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = {}
    for error in exc.errors():
        parts = [str(part) for part in error.get("loc", ()) if part not in ("body", "query", "path")]
        fields[".".join(parts) or "request"] = str(error.get("msg") or "Check this field.")
    return _error_body(api_error(422, "INVALID_INPUT", "Check the highlighted fields.", fields=fields))

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
app.include_router(routes_sms.router)
