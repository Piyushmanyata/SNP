import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

import msg91
import routes_reminders
import sms
from conftest import advance_clock
from seed import TOMORROW, patient_doc, run_camp, seed_camp
from test_reminders import _run

PATIENTS = 20


async def _camp_of_twenty(database):
    camp_id, (day_id,) = await seed_camp(
        database, days=(TOMORROW,), name="Nadia Camp", venue="Hall A", camp_number=162,
    )
    await database.patients.insert_many([
        patient_doc(camp_id=camp_id, camp_day_id=day_id, full_name=f"Patient {n}",
                    phone=f"98765{n:05d}", phone_normalized=f"98765{n:05d}")
        for n in range(PATIENTS)
    ])


def test_a_hung_provider_cannot_hold_the_batch_past_its_lease(monkeypatch, sms_provider):
    provider = sms_provider
    provider.switch_on()
    provider.outcome = "hang"
    monkeypatch.setattr(sms, "SEND_SECONDS", 0.2)
    monkeypatch.setattr(routes_reminders, "SWEEP_SECONDS", 0.5)

    async def body(database, _client):
        await _camp_of_twenty(database)
        started = time.monotonic()
        first = await routes_reminders.send_d1_reminders()
        elapsed = time.monotonic() - started
        hung = {row["number"] for row in await database.reminder_ledger.find({"status": "uncertain"}).to_list(None)}

        provider.release()
        await asyncio.sleep(0.1)
        provider.outcome = "accept"
        later = []
        while not later or not later[-1]["complete"]:
            later.append(await routes_reminders.send_d1_reminders())
            assert len(later) < 10
        advance_clock(sms.RETRY_AFTER)
        await routes_reminders.send_d1_reminders()
        statuses = [row["status"] for row in await database.reminder_ledger.find({}).to_list(None)]
        return first, elapsed, hung, later, statuses

    try:
        first, elapsed, hung, later, statuses = _run(monkeypatch, body)
    finally:
        provider.release()
    assert first["complete"] is False
    assert elapsed < 0.5 + 0.2 + 0.5
    assert 4 <= len(hung) < PATIENTS
    assert sorted(statuses) == sorted(["uncertain"] * len(hung) + ["sent"] * (PATIENTS - len(hung)))
    assert not hung & {send["mobile"] for send in provider.sent}
    assert len(provider.sent) == PATIENTS - len(hung)


def test_a_send_still_queued_when_time_runs_out_is_withdrawn_not_guessed(monkeypatch, sms_provider):
    provider = sms_provider
    provider.switch_on()
    provider.outcome = "hang"
    monkeypatch.setattr(sms, "SEND_SECONDS", 0.2)
    monkeypatch.setattr(sms, "_sends", ThreadPoolExecutor(max_workers=1))

    async def run(_database):
        handed, queued = await asyncio.gather(
            sms._submit("camp", "9876500001", {}), sms._submit("camp", "9876500002", {}), return_exceptions=True,
        )
        return handed, queued

    try:
        handed, queued = run_camp(monkeypatch, run)
    finally:
        provider.release()
    assert isinstance(handed, TimeoutError)
    assert isinstance(queued, msg91.Unsent)


def test_time_spent_waiting_for_a_thread_does_not_eat_the_provider_s_answer_time(monkeypatch, sms_provider):
    sms_provider.switch_on()
    sms_provider.outcome = lambda *_args: time.sleep(0.15) or "provider-id"
    monkeypatch.setattr(sms, "SEND_SECONDS", 0.2)
    monkeypatch.setattr(sms, "_sends", ThreadPoolExecutor(max_workers=1))

    async def run(_database):
        return await asyncio.gather(sms._submit("camp", "9876500001", {}), sms._submit("camp", "9876500002", {}))

    assert run_camp(monkeypatch, run) == ["provider-id", "provider-id"]


def test_the_provider_s_own_socket_timeout_keeps_its_own_words(monkeypatch, sms_provider):
    sms_provider.switch_on()

    def socket_timeout(*_args):
        raise TimeoutError("The read operation timed out")

    sms_provider.outcome = socket_timeout

    async def run(_database):
        return await asyncio.gather(sms._submit("camp", "9876500001", {}), return_exceptions=True)

    (error,) = run_camp(monkeypatch, run)
    assert isinstance(error, TimeoutError)
    assert str(error) == "The read operation timed out"
