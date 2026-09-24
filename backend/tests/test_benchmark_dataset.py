from time import perf_counter

from conftest import run_db
from benchmark_dataset import FULL_PATIENTS, MARKER, seed, shape


def test_full_benchmark_dataset_matches_the_spec_and_seeds_within_a_minute(monkeypatch):
    async def run(db):
        started = perf_counter()
        result = await seed(db)
        elapsed = perf_counter() - started
        spec = shape(FULL_PATIENTS)
        counts = result["counts"]
        assert result["benchmark_marker"] == MARKER
        assert elapsed < 60, elapsed
        assert counts["patients"] == spec["patients"]
        assert counts["persons"] == spec["persons"]
        assert counts["users"] == spec["staff"]
        assert counts["reminder_ledger"] == spec["ledger"]
        assert counts["camp_days"] == 3
        assert counts["ot_schedule_days"] == 6
        assert counts["specs_collection_days"] == 3
        assert counts["deferred_slips"] == spec["ot_slips"] + spec["specs_slips"]
        assert await db.patients.count_documents({"arrived_at": {"$ne": None}}) == spec["arrived"]
        assert await db.patients.count_documents({"printed_at": {"$ne": None}}) == spec["printed"]
        assert await db.patients.count_documents({"committed_revision_id": {"$ne": None}}) == spec["completed"]
        lines = await db.fulfilments.distinct("item_type")
        assert set(lines) == {"medicine", "specs_fixed", "specs_made", "ot"}

    run_db(run)
