"""S10: ledger-first SMS, sweep lease, outbox, and reminder health."""
from datetime import timedelta

import pytest

import helpers
import msg91
import routes_reminders
import sms
from conftest import CommandLog
from routes_reminders import drain_outbox, send_d1_reminders
from routes_reports import system_status
from seed import ADMIN, NOW, TODAY, TOMORROW, patient_doc, run_camp, seed_camp
from test_reminders import HOUSEHOLD, _post, _run, _seed_camp_household
from test_system_status import Usage, _backup


def _disk(monkeypatch):
    monkeypatch.setattr("routes_reports.shutil.disk_usage", lambda path: Usage(100, 20, 80))


def test_rejected_canary_pauses_after_one_send(monkeypatch):
    def reject(*_args):
        raise msg91.Rejected("low balance")

    monkeypatch.setattr(msg91, "send_dlt_sms", reject)

    async def body(database, client):
        await _seed_camp_household(database, n_patients=3)
        first = (await _post(client)).json()
        second = (await _post(client)).json()
        assert first["used"] == 1
        assert second["paused"] is True
        assert second["used"] == 1
        assert await sms.paused(database, "camp")
        assert await database.reminder_ledger.count_documents({"status": "rejected"}) == 1

    _run(monkeypatch, body, canary=True)


def test_a_held_lease_does_not_start_another_sweep(monkeypatch):
    monkeypatch.setattr(msg91, "configured", lambda: True)
    monkeypatch.setattr(msg91, "send_dlt_sms", lambda *_args: pytest.fail("sent during a held lease"))

    async def body(database):
        camp_id, _day = await seed_camp(database, days=(TOMORROW,), venue="Hall A")
        await database.patients.insert_one(patient_doc(
            camp_id=camp_id, phone=HOUSEHOLD, phone_normalized=HOUSEHOLD,
        ))
        await database.sms_controls.insert_one({
            "_id": "reminder_lease", "holder": "other", "expires_at": NOW + timedelta(minutes=2),
            "cursor": {"camp": "held"},
        })
        result = await send_d1_reminders()
        assert result["waiting"] is True
        assert result["sent"] == 0
        lease = await database.sms_controls.find_one({"_id": "reminder_lease"})
        assert lease["cursor"]["camp"] == "held"
        assert lease["holder"] == "other"

    run_camp(monkeypatch, body)


async def _open(*_args):
    return "open"


async def _gate_open(*_args):
    return "open"


def test_sweep_does_not_reread_the_ledger_per_patient(monkeypatch):
    log = CommandLog()
    monkeypatch.setattr(msg91, "configured", lambda: True)
    monkeypatch.setattr(msg91, "send_dlt_sms", lambda *_args: "id")
    monkeypatch.setattr(routes_reminders, "_gate", _gate_open)

    async def body(database):
        camp_id, (day_id,) = await seed_camp(database, days=(TOMORROW,), venue="Hall A")
        patients = [
            patient_doc(
                camp_id=camp_id, camp_day_id=day_id, phone=HOUSEHOLD, phone_normalized=HOUSEHOLD,
                reg_no=i, patient_qr=f"s10-{i}",
            )
            for i in range(1000)
        ]
        await database.patients.insert_many(patients)
        await database.reminder_ledger.insert_many([
            {
                "patient_id": patient["_id"], "message_type": "camp", "event_date": TOMORROW,
                "event_key": None, "status": "sent", "created_at": NOW, "camp_id": camp_id,
            }
            for patient in patients[:900]
        ])
        log.commands.clear()
        await send_d1_reminders()
        finds = [name for name, target in log.commands if name == "find" and target == "reminder_ledger"]
        pages = 5
        assert len(finds) <= pages + 100

    run_camp(monkeypatch, body, listener=log)


def test_outbox_sends_old_queued_rows_and_retires_stale_pending(monkeypatch):
    calls = []
    monkeypatch.setattr(msg91, "configured", lambda: True)
    monkeypatch.setattr(msg91, "send_dlt_sms", lambda *_args: calls.append(1) or "id")

    async def body(database):
        camp_id, _day = await seed_camp(database)
        patient = patient_doc(camp_id=camp_id, phone=HOUSEHOLD, phone_normalized=HOUSEHOLD, reg_no=7)
        await database.patients.insert_one(patient)
        old = {
            "patient_id": patient["_id"], "message_type": "registration", "event_date": TODAY,
            "event_key": "old", "number": HOUSEHOLD, "status": "queued", "attempts": 0,
            "variables": {"reg_no": "7"}, "camp_id": camp_id, "created_at": NOW - timedelta(seconds=31),
        }
        fresh = {**old, "event_key": "fresh", "created_at": NOW}
        pending = {**old, "event_key": "pending", "status": "pending", "created_at": NOW - timedelta(minutes=6)}
        await database.reminder_ledger.insert_many([old, fresh, pending])
        await drain_outbox()
        assert len(calls) == 1
        assert (await database.reminder_ledger.find_one({"event_key": "old"}))["status"] == "sent"
        assert (await database.reminder_ledger.find_one({"event_key": "fresh"}))["status"] == "queued"
        assert (await database.reminder_ledger.find_one({"event_key": "pending"}))["status"] == "uncertain"
        await drain_outbox()
        assert len(calls) == 1

    run_camp(monkeypatch, body)


