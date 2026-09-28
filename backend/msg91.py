import http.client
import json
import os
import socket
import threading
from typing import Any, Dict

MSG91_HOST = "control.msg91.com"
MSG91_FLOW_PATH = "/api/v5/flow"
TIMEOUT_SECONDS = 8

TEMPLATE_ENV = {
    "registration": "MSG91_TEMPLATE_REGISTRATION",
    "camp": "MSG91_TEMPLATE_CAMP",
    "ot_token": "MSG91_TEMPLATE_OT_TOKEN",
    "ot": "MSG91_TEMPLATE_OT",
    "specs_token": "MSG91_TEMPLATE_SPECS_TOKEN",
    "specs": "MSG91_TEMPLATE_SPECS",
    "ot_change": "MSG91_TEMPLATE_OT_CHANGE",
    "specs_change": "MSG91_TEMPLATE_SPECS_CHANGE",
}


class Unsent(Exception):
    pass


class Rejected(Exception):
    pass


class Throttled(Unsent):
    """MSG91 did not accept the message. A later try cannot double-charge."""


def configured() -> bool:
    return bool(os.environ.get("MSG91_AUTH_KEY")) and any(
        os.environ.get(name) for name in TEMPLATE_ENV.values()
    )


def template_id(message_type: str) -> str:
    return os.environ.get(TEMPLATE_ENV[message_type], "")


def _cut(conn: http.client.HTTPConnection, expired: threading.Event) -> None:
    """Ends a call that is still running at its deadline; the socket timeout alone bounds each read, not the reply."""
    expired.set()
    try:
        if conn.sock:
            conn.sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


def send(message_type: str, mobile: str, variables: Dict[str, Any]) -> str:
    payload = {
        "template_id": template_id(message_type),
        "short_url": "0",
        "recipients": [{
            "mobiles": f"91{mobile}",
            **{name: str(value) for name, value in variables.items()},
        }],
    }
    conn = http.client.HTTPSConnection(MSG91_HOST, timeout=TIMEOUT_SECONDS)
    expired = threading.Event()
    deadline = threading.Timer(TIMEOUT_SECONDS, _cut, (conn, expired))
    deadline.start()
    try:
        try:
            conn.connect()
        except OSError as exc:
            raise Unsent(f"{type(exc).__name__}: {exc}") from exc
        if expired.is_set():
            raise Unsent(f"MSG91 connection took longer than {TIMEOUT_SECONDS} s")
        conn.request(
            "POST",
            MSG91_FLOW_PATH,
            body=json.dumps(payload).encode(),
            headers={
                "authkey": os.environ["MSG91_AUTH_KEY"],
                "Content-Type": "application/json",
                "accept": "application/json",
            },
        )
        response = conn.getresponse()
        status = response.status
        raw = response.read()
    finally:
        deadline.cancel()
        conn.close()
    if status in (429, 503):
        raise Throttled(f"MSG91 answered HTTP {status}")
    if status >= 500:
        raise ValueError(f"MSG91 answered HTTP {status}")
    body = json.loads(raw.decode() or "{}")
    if isinstance(body, dict) and body.get("type") == "error":
        raise Rejected(str(body.get("message") or f"HTTP {status}"))
    if not isinstance(body, dict) or body.get("type") != "success":
        raise ValueError("MSG91 reply did not confirm the message")
    request_id = str(body.get("message") or body.get("request_id") or "").strip()
    if not request_id:
        raise ValueError("MSG91 accepted the message without a request id")
    return request_id
