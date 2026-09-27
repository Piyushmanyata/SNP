"""The in-memory SMS provider adapter: records accepted sends and plays scripted outcomes."""

import threading
from typing import Any, Callable, Dict, List, Union

import msg91

Outcome = Union[str, Callable[[str, str, Dict[str, Any]], str]]
REPORT_CODES = {"delivered": "1", "failed": "2", "dlt_failure": "16", "dnd": "2"}


class Recorder:
    def __init__(self, enabled: bool = True) -> None:
        self.sent: List[Dict[str, Any]] = []
        self.numbers: Dict[str, str] = {}
        self.templates = {message_type: "test-flow" for message_type in msg91.TEMPLATE_ENV}
        self.enabled = enabled
        self.outcome: Outcome = "accept"
        self.scripted: List[Outcome] = []
        self._lock = threading.Lock()

    def configured(self) -> bool:
        return self.enabled and any(self.templates.values())

    def template_id(self, message_type: str) -> str:
        return self.templates.get(message_type, "")

    def script(self, *outcomes: Outcome) -> None:
        self.scripted.extend(outcomes)

    def send(self, message_type: str, mobile: str, variables: Dict[str, Any]) -> str:
        with self._lock:
            outcome = self.scripted.pop(0) if self.scripted else self.outcome
        if callable(outcome):
            return outcome(message_type, mobile, variables)
        if outcome == "unsent":
            raise msg91.Unsent("scripted: connection refused")
        if outcome == "throttled":
            raise msg91.Throttled("scripted: HTTP 503")
        if outcome == "rejected":
            raise msg91.Rejected("scripted: rejected")
        if outcome == "unknown":
            raise ValueError("scripted: the reply was lost")
        assert outcome == "accept", outcome
        self.sent.append({"type": message_type, "mobile": mobile, **variables})
        request_id = f"id-{len(self.sent)}"
        self.numbers[request_id] = mobile
        return request_id

    def report(self, request_id: str, outcome: str = "delivered", reason: str = "") -> Dict[str, Any]:
        """The MSG91 Delivery report for a recorded send: delivered, failed, dlt_failure or dnd."""
        if outcome == "dnd":
            reason = reason or "DND: Failed due to Preference Category on DLT"
        return {
            "requestId": request_id, "status": REPORT_CODES[outcome], "telNum": f"91{self.numbers[request_id]}",
            "failureReason": reason, "credit": "1",
        }

    def switch_on(self) -> List[Dict[str, Any]]:
        self.enabled = True
        return self.sent


_installed = Recorder(enabled=False)


def installed() -> Recorder:
    return _installed


def install(recorder: Recorder) -> None:
    global _installed
    _installed = recorder
