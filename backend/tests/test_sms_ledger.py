"""The SMS intent ledger through its verbs, with the in-memory provider and `now` passed in."""

from datetime import timedelta

import pytest
from bson import ObjectId

import sms
from conftest import run_db
from db import in_transaction
from helpers import as_utc
from seed import NOW, TOMORROW, patient_doc, seed_camp

HOUSEHOLD = "9876500001"


def _run(body):
    return run_db(body)


async def _patient(database, **fields):
    camp_id, _ = await seed_camp(database, venue="Hall A")
    patient = patient_doc(camp_id=camp_id, phone=HOUSEHOLD, phone_normalized=HOUSEHOLD, **fields)
    await database.patients.insert_one(patient)
    return patient


async def _send(database, patient, message_type="camp", *, now=NOW, **kwargs):
    return await sms.record_and_send(database, patient, message_type, TOMORROW, "Hall A", now=now, **kwargs)


async def _row(database):
    return await database.reminder_ledger.find_one({})


async def _recorded(database, patient, message_type="ot_token", event_key="token-1"):
    async def write(session):
        return await sms.record(
            database, [patient], message_type, TOMORROW, "Hall A", event_key=event_key, session=session, now=NOW,
        )
    return await in_transaction(write)


@pytest.mark.parametrize("outcome,status", [
    ("accept", "sent"), ("unsent", "failed"), ("throttled", "failed"), ("rejected", "rejected"), ("unknown", "uncertain"),
])
def test_a_provider_outcome_settles_the_intent(sms_provider, outcome, status):
    sms_provider.switch_on()
    sms_provider.script(outcome)

    async def body(database):
        patient = await _patient(database)
        assert await _send(database, patient) == status
        row = await _row(database)
        assert row["status"] == status
        assert row["attempts"] == 1
        if outcome == "throttled":
            assert as_utc(row["retry_after"]) == NOW + sms.THROTTLE_BACKOFF
        if outcome == "accept":
            assert row["provider_id"] == "id-1"

    _run(body)


def test_an_intent_recorded_in_a_transaction_is_queued_or_paused(sms_provider):
    sms_provider.switch_on()

    async def body(database):
        patient = await _patient(database)
        [queued] = await _recorded(database, patient)
        assert (await database.reminder_ledger.find_one({"_id": queued}))["status"] == "queued"
        await database.sms_controls.insert_one({"_id": "specs_token", "paused": True})
        assert await _recorded(database, patient, "specs_token") == []
        assert (await database.reminder_ledger.find_one({"message_type": "specs_token"}))["status"] == "paused"

    _run(body)


def test_the_sweep_sends_a_queued_intent_only_after_thirty_seconds(sms_provider):
    sms_provider.switch_on()

    async def body(database):
        patient = await _patient(database)
        await _recorded(database, patient)
        assert await sms.sweep(database, NOW + timedelta(seconds=29), 200) == (0, 0)
        assert await sms.sweep(database, NOW + sms.QUEUED_RESEND_AFTER, 200) == (1, 0)
        assert (await _row(database))["status"] == "sent"
        assert len(sms_provider.sent) == 1

    _run(body)


def test_a_pending_intent_becomes_uncertain_after_five_minutes_and_is_never_resent(sms_provider):
    sms_provider.switch_on()

    async def body(database):
        patient = await _patient(database)
        [row_id] = await _recorded(database, patient)
        await database.reminder_ledger.update_one({"_id": row_id}, {"$set": {"status": "pending"}})
        await sms.sweep(database, NOW + timedelta(minutes=4), 200)
        assert (await _row(database))["status"] == "pending"
        await sms.sweep(database, NOW + sms.PENDING_UNCERTAIN_AFTER, 200)
        assert (await _row(database))["status"] == "uncertain"
        await sms.sweep(database, NOW + timedelta(hours=1), 200)
        assert sms_provider.sent == []

    _run(body)


def test_a_throttled_intent_is_retried_by_the_sweep_after_five_minutes(sms_provider):
    sms_provider.switch_on()
    sms_provider.script("throttled")

    async def body(database):
        patient = await _patient(database)
        await _send(database, patient)
        assert await sms.sweep(database, NOW + timedelta(minutes=4), 200) == (0, 0)
        assert await sms.sweep(database, NOW + sms.THROTTLE_BACKOFF, 200) == (0, 1)
        assert (await _row(database))["status"] == "sent"

    _run(body)


def test_a_failed_reminder_is_due_again_only_after_ten_minutes(sms_provider):
    sms_provider.switch_on()
    sms_provider.script("unsent")

    async def body(database):
        patient = await _patient(database)
        await _send(database, patient)
        assert await sms.due_retries(database, "camp", TOMORROW, NOW + timedelta(minutes=9), 200) == []
        [due] = await sms.due_retries(database, "camp", TOMORROW, NOW + sms.RETRY_AFTER, 200)
        assert due["status"] == "failed"
        assert await _send(database, patient, retry_after=sms.RETRY_AFTER, now=NOW + timedelta(minutes=9)) == "skipped"
        assert await _send(database, patient, retry_after=sms.RETRY_AFTER, now=NOW + sms.RETRY_AFTER) == "sent"

    _run(body)


def test_three_attempts_then_abandoned(sms_provider):
    sms_provider.switch_on()
    sms_provider.outcome = "unsent"

    async def body(database):
        patient = await _patient(database)
        outcomes = [await _send(database, patient, now=NOW + timedelta(minutes=i)) for i in range(4)]
        assert outcomes == ["failed", "failed", "failed", "skipped"]
        row = await _row(database)
        assert (row["status"], row["attempts"]) == ("abandoned", 3)

    _run(body)


