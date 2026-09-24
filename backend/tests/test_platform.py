import asyncio
import json
import logging

import httpx
from fastapi import FastAPI

import db
from conftest import run_db
from server import request_context


class Aborted(Exception):
    pass


def test_an_aborted_transaction_leaves_no_document_in_either_collection():
    async def body(database):
        try:
            async with db.get_client().start_session() as session:
                async with await session.start_transaction():
                    await database.patients.insert_one({"reg_no": "TX-1", "patient_qr": "TX-1"}, session=session)
                    await database.fulfilments.insert_one({"transcription_id": "t", "item_type": "x"}, session=session)
                    raise Aborted
        except Aborted:
            pass
        return await database.patients.count_documents({}), await database.fulfilments.count_documents({})

    assert run_db(body) == (0, 0)


class _Lines(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append((record.levelno, json.loads(record.getMessage())))


def _call(path, lines):
    app = FastAPI()
    app.middleware("http")(request_context)

    @app.get("/api/items/{item_id}")
    async def item(item_id: str):
        return {"id": item_id}

    @app.get("/api/boom")
    async def boom():
        patient = "phone 9876543210 name Ramesh"
        raise RuntimeError(patient)

    handler = _Lines()
    logger = logging.getLogger("snp.http")
    logger.addHandler(handler)

    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
            return await client.get(path)

    try:
        return asyncio.run(go())
    finally:
        logger.removeHandler(handler)
        lines.extend(handler.lines)


def test_each_request_gets_an_id_and_one_log_line_with_the_route_template():
    lines = []
    response = _call("/api/items/abc?phone=9876543210", lines)
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 12 and int(request_id, 16) >= 0
    assert lines == [(logging.INFO, {
        "request_id": request_id, "method": "GET", "path": "/api/items/{item_id}", "status": 200,
        "ms": lines[0][1]["ms"],
    })]


def test_an_unhandled_error_returns_a_quotable_code_and_logs_no_patient_data():
    lines = []
    response = _call("/api/boom", lines)
    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["code"] == "INTERNAL"
    assert detail["request_id"] == response.headers["X-Request-ID"]
    logged = json.dumps(lines)
    assert "RuntimeError" in logged and detail["request_id"] in logged
    assert "9876543210" not in logged and "Ramesh" not in logged
