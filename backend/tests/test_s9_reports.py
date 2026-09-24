"""S9: backlog, ledger aggregates, KPI shape, and a bounded camp export."""
from datetime import timedelta

from bson import ObjectId

import sms
from conftest import CommandLog
from db import in_transaction
from routes_reports import camp_day_board, export_camp_records, kpis
from routes_sms import sms_status
from seed import ADMIN, NOW, TODAY, patient_doc, run_camp, seed_camp


def test_kpis_without_a_camp_use_the_same_keys(monkeypatch):
    async def body(database):
        assert await kpis(actor=ADMIN) == {
            "active_camp": None, "registered": 0, "seen": 0, "pending": 0,
        }
        assert "pre_registered" not in await kpis(actor=ADMIN)

    run_camp(monkeypatch, body)


def test_backlog_is_printed_arrivals_without_a_completed_prescription(monkeypatch):
    async def body(database):
        camp_id, _ = await seed_camp(database)
        await database.patients.insert_many([
            patient_doc(camp_id=camp_id, arrived_at=NOW),
            patient_doc(camp_id=camp_id, arrived_at=NOW, printed_at=NOW),
            patient_doc(camp_id=camp_id, arrived_at=NOW, printed_at=NOW, seen_at=NOW),
            patient_doc(
                camp_id=camp_id, arrived_at=NOW, printed_at=NOW, committed_revision_id=ObjectId(),
            ),
            patient_doc(
                camp_id=camp_id, arrived_at=NOW - timedelta(days=1), printed_at=NOW - timedelta(days=1),
            ),
        ])
        stages = (await camp_day_board(actor=ADMIN))["stages"]
        assert stages["transcription_backlog"] == 2
        assert stages["arrived"] == 4

    run_camp(monkeypatch, body)


def test_sms_counts_group_in_the_database(monkeypatch):
    log = CommandLog()

    async def body(database):
        camp_id, _ = await seed_camp(database)
        other = ObjectId()
        await database.reminder_ledger.insert_many([
            {
                "camp_id": camp_id, "event_date": TODAY, "message_type": "camp", "status": "failed",
                "patient_id": ObjectId(), "event_key": "a", "created_at": NOW,
            },
            {
                "camp_id": other, "event_date": TODAY, "message_type": "camp", "status": "failed",
                "patient_id": ObjectId(), "event_key": "b", "created_at": NOW,
            },
            {
                "camp_id": camp_id, "event_date": TODAY, "message_type": "registration", "status": "paused",
                "patient_id": ObjectId(), "event_key": "c", "created_at": NOW,
            },
        ])
        log.commands.clear()
        board = await camp_day_board(actor=ADMIN)
        status = await sms_status(actor=ADMIN)
        assert ("find", "reminder_ledger") not in log.commands
        assert ("aggregate", "reminder_ledger") in log.commands
        assert board["sms_failures"] == 1
        assert board["sms_not_sent"] == 1
        assert status["today"]["unsent"] == 2
        assert status["today"]["paused"] == 1

    run_camp(monkeypatch, body, listener=log)


def test_export_streams_every_patient(monkeypatch):
    async def body(database):
        camp_id, _ = await seed_camp(database)
        count = 450
        await database.patients.insert_many([
            patient_doc(camp_id=camp_id, full_name=f"Patient {i}") for i in range(count)
        ])
        response = await export_camp_records(camp_id=str(camp_id), actor=ADMIN)
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk if isinstance(chunk, str) else chunk.decode())
        assert chunks[0].startswith("reg_no,")
        assert "Patient 449" not in chunks[0]
        text = "".join(chunks)
        assert text.count("\n") == count + 1
        assert "Patient 0" in text and "Patient 449" in text

    run_camp(monkeypatch, body)


def test_new_ledger_rows_store_camp_id(monkeypatch):
    monkeypatch.setattr(sms.msg91, "configured", lambda: True)
    monkeypatch.setattr(sms.msg91, "template_id", lambda _message_type: "flow")

    async def body(database):
        camp_id, _ = await seed_camp(database)
        patient = patient_doc(
            camp_id=camp_id, phone="9876543210", phone_normalized="9876543210", reg_no=501,
        )
        await database.patients.insert_one(patient)

        async def queue(session):
            return await sms.queue_sms(
                database, [patient], "registration", TODAY, "Hall A", event_key="reg", session=session,
            )

        queued = await in_transaction(queue)
        row = await database.reminder_ledger.find_one({"_id": queued[0]})
        assert row["camp_id"] == camp_id
        assert row["status"] == "queued"

    run_camp(monkeypatch, body)