@pytest.mark.parametrize("gone", ["patient", "token"])
def test_a_failed_intent_is_abandoned_when_its_patient_or_token_is_gone(sms_provider, gone):
    sms_provider.switch_on()
    sms_provider.script("unsent")

    async def body(database):
        patient = await _patient(database)
        await database.deferred_slips.insert_one({
            "patient_id": patient["_id"], "item_type": "ot", "active": gone != "token", "collection_date": TOMORROW,
        })
        if gone == "patient":
            await database.patients.delete_one({"_id": patient["_id"]})
        await _send(database, patient, "ot")
        assert await sms.abandon_if_gone(database, await _row(database)) is True
        assert (await _row(database))["status"] == "abandoned"

    _run(body)


def test_a_failed_intent_whose_token_is_live_is_kept(sms_provider):
    sms_provider.switch_on()
    sms_provider.script("unsent")

    async def body(database):
        patient = await _patient(database)
        await database.deferred_slips.insert_one({
            "patient_id": patient["_id"], "item_type": "ot", "active": True, "collection_date": TOMORROW,
        })
        await _send(database, patient, "ot")
        assert await sms.abandon_if_gone(database, await _row(database)) is False
        assert (await _row(database))["status"] == "failed"

    _run(body)


@pytest.mark.parametrize("outcome,pauses", [("dlt_failure", True), ("dnd", False), ("failed", False)])
def test_only_a_dlt_failure_pauses_its_type(sms_provider, outcome, pauses):
    sms_provider.switch_on()

    async def body(database):
        patient = await _patient(database)
        await _send(database, patient)
        later = NOW + timedelta(minutes=1)
        assert await sms.record_delivery_report(database, sms_provider.report("id-1", outcome), later)
        assert await sms.paused(database, "camp") is pauses
        assert not await sms.paused(database, "ot")
        row = await _row(database)
        assert (row["delivery"], as_utc(row["reported_at"])) == ("failed", later)

    _run(body)


def test_resume_lets_a_rejected_intent_from_before_the_pause_retry_once(sms_provider):
    sms_provider.switch_on()
    sms_provider.outcome = "rejected"

    async def body(database):
        patient = await _patient(database)
        assert await _send(database, patient) == "rejected"
        assert await _send(database, patient, now=NOW + timedelta(minutes=1)) == "skipped"
        await sms.resume(database, "camp", "admin", NOW + timedelta(minutes=2))
        assert await _send(database, patient, now=NOW + timedelta(minutes=3)) == "rejected"
        assert await _send(database, patient, now=NOW + timedelta(minutes=4)) == "skipped"
        assert (await _row(database))["resumed_retry"] is True

    _run(body)


def test_the_canary_sends_one_then_waits_for_its_delivery_report(sms_provider):
    sms_provider.switch_on()

    async def body(database):
        patient = await _patient(database)
        assert await sms.canary(database, "camp", TOMORROW, NOW) == "canary"
        await _send(database, patient, fresh=True)
        assert await sms.canary(database, "camp", TOMORROW, NOW + timedelta(minutes=9)) == "waiting"
        assert await sms.canary(database, "camp", TOMORROW, NOW + sms.CANARY_WAIT) == "open"
        await sms.record_delivery_report(database, sms_provider.report("id-1"), NOW + timedelta(minutes=1))
        assert await sms.canary(database, "camp", TOMORROW, NOW + timedelta(minutes=1)) == "open"
        await database.sms_controls.insert_one({"_id": "camp", "paused": True})
        assert await sms.canary(database, "camp", TOMORROW, NOW) == "paused"

    _run(body)


def test_a_rejected_canary_pauses_its_type(sms_provider):
    sms_provider.switch_on()
    sms_provider.script("rejected")

    async def body(database):
        patient = await _patient(database)
        await _send(database, patient, fresh=True)
        await sms.pause_after_rejection(database, "camp", TOMORROW, NOW)
        control = await database.sms_controls.find_one({"_id": "camp"})
        assert control["paused"] is True
        assert as_utc(control["paused_at"]) == NOW

    _run(body)


def test_a_household_gets_at_most_six_registration_messages_a_day(sms_provider):
    sms_provider.switch_on()

    async def body(database):
        camp_id, _ = await seed_camp(database, venue="Hall A")
        patients = [patient_doc(camp_id=camp_id, phone=HOUSEHOLD, phone_normalized=HOUSEHOLD) for _ in range(7)]
        await database.patients.insert_many(patients)
        outcomes = [await _send(database, patient, "registration") for patient in patients]
        assert outcomes == ["sent"] * sms.REGISTRATION_DAILY_CAP + ["skipped"]
        capped = await database.reminder_ledger.find_one({"status": "skipped"})
        assert capped["reason"] == "daily_cap"

    _run(body)


def test_a_paused_type_records_the_intent_as_paused(sms_provider):
    sms_provider.switch_on()

    async def body(database):
        patient = await _patient(database)
        await database.sms_controls.insert_one({"_id": "camp", "paused": True})
        assert await _send(database, patient) == "paused"
        assert (await _row(database))["status"] == "paused"
        assert sms_provider.sent == []

    _run(body)


def test_a_schedule_edit_notice_is_not_sent_when_missing_failed_or_stuck(sms_provider):
    sms_provider.switch_on()

    async def body(database):
        patient = await _patient(database)
        missing = ObjectId()
        await _recorded(database, patient, "ot_change", sms.edit_key("rev-1"))
        notices = [(patient["_id"], "rev-1"), (missing, "rev-1")]
        assert await sms.notice_states(database, notices, NOW) == {
            (patient["_id"], "rev-1"): "queued", (missing, "rev-1"): "not_sent",
        }
        stuck = await sms.notice_states(database, notices, NOW + sms.RETRY_AFTER)
        assert stuck[(patient["_id"], "rev-1")] == "not_sent"

    _run(body)
