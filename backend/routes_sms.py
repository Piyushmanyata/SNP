import hmac
import os
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request

import msg91
import sms
from db import get_db
from helpers import ist_day_bounds, iso, today_ist_str
from security import require_admin

router = APIRouter(prefix="/api", tags=["sms"])

WEBHOOK_HEADER = "X-SNP-Webhook-Secret"


def _tally(rows: List[dict]) -> Dict[str, Any]:
    t: Dict[str, Any] = dict.fromkeys(
        ("submitted", "delivered", "dlt_failed", "other_failed", "uncertain", "rejected", "unsent", "paused"), 0,
    )
    t["credits"] = 0.0
    for r in rows:
        status = r.get("status")
        if status in ("sent", "uncertain"):
            t["submitted"] += 1
        if status in ("uncertain", "rejected", "paused"):
            t[status] += 1
        elif status in ("failed", "abandoned"):
            t["unsent"] += 1
        if r.get("delivery") == "delivered":
            t["delivered"] += 1
        elif r.get("delivery") == "failed":
            t["dlt_failed" if r.get("dlt_failure") else "other_failed"] += 1
        t["credits"] += r.get("credit") or 0.0
    t["credits"] = round(t["credits"], 2)
    return t


@router.post("/webhooks/msg91")
async def msg91_delivery_report(request: Request) -> Dict[str, Any]:
    expected = (os.environ.get("MSG91_WEBHOOK_SECRET") or "").encode()
    got = (request.headers.get(WEBHOOK_HEADER) or "").encode()
    if not expected or not hmac.compare_digest(expected, got):
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Delivery report must be JSON")
    reports = body if isinstance(body, list) else [body]
    db = get_db()
    recorded = 0
    for report in reports:
        if isinstance(report, dict) and await sms.record_delivery_report(db, report):
            recorded += 1
    return {"ok": True, "recorded": recorded}


@router.get("/sms/status")
async def sms_status(actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    controls = {c["_id"]: c for c in await db.sms_controls.find({}).to_list(None)}
    start, end = ist_day_bounds(today_ist_str())
    rows = await db.reminder_ledger.find({"created_at": {"$gte": start, "$lt": end}}).to_list(None)
    has_key = bool(os.environ.get("MSG91_AUTH_KEY"))
    types = []
    for message_type in sms.MESSAGE_COPY:
        control = controls.get(message_type) or {}
        types.append({
            "message_type": message_type,
            "configured": has_key and bool(msg91.template_id(message_type)),
            "paused": bool(control.get("paused")),
            "paused_at": iso(control.get("paused_at")) if control.get("paused") else None,
            "paused_reason": control.get("paused_reason") if control.get("paused") else None,
            "paused_request_id": control.get("paused_request_id") if control.get("paused") else None,
            "today": _tally([r for r in rows if r.get("message_type") == message_type]),
        })
    return {
        "types": types,
        "today": _tally(rows),
        "reports_enabled": bool(os.environ.get("MSG91_WEBHOOK_SECRET")),
    }


@router.post("/sms/{message_type}/resume")
async def resume_sms(message_type: str, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    if message_type not in sms.MESSAGE_COPY:
        raise HTTPException(status_code=404, detail="Unknown message type")
    await sms.resume(get_db(), message_type, str(actor["_id"]))
    return await sms_status(actor)
