# Can the 2-vCPU VPS hold the camp-day peak?

Issue #76. Researched 2026-09-26 from the repo, ADR 0068, the CI perf budgets, the throughput model (#71) and the live VPS per-path p95s measured from backend JSON logs on 2026-09-25. No load test was run.

## Answer

- **Yes, the 2-vCPU VPS is enough for 5,000 patients a day.** Peak demand is about 6.5 requests/s, using at most about 0.4 of the 2 vCPU on the CI budgets and about 0.15 of it on the live p95s. That is 5× to 15× headroom.
- **No budgeted endpoint is expected to go over its budget at peak.** The busiest query path is the desk scan, which costs at most about 75 ms of CPU a call.
- **The endpoints at risk are the ones without a budget.** `/aadhaar/extract` can take both vCPU. The login burst at shift start takes seconds of bcrypt time. `/self-register` has a per-IP limit that mobile carrier NAT can hit.
- **Do not add uvicorn workers.** The rate limits and the extract slots live in each process, so every extra worker multiplies them.

## Demand at peak

| Source | Rate | Evidence |
|---|---|---|
| Desk work, 5,000 in 6 h, 1.5× peak, about 10 calls a patient | 3.5 req/s | throughput model, "Server headroom" (`origin/research/throughput-model:docs/research/throughput-model.md:90`) |
| Desk poll: `/kpis` + `/camps/active` every 30 s, up to 37 desks | ≤ 2.5 req/s | `frontend/src/pages/Desk.js:35`, `:129`, `:154` (skipped while the tab is hidden) |
| Board poll: `/board` every 15 s, assuming about 5 leads | about 0.3 req/s | `frontend/src/pages/Board.js:8`, `:25`, `:39` |
| **Total** | **about 6.3 req/s** | |

Correction to #71: the throughput model counts only the requests each patient makes. The desk and board polls come on top and nearly double the rate. With them, the headroom is about 4× on the CI budgets, not 7×.

## Supply: scaling the CI budget to the VPS

- The CI perf run measures p95 at concurrency 8 after 20 warm-ups, on a 20,000-patient camp, with an in-process httpx ASGI client. CPU on that runner is taken by MongoDB (`docs/adr/0068-performance-budgets.md:11`, `backend/tests/benchmark_http.py:12-27`).
- Little's law gives throughput X = 8 / mean latency. The mean is at most the p95, so X ≥ 8 / p95. On 4 vCPU, the CPU cost of one call is therefore at most 4 / X ≤ **p95 / 2**. This is an upper bound: it assumes all four cores were busy and counts the in-process client as server work.
- That gives these upper bounds on CPU per call: desk scan ≤ 75 ms (≤ 67 ms at the measured 134 ms), KPIs ≤ 50 ms, `/camps/active` ≤ 25 ms, register ≤ 100 ms, board ≤ 150 ms (`benchmark_http.py:13-21`).
- On 2 vCPU: 2 cores / 75 ms ≈ **27 desk-scan-weight req/s**. This matches the model's "about 25 req/s". The #71 figure holds as a floor, but "divide by two" only works because the per-call CPU bound is linear in cores.
- Peak CPU on the budgets: 3.5 × 75 ms + 2.5 × 50 ms + 0.33 × 150 ms ≈ 0.44 core-seconds per second, or **about 22% of 2 vCPU**. On the live numbers (nearly every path p95 < 20 ms near idle, which caps a call's CPU at 20 ms): 6.3 × 20 ms ≈ 0.13 cores, or **about 6%**.
- One uvicorn process serves the API: `backend/Dockerfile:16` sets no `--workers`, so the default of 1 applies. Python-side work is therefore capped at one core. At 6.3 req/s and a few ms of Python per call, that cap is far away.
- Memory limits add up to 5.4 GB: mongo 3g (WiredTiger 2 GB), backend 1g, backup 768m, caddy and reminders 256m each, frontend 128m (`docker-compose.prod.yml:13-14`, `:35`; ADR 0068:11). That fits in the 6.8 GB free.

## Endpoints at risk

1. **`/aadhaar/extract`: CPU and memory.**
   - Each upload runs in its own subprocess, capped by `Semaphore(2)`. When both slots are busy, the next upload gets an immediate `429 QR_BUSY` instead of waiting in a queue (`backend/aadhaar_extract.py:16`, `:24-29`, `:87-89`). That caps extraction at about 2 / 1.4 s ≈ 1.4 uploads/s.
   - Two busy slots can take both vCPU for up to 25 s of CPU each (`RLIMIT_CPU`, `backend/aadhaar_document.py:73`). Desk calls then share the CPU with them, so desk latency rises for as long as the uploads keep coming. This is the only path that can use up the headroom.
   - Each subprocess is allowed 1 GB of address space (`aadhaar_document.py:72`). Both run inside the backend container's 1g limit (`docker-compose.prod.yml:35`), so two large HEIC or PDF files could OOM-kill a process in that container.
   - Cheapest fixes, not built yet: lower the worker's priority (`os.nice` next to the `setrlimit` calls) or use `Semaphore(1)` on this host.
2. **Login burst at shift start.**
   - `bcrypt.gensalt()` uses its default of 12 rounds (`backend/security.py:17`). Verification runs through `asyncio.to_thread` (`backend/routes_auth.py:83`), so it does not block the event loop.
   - Python's default thread pool has `min(32, cpu_count + 4)` = 6 threads on 2 vCPU (Python docs, `concurrent.futures.ThreadPoolExecutor`). At about 0.25 s of CPU per hash (an estimate, not measured here), 37 simultaneous logins take about 9 core-seconds and clear in about 5 s.
   - During that burst, `decode_aadhaar` calls from the desks (`routes_desk.py:59`, `routes_registration.py:55`) wait behind the logins for a few seconds.
   - Mitigation: stagger sign-in over a minute. No code change is needed.
3. **`/self-register` pre-registration surge.**
   - Limits: 30 requests per client IP per 10 minutes for self-register, and 60 for decode (`backend/routes_registration.py:26-27`, `:31-41`). Extract allows 12 per IP per 10 minutes and tracks at most 2,048 IPs (`aadhaar_extract.py:61-65`).
   - Uvicorn trusts `X-Forwarded-For` from any proxy (`--forwarded-allow-ips *`, `backend/Dockerfile:16`), so the client IP is the phone's public IP. On mobile carrier NAT, many households share one IP, so an SMS blast can hit 429s well below any CPU limit.
   - The CPU cost is small: register is about 170 ms of wall time live, so even 1 req/s is under 0.2 core.
   - This is a throttling risk, not a capacity risk. Check the 429 count in the live logs after the first blast.

Prescription printing adds no server CPU. The backend has no PDF or render library (the only PIL imports are in `aadhaar_document.py:18` and `routes_templates.py:9`), and printing goes through the browser's `--kiosk-printing`. `/desk/print/{id}` returns data (`frontend/src/pages/Desk.js:288`).

## Not verified

- No load test was run on the VPS. The per-call CPU figures are upper bounds derived from CI p95, not measured.
- The bcrypt cost per hash on the VPS CPU was not measured, and neither was whether pyca/bcrypt releases the GIL.
- The number of leads with a board open is assumed to be 5.
- Whether clinical desks run the `Desk.js` poll was not checked. Counting all 37 is the upper bound.
