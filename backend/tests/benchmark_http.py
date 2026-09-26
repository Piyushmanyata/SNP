"""p95 budgets for a camp of 20,000 patients. A breach exits non-zero."""

import asyncio
import json
import math
import os
import statistics
import sys
from time import perf_counter
from uuid import uuid4

BUDGETS_MS = {
    "desk_scan_arrived": 150,
    "register": 200,
    "clinical_search": 150,
    "clinical_lookup": 150,
    "fulfilment": 250,
    "kpis": 100,
    "board": 300,
    "leaderboard": 400,
    "active_public_camp": 50,
}
EXPORT_FIRST_BYTE_S = 1
EXPORT_TOTAL_S = 15
EXPORT_RSS_GROWTH_MB = 80
WARMUPS = 20
SAMPLES = 40


def percentile(timings: list[float], fraction: float) -> float:
    ordered = sorted(timings)
    return ordered[math.ceil(len(ordered) * fraction) - 1]


def rss_bytes() -> int:
    if sys.platform == "win32":
        import ctypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb,
        )
        return int(counters.WorkingSetSize)
    with open("/proc/self/status", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    return 0


async def time_calls(call, concurrency: int, warmups: int = WARMUPS, samples: int = SAMPLES) -> dict:
    for _ in range(warmups):
        await call()
    timings = []
    remaining = samples

    async def once():
        started = perf_counter()
        await call()
        return (perf_counter() - started) * 1000

    while remaining:
        batch = min(concurrency, remaining)
        timings.extend(await asyncio.gather(*(once() for _ in range(batch))))
        remaining -= batch
    return {
        "requests": len(timings),
        "concurrency": concurrency,
        "p50_ms": round(statistics.median(timings), 2),
        "p95_ms": round(percentile(timings, 0.95), 2),
        "max_ms": round(max(timings), 2),
    }


def breaches(results: list[dict]) -> list[str]:
    found = []
    for row in results:
        limit = BUDGETS_MS.get(row["name"])
        if row.get("concurrency") == 8 and limit is not None and row["p95_ms"] > limit:
            found.append(f"{row['name']} p95 {row['p95_ms']}ms > {limit}ms")
        if row["name"] == "camp_records":
            if row["first_byte_s"] > EXPORT_FIRST_BYTE_S:
                found.append(f"camp_records first byte {row['first_byte_s']}s")
            if row["total_s"] > EXPORT_TOTAL_S:
                found.append(f"camp_records total {row['total_s']}s")
            if row["rss_growth_mb"] > EXPORT_RSS_GROWTH_MB:
                found.append(f"camp_records rss {row['rss_growth_mb']}MB")
    return found


def scan_body() -> dict:
    from xml.etree.ElementTree import Element, tostring
    return {"payload": tostring(Element(
        "PrintLetterBarcodeData", name="Sunita Devi", gender="F", dob="1975-06-14",
        uid="123456781234", street="12 Station Road Sikar",
    ), encoding="unicode")}


async def measure_api(client, seeded: dict) -> list[dict]:
    from security import create_access_token
    admin = create_access_token(seeded["admin_id"], "Benchmark admin", "admin")
    clinical = create_access_token(seeded["clinical_id"], "Benchmark clinical", "clinical_desk_operator")
    pool = list(seeded["fulfil"])
    register_n = 0

    async def hit(method, path, token, **kwargs):
        response = await client.request(method, path, headers={"Authorization": f"Bearer {token}"}, **kwargs)
        response.raise_for_status()
        return response

    async def desk_scan():
        await hit("POST", "/api/desk/scan", admin, json=scan_body())

    async def register():
        nonlocal register_n
        register_n += 1
        await hit("POST", "/api/register", admin, json={
            "full_name": f"Bench Register {register_n} {uuid4().hex[:8]}",
            "age": 40, "gender": "F", "phone": f"97{register_n:08d}",
            "address": "Bench road", "camp_day_id": seeded["day_id"],
            "registration_request_id": str(uuid4()), "manual_reason": "no_card",
        })

    async def clinical_search():
        await hit("GET", "/api/clinical/search", clinical, params={"q": "synthetic"})

    async def clinical_lookup():
        await hit("POST", "/api/clinical/lookup", clinical, json={"value": seeded["lookup_qr"]})

    async def fulfilment():
        item = pool.pop()
        await hit("POST", "/api/clinical/fulfilment", clinical, json={
            "transcription_id": item["transcription_id"], "item_type": "medicine", "status": "fulfilled",
            "paper_reviewed": True, "reviewed_revision_id": item["revision_id"],
            "reviewed_generation": item["generation"], "operation_id": str(uuid4()),
            "medicine_outcomes": [{"medicine_id": seeded["medicine_id"], "given": True}],
        })

    calls = {
        "desk_scan_arrived": desk_scan,
        "register": register,
        "clinical_search": clinical_search,
        "clinical_lookup": clinical_lookup,
        "fulfilment": fulfilment,
        "kpis": lambda: hit("GET", "/api/kpis", admin),
        "board": lambda: hit("GET", "/api/board", admin),
        "leaderboard": lambda: hit("GET", "/api/leaderboard", admin),
        "active_public_camp": lambda: hit("GET", "/api/camps/active/public", admin),
    }
    results = []
    for name, call in calls.items():
        for concurrency in (1, 8):
            results.append({"name": name, **await time_calls(call, concurrency)})
    from server import app
    before = rss_bytes()
    started = perf_counter()
    first = None
    peak = before
    asked = False

    async def receive():
        nonlocal asked
        if not asked:
            asked = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        nonlocal first, peak
        if message["type"] == "http.response.body" and message.get("body"):
            now = perf_counter()
            peak = max(peak, rss_bytes())
            if first is None:
                first = now

    await app({
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
        "scheme": "http", "path": "/api/exports/camp-records", "raw_path": b"/api/exports/camp-records",
        "query_string": b"", "headers": [(b"authorization", f"Bearer {admin}".encode())],
        "client": ("127.0.0.1", 123), "server": ("benchmark", 80), "state": {},
    }, receive, send)
    finished = perf_counter()
    results.append({
        "name": "camp_records",
        "first_byte_s": round((first or finished) - started, 3),
        "total_s": round(finished - started, 3),
        "rss_growth_mb": round(max(0, peak - before) / (1024 * 1024), 1),
    })
    return results


def write_report(results: list[dict], path: str) -> list[str]:
    failed = breaches(results)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"warmups": WARMUPS, "samples": SAMPLES, "results": results, "breaches": failed}, handle, indent=2)
    return failed