def test_http_429_and_503_are_failed_with_a_retry_delay(monkeypatch):
    class Response:
        status = 503

        def read(self):
            return b"{}"

    class Conn:
        def connect(self):
            return None

        def request(self, *_args, **_kwargs):
            return None

        def getresponse(self):
            return Response()

        def close(self):
            return None

    monkeypatch.setattr(msg91.http.client, "HTTPSConnection", lambda *_args, **_kwargs: Conn())
    monkeypatch.setenv("MSG91_AUTH_KEY", "auth")
    monkeypatch.setenv("MSG91_TEMPLATE_CAMP", "tmpl")
    with pytest.raises(msg91.Throttled):
        msg91.send_dlt_sms("camp", HOUSEHOLD, {"reg_no": "1"})
    Response.status = 429
    with pytest.raises(msg91.Throttled):
        msg91.send_dlt_sms("camp", HOUSEHOLD, {"reg_no": "1"})

    async def body(database):
        camp_id, _day = await seed_camp(database, days=(TODAY,), venue="Hall A")
        patient = patient_doc(
            camp_id=camp_id, phone=HOUSEHOLD, phone_normalized=HOUSEHOLD, reg_no=8,
        )
        await database.patients.insert_one(patient)
        monkeypatch.setattr(msg91, "configured", lambda: True)
        monkeypatch.setattr(msg91, "template_id", lambda _kind: "tmpl")
        monkeypatch.setattr(msg91, "send_dlt_sms", lambda *_args: (_ for _ in ()).throw(msg91.Throttled("HTTP 503")))
        assert await sms.deliver_patient_sms(database, patient, "camp", TODAY, "Hall A") == "failed"
        row = await database.reminder_ledger.find_one({"patient_id": patient["_id"]})
        assert row["status"] == "failed"
        assert helpers.as_utc(row["retry_after"]) - helpers.now_utc() >= timedelta(minutes=4, seconds=50)

    run_camp(monkeypatch, body)


@pytest.mark.parametrize("ist,done,level", [
    ("2026-10-05T09:00", {}, "green"),
    ("2026-10-05T10:29", {}, "green"),
    ("2026-10-05T10:30", {}, "red"),
    ("2026-10-05T10:30", {"10": True}, "green"),
    ("2026-10-05T20:30", {"10": True}, "red"),
    ("2026-10-05T20:30", {"10": True, "20": True}, "green"),
])
def test_reminder_health_thresholds(monkeypatch, ist, done, level):
    _disk(monkeypatch)

    async def body(database):
        await database.ops_status.insert_many([
            _backup(),
            {"_id": "reminders", "heartbeat_at": helpers.now_utc(), "sweeps": {ist[:10]: done}},
        ])
        stale = await system_status(actor=ADMIN)
        await database.ops_status.update_one(
            {"_id": "reminders"}, {"$set": {"heartbeat_at": helpers.now_utc() - timedelta(minutes=6)}},
        )
        aged = await system_status(actor=ADMIN)
        return stale["levels"]["reminders"], aged["levels"]["reminders"]

    fresh, aged = run_camp(monkeypatch, body, ist=ist)
    assert fresh == level
    assert aged == "red"


def test_two_thousand_targets_finish_under_three_minutes(monkeypatch):
    import time

    monkeypatch.setenv("MSG91_AUTH_KEY", "auth")
    monkeypatch.setenv("MSG91_TEMPLATE_CAMP", "tmpl")
    monkeypatch.setenv("MSG91_TEMPLATE_OT", "tmpl")
    monkeypatch.setenv("MSG91_TEMPLATE_SPECS", "tmpl")
    monkeypatch.setattr(routes_reminders, "_gate", _gate_open)

    def slow(*_args):
        time.sleep(0.2)
        return "id"

    monkeypatch.setattr(msg91, "send_dlt_sms", slow)

    async def body(database):
        camp_id, (day_id,) = await seed_camp(database, days=(TOMORROW,), venue="Hall A")
        await database.patients.insert_many([
            patient_doc(
                camp_id=camp_id, camp_day_id=day_id, phone=HOUSEHOLD, phone_normalized=HOUSEHOLD,
                reg_no=i, patient_qr=f"bulk-{i}",
            )
            for i in range(2000)
        ])
        routes_reminders.SWEEP_SECONDS = 300
        started = time.monotonic()
        result = {"complete": False}
        for _ in range(12):
            result = await send_d1_reminders()
            if result["complete"]:
                break
        assert result["complete"] is True
        assert time.monotonic() - started < 180
        assert await database.reminder_ledger.count_documents({"status": "sent"}) == 2000

    run_camp(monkeypatch, body)
