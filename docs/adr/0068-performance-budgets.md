# 0068. Performance budgets are measured on one 20,000-patient camp

A camp day is polled by every lead and searched by every desk. Counts and lookups have to stay on indexes once that camp holds 20,000 patients.

The benchmark marker is `snp-benchmark-20000-v2`. It is one camp: 3 camp days, 18,000 persons, 20,000 patients (2,000 manual, so the person-in-camp unique index still holds), 70% arrived, 65% printed, 60% completed, fulfilments on all four lines, 2,500 OT slips over 6 days, 1,500 specs slips over 3 days, 80,000 ledger rows and 40 staff. Inserts are batches of 1,000.

`backend/tests/test_query_plans.py` explains the desk, clinical, board, KPI, leaderboard, reminder, canary, slip and fulfilment queries on 2,000 of those patients and fails if a winning plan is a collection scan. `fulfilments.operation_id` is unique when it is a string. A fulfilment stores `camp_id` and the patient's `seen_at`, so the board groups that line without loading every seen patient. Reminder health groups on `{camp_id, created_at}`. The HTTP middleware is raw ASGI, so the export header is not held until the file is finished. httpx's ASGI transport buffers the body, so the export budget is read from the first ASGI body message.

The corrections collection was removed in S7. A correction is a prescription revision, read by `_id`. There is no `corrections.revision_id` index.

p95 at concurrency 8, after 20 warm-ups, fails the perf run (`SNP_PERF=1`) when it passes the budgets in `benchmark_http.py`. On this machine that run met register, clinical search, clinical lookup, fulfilment, KPIs, the public camp and the export (first byte 3 ms, total 1.9 s). Desk scan, the board and the leaderboard were over budget at concurrency 8, so the run exits non-zero. The budgets are not raised. Container memory limits are mongo 3g (WiredTiger cache 2 GB), backend 1g, reminders 256m, frontend 128m, caddy 256m, backup 768m. Coverage fail-under is set from the suite measured at the end of S15, not from a guess.