async def run_in_process(seeded: dict) -> list[dict]:
    import httpx
    from server import app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://benchmark") as client:
        return await measure_api(client, seeded)


def main() -> None:
    """Read-only check against a server that already holds the benchmark camp."""
    import concurrent.futures
    import requests
    origin = os.environ["SNP_LIVE_API"].rstrip("/")
    credentials = {"name": os.environ["SNP_TEST_ADMIN_NAME"], "pin": os.environ["SNP_TEST_ADMIN_PIN"]}
    with requests.Session() as session:
        login = session.post(f"{origin}/api/auth/login", json=credentials, timeout=30)
        login.raise_for_status()
        token = login.cookies["access_token"]

        def once(path):
            started = perf_counter()
            response = session.get(
                f"{origin}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=30,
            )
            response.raise_for_status()
            response.json()
            return (perf_counter() - started) * 1000

        results = []
        for path, name in (
            ("/api/kpis", "kpis"), ("/api/board", "board"),
            ("/api/leaderboard", "leaderboard"), ("/api/camps/active/public", "active_public_camp"),
        ):
            for concurrency in (1, 8):
                for _ in range(WARMUPS):
                    once(path)
                with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
                    timings = list(pool.map(lambda _: once(path), range(SAMPLES)))
                results.append({
                    "name": name, "requests": len(timings), "concurrency": concurrency,
                    "p50_ms": round(statistics.median(timings), 2),
                    "p95_ms": round(percentile(timings, 0.95), 2),
                    "max_ms": round(max(timings), 2),
                })
    path = os.environ.get("SNP_BENCHMARK_JSON", "benchmark.json")
    failed = write_report(results, path)
    print(json.dumps({"path": path, "breaches": failed}, indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
