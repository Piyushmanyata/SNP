import json
import os
import urllib.request

MSG91_FLOW_URL = "https://control.msg91.com/api/v5/flow"


def configured() -> bool:
    return bool(
        os.environ.get("MSG91_AUTH_KEY")
        and os.environ.get("MSG91_TEMPLATE_CAMP")
        and os.environ.get("MSG91_TEMPLATE_OT")
        and os.environ.get("MSG91_TEMPLATE_SPECS")
    )


def template_id(reminder_type: str) -> str:
    return {
        "camp": os.environ["MSG91_TEMPLATE_CAMP"],
        "ot": os.environ["MSG91_TEMPLATE_OT"],
        "specs": os.environ["MSG91_TEMPLATE_SPECS"],
    }[reminder_type]


def send_dlt_sms(reminder_type: str, mobile: str, venue: str) -> str:
    payload = {
        "template_id": template_id(reminder_type),
        "short_url": "0",
        "recipients": [{"mobiles": f"91{mobile}", "venue": venue}],
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
    return str(body.get("message") or body.get("request_id") or "")
