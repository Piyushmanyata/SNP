from collections import namedtuple
from datetime import timedelta

import pytest

import routes_reports
from routes_reports import camp_day_board, system_status
from seed import ADMIN, NOW, asgi_client, bearer, run_camp, seed_camp, user_doc

HOUR = timedelta(hours=1)
Usage = namedtuple("Usage", "total used free")


def _backup(**fields):
    return {
        "_id": "backup", "last_success_at": NOW - HOUR, "interval_seconds": 3600,
        "remote_configured": True, "remote_last_success_at": NOW - HOUR,
        "snapshot_id": "2f707196", "bytes": 2661, "patients_count": 50, **fields,
    }


def _disk(monkeypatch, free=80, total=100):
    monkeypatch.setattr(routes_reports.shutil, "disk_usage", lambda path: Usage(total, total - free, free))


def _status(monkeypatch, backup):
    async def body(database):
        if backup:
            await database.ops_status.insert_one(backup)
        await database.ops_status.update_one(
            {"_id": "reminders"},
            {"$set": {"heartbeat_at": NOW, "sweeps": {NOW.astimezone(routes_reports.IST).date().isoformat(): {"10": True, "20": True}}}},
            upsert=True,
        )
        return await system_status(actor=ADMIN)

    return run_camp(monkeypatch, body)


@pytest.mark.parametrize("backup, level", [
    (_backup(), "green"),
    (_backup(last_success_at=NOW - 2 * HOUR), "green"),
    (_backup(last_success_at=NOW - 2 * HOUR - timedelta(seconds=1)), "amber"),
    (_backup(remote_configured=False, remote_last_success_at=None), "amber"),
    (_backup(remote_last_success_at=NOW - 3 * HOUR), "amber"),
    (_backup(remote_last_success_at=None), "amber"),
    (_backup(last_error_at=NOW - HOUR, last_error="prune failed"), "amber"),
    (_backup(last_error_at=NOW - 2 * HOUR, last_error="dump failed"), "green"),
    (_backup(last_success_at=NOW - 6 * HOUR - timedelta(seconds=1)), "red"),
    (_backup(last_success_at=NOW - 7 * HOUR, remote_last_success_at=NOW - 7 * HOUR, interval_seconds=3 * 3600), "amber"),
    (_backup(last_success_at=NOW - 9 * HOUR - timedelta(seconds=1), interval_seconds=3 * 3600), "red"),
    (None, "red"),
])
def test_backup_level_follows_the_last_success(monkeypatch, backup, level):
    _disk(monkeypatch)
    result = _status(monkeypatch, backup)
    assert result["levels"]["backup"] == level
    assert result["status"] == level


@pytest.mark.parametrize("free, level", [(20, "green"), (19, "amber"), (10, "amber"), (9, "red")])
def test_disk_level_follows_free_space(monkeypatch, free, level):
    _disk(monkeypatch, free=free)
    result = _status(monkeypatch, _backup())
    assert result["disk"] == {"free_bytes": free, "total_bytes": 100}
    assert result["levels"]["disk"] == level
    assert result["status"] == level


def test_an_unmounted_backup_volume_reports_unknown_disk(monkeypatch):
    def missing(path):
        raise FileNotFoundError(path)

    monkeypatch.setattr(routes_reports.shutil, "disk_usage", missing)
    result = _status(monkeypatch, _backup())
    assert result["disk"] == "unknown"
    assert result["status"] == "green"


def test_the_backup_status_carries_the_error_message_only(monkeypatch):
    _disk(monkeypatch)
    result = _status(monkeypatch, _backup(last_error_at=NOW, last_error="dump failed", stray="not shown"))
    assert result["backup"] == {
        "last_success_at": (NOW - HOUR).isoformat(), "last_error_at": NOW.isoformat(), "last_error": "dump failed",
        "remote_configured": True, "remote_last_success_at": (NOW - HOUR).isoformat(),
        "interval_seconds": 3600, "bytes": 2661, "patients_count": 50,
    }


def test_only_an_admin_reads_the_system_status(monkeypatch):
    async def body(database):
        lead = (await database.users.insert_one(user_doc("Lead", "team_lead"))).inserted_id
        admin = (await database.users.insert_one(user_doc("Admin", "admin"))).inserted_id
        async with asgi_client() as client:
            refused = await client.get("/api/admin/system", headers=bearer(lead, "Lead", "team_lead"))
            allowed = await client.get("/api/admin/system", headers=bearer(admin, "Admin", "admin"))
        assert refused.status_code == 403
        assert allowed.status_code == 200, allowed.text
        assert allowed.json()["status"] == "red"

    run_camp(monkeypatch, body)


@pytest.mark.parametrize("backup, failing", [(_backup(), False), (_backup(remote_configured=False), False), (None, True)])
def test_the_board_flags_failing_backups_in_every_state(monkeypatch, backup, failing):
    _disk(monkeypatch)

    async def body(database):
        if backup:
            await database.ops_status.insert_one(backup)
        without_camp = await camp_day_board(actor=ADMIN)
        await seed_camp(database)
        with_camp = await camp_day_board(actor=ADMIN)
        return without_camp, with_camp

    without_camp, with_camp = run_camp(monkeypatch, body)
    assert without_camp["state"] == "no_camp"
    assert with_camp["state"] == "current"
    assert without_camp["backups_failing"] is failing
    assert with_camp["backups_failing"] is failing
