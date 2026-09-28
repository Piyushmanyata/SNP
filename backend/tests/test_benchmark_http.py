import asyncio
import os

import pytest

from benchmark_http import WARMUPS, breaches, time_calls


def test_one_stalled_concurrency_8_batch_does_not_move_the_p95():
    calls = 0

    async def call():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.2 if WARMUPS < calls <= WARMUPS + 8 else 0)

    result = asyncio.run(time_calls(call, 8))
    assert result["max_ms"] >= 200
    assert result["p95_ms"] < 100


def test_a_concurrency_8_p95_over_the_budget_is_a_breach():
    assert breaches([{"name": "kpis", "concurrency": 8, "p95_ms": 101}]) == ["kpis p95 101ms > 100ms"]
    assert breaches([{"name": "kpis", "concurrency": 1, "p95_ms": 500}]) == []
    assert breaches([{"name": "camp_records", "first_byte_s": 1.1, "total_s": 2, "rss_growth_mb": 1}])


@pytest.mark.skipif(os.environ.get("SNP_PERF") != "1", reason="Set SNP_PERF=1 to measure the 20000-patient budgets")
def test_seeded_camp_meets_the_p95_budgets(monkeypatch):
    import json
    from conftest import run_db
    from benchmark_dataset import seed
    from benchmark_http import breaches, run_in_process, write_report

    async def run(db):
        os.environ.setdefault("ADMIN_BOOTSTRAP_PIN", "864200")
        seeded = await seed(db)
        results = await run_in_process(seeded)
        path = os.environ.get("SNP_BENCHMARK_JSON")
        failed = write_report(results, path) if path else breaches(results)
        assert not failed, json.dumps(results)

    run_db(run)
