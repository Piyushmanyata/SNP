import json
import os
import urllib.request

MSG91_FLOW_URL = "https://control.msg91.com/api/v5/flow"

TEMPLATE_ENV = {
    "registration": "MSG91_TEMPLATE_REGISTRATION",
    "camp": "MSG91_TEMPLATE_CAMP",
    "ot_token": "MSG91_TEMPLATE_OT_TOKEN",
    "ot": "MSG91_TEMPLATE_OT",
    "specs_token": "MSG91_TEMPLATE_SPECS_TOKEN",
    "specs": "MSG91_TEMPLATE_SPECS",
}


def configured() -> bool:
    return bool(os.environ.get("MSG91_AUTH_KEY")) and all(
        os.environ.get(name) for name in TEMPLATE_ENV.values()
    )


def template_id(message_type: str) -> str:
    return os.environ[TEMPLATE_ENV[message_type]]


def send_dlt_sms(message_type: str, mobile: str, reg_no: int, event_date: str, venue: str) -> str:
    payload = {
        "template_id": template_id(message_type),
        "short_url": "0",
        "recipients": [{
            "mobiles": f"91{mobile}",
            "reg_no": str(reg_no),
            "date": event_date,
            "venue": venue,
        }],
    }
    req = urllib.request.Request(
        MSG91_FLOW_URL,
        data=json.dumps(payload).encode(),
        headers={
            "authkey": os.environ["MSG91_AUTH_KEY"],
            "Content-Type": "application/json",
            "accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = json.loads(resp.read().decode() or "{}")
    if not isinstance(body, dict) or body.get("type") != "success":
        raise ValueError("MSG91 did not accept the message")
    request_id = str(body.get("message") or body.get("request_id") or "").strip()
    if not request_id:
        raise ValueError("MSG91 accepted the message without a request id")
    return request_id
