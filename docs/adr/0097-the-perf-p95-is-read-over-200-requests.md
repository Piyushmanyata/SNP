# 0097. The perf p95 is read over 200 requests

The perf job read each p95 from 40 requests. At concurrency 8 the requests are timed in `asyncio.gather` batches of 8, so one runner stall slows a whole batch: 8 of 40 samples, 20%, and the p95 is the stalled time. On 2026-09-28 this failed four runs that passed on a re-run: `active_public_camp` 61.5 > 50 ms, `board` 311 and 360 > 300 ms, and `desk_scan_arrived` 150.8 > 150 ms with p50 unchanged at about 105 ms.

Each endpoint now takes 200 requests after the 20 warm-ups (`SAMPLES` in `benchmark_http.py`). One stalled batch is 8 of 200, 4%, which is below the p95; 10 slow requests are needed to move it. The benchmark camp leaves 480 completed patients without fulfilments, enough for the 440 fulfilments the run writes. The budgets in ADR 0068 are unchanged, and a regression that slows the typical request still fails: PR 100 took `/api/kpis` p50 from 64 to 125 ms, above its 100 ms p95 budget at any sample size. A local run takes 55 s; the job has 25 minutes.

Rejected: retrying a failing endpoint once. That reads the lower of two p95s, so a tail regression that shows in half the runs passes.
Rejected: a p50 budget with a looser p95. That raises the budgets ADR 0068 holds.
Rejected: the median of several 40-request p95s, or a trimmed p95. Each needs the same 200 requests and more code, and a trimmed p95 is a higher percentile under another name.

Consequence: the perf job takes about five times longer to measure. Several stalls in one endpoint can still fail it, and that failure is re-run only after checking that p50 is unchanged.
