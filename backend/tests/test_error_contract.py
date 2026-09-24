"""Every API error is built by helpers.api_error."""
from pathlib import Path


def test_http_exception_is_only_constructed_in_api_error():
    root = Path(__file__).resolve().parents[1]
    offenders = []
    for path in root.glob("*.py"):
        if path.name == "helpers.py":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "HTTPException(" in line:
                offenders.append(f"{path.name}:{number}")
    assert offenders == []
