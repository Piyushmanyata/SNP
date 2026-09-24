import json
import math
import os
import statistics
import threading
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter

import requests


def benchmark() -> None:
    origin = os.environ["SNP_LIVE_API"].rstrip("/")
    credentials = {"name": os.environ["SNP_TEST_ADMIN_NAME"], "pin": os.environ["SNP_TEST_ADMIN_PIN"]}
    with requests.Session() as auth:
        login = auth.post(f"{origin}/api/auth/login", json=credentials, timeout=30)
        login.raise_for_status()
        token = login.cookies["access_token"]
        summary = auth.get(f"{origin}/api/kpis", timeout=30)
        summary.raise_for_status()
        registered = summary.json().get("registered", 0)
    results = []
    for path in ("/api/kpis", "/api/board"):
        for concurrency in (1, 8):
            local = threading.local()
            sessions = []

            def request_once(_):
                if not hasattr(local, "session"):
                    local.session = requests.Session()
                    local.session.headers["Authorization"] = f"Bearer {token}"
                    sessions.append(local.session)
                started = perf_counter()
                response = local.session.get(f"{origin}{path}", timeout=30)
                response.raise_for_status()
                response.json()
                return (perf_counter() - started) * 1000

            try:
                with ThreadPoolExecutor(max_workers=concurrency) as executor:
                    list(executor.map(request_once, range(8)))
                    started = perf_counter()
                    timings = list(executor.map(request_once, range(100)))
                    elapsed = perf_counter() - started
            finally:
                for session in sessions:
                    session.close()
            timings.sort()
            results.append({
                "path": path,
                "requests": len(timings),
                "errors": 0,
                "concurrency": concurrency,
                "p50_ms": round(statistics.median(timings), 2),
                "p95_ms": round(timings[math.ceil(len(timings) * 0.95) - 1], 2),
                "max_ms": round(timings[-1], 2),
                "requests_per_second": round(len(timings) / elapsed, 2),
            })
    print(json.dumps({"origin": origin, "active_camp_registered": registered, "warmups_per_case": 8, "results": results}, indent=2))


if __name__ == "__main__":
    benchmark()
