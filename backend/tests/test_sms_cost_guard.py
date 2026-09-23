import asyncio
from datetime import timedelta

import pytest
from bson import ObjectId
from fastapi import HTTPException
from pydantic import ValidationError

import helpers
import routes_clinical
import routes_reminders
import routes_sms
import sms
from models import OtScheduleBody, SpecsScheduleBody
from test_adversarial_challenger import setup_mock_db
from test_reminders import HOUSEHOLD, TOMORROW, _calls, _client, _post, _seed_camp_household

SECRET = "report-secret"
ADMIN = {"_id": ObjectId(), "role": "admin"}


def _reporting(monkeypatch, mock_db, **kwargs):
    monkeypatch.setattr(routes_sms, "get_db", lambda: mock_db)
    monkeypatch.setenv("MSG91_WEBHOOK_SECRET", SECRET)
    return _client(monkeypatch, mock_db, **kwargs)


def _report(client, request_id, status="1", reason="", tel=f"91{HOUSEHOLD}", secret=SECRET, credit="0.75"):
    return client.post(
        "/api/webhooks/msg91",
        headers={"X-SNP-Webhook-Secret": secret},
        json={"requestId": request_id, "status": status, "failureReason": reason, "telNum": tel, "credit": credit},
    )


def _registration_patient(mock_db):
    async def seed():
        camp_id, _day, [pid] = await _seed_camp_household(mock_db, n_patients=1)
        return await mock_db.patients.find_one({"_id": pid})
    return asyncio.run(seed())


class TestDeliveryReports:
    def test_reports_need_the_configured_secret(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        client = _reporting(monkeypatch, mock_db)
        assert _report(client, "rq", secret="wrong").status_code == 401
        assert _report(client, "rq", secret="").status_code == 401
        monkeypatch.delenv("MSG91_WEBHOOK_SECRET")
        assert _report(client, "rq", secret="").status_code == 401

    def test_a_delivered_report_records_delivery_and_credit(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        asyncio.run(_seed_camp_household(mock_db, n_patients=1))
        _calls(monkeypatch)
        client = _reporting(monkeypatch, mock_db)
        _post(client)

        response = _report(client, "id-1")

        assert response.json() == {"ok": True, "recorded": 1}
        row = mock_db.reminder_ledger.docs[0]
        assert (row["delivery"], row["dlt_failure"], row["credit"]) == ("delivered", False, 0.75)
        assert mock_db.sms_controls.docs == []

    @pytest.mark.parametrize("report", [
        {"request_id": "unknown"},
        {"status": "0"},
        {"tel": "919000000000"},
    ])
    def test_unknown_pending_or_mismatched_reports_change_nothing(self, monkeypatch, report):
        mock_db = setup_mock_db(monkeypatch)
        asyncio.run(_seed_camp_household(mock_db, n_patients=1))
        _calls(monkeypatch)
        client = _reporting(monkeypatch, mock_db)
        _post(client)

        response = _report(client, report.get("request_id", "id-1"), status=report.get("status", "2"),
                           reason="DLT Template variable exceeded max length", tel=report.get("tel", f"91{HOUSEHOLD}"))

        assert response.json() == {"ok": True, "recorded": 0}
        assert "delivery" not in mock_db.reminder_ledger.docs[0]
        assert mock_db.sms_controls.docs == []

    def test_a_switched_off_phone_does_not_pause_sending(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        asyncio.run(_seed_camp_household(mock_db, n_patients=1))
        _calls(monkeypatch)
        client = _reporting(monkeypatch, mock_db)
        _post(client)

        _report(client, "id-1", status="2", reason="Absent Subscriber")

        row = mock_db.reminder_ledger.docs[0]
        assert (row["delivery"], row["dlt_failure"]) == ("failed", False)
        assert not asyncio.run(sms.paused(mock_db, "camp"))

    @pytest.mark.parametrize("status,reason", [
        ("2", "DLT Template variable exceeded max length"),
        ("2", "Template content mismatch"),
        ("16", ""),
    ])
    def test_a_dlt_failure_pauses_only_that_message_type(self, monkeypatch, status, reason):
        mock_db = setup_mock_db(monkeypatch)
        asyncio.run(_seed_camp_household(mock_db, n_patients=1))
        _calls(monkeypatch)
        client = _reporting(monkeypatch, mock_db)
        _post(client)

        _report(client, "id-1", status=status, reason=reason)

        assert mock_db.reminder_ledger.docs[0]["dlt_failure"] is True
        assert asyncio.run(sms.paused(mock_db, "camp"))
        assert not asyncio.run(sms.paused(mock_db, "registration"))
        control = mock_db.sms_controls.docs[0]
        assert control["paused_request_id"] == "id-1"
        assert control["paused_reason"] == (reason or "Operator status 16")


class TestSmsPause:
    def test_a_paused_type_holds_back_event_sends_and_does_not_send_them_later(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        patient = _registration_patient(mock_db)
        captured = _calls(monkeypatch)
        _client(monkeypatch, mock_db)
        asyncio.run(mock_db.sms_controls.insert_one({"_id": "registration", "paused": True}))

        assert not asyncio.run(sms.send_patient_sms(mock_db, patient, "registration", TOMORROW, "Hall A"))
        assert captured == []
        assert mock_db.reminder_ledger.docs[0]["status"] == "paused"

        asyncio.run(sms.resume(mock_db, "registration", "admin"))
        assert asyncio.run(sms.deliver_patient_sms(mock_db, patient, "ot_token", TOMORROW, "Hall A")) == "sent"
        assert [c["type"] for c in captured] == ["ot_token"]

    def test_a_paused_reminder_batch_waits_and_goes_out_after_resume(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        asyncio.run(_seed_camp_household(mock_db, n_patients=2))
        captured = _calls(monkeypatch)
        client = _client(monkeypatch, mock_db)
        asyncio.run(mock_db.sms_controls.insert_one({"_id": "camp", "paused": True}))

        held = _post(client).json()
        asyncio.run(sms.resume(mock_db, "camp", "admin"))
        released = _post(client).json()

        assert (held["sent"], held["complete"], held["waiting"], held["ok"]) == (0, False, True, True)
        assert (released["sent"], released["complete"]) == (2, True)
        assert len(captured) == 2

    def test_a_pause_during_an_open_batch_holds_the_rest_until_resume(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        asyncio.run(_seed_camp_household(mock_db, n_patients=3))
        captured = []

        def send_then_pause(message_type, mobile, variables):
            captured.append(variables["reg_no"])
            mock_db.sms_controls.docs[:] = [{"_id": "camp", "paused": True}]
            return f"id-{len(captured)}"

        _calls(monkeypatch)
        monkeypatch.setattr(sms.msg91, "send_dlt_sms", send_then_pause)
        client = _client(monkeypatch, mock_db)

        held = _post(client).json()
        asyncio.run(sms.resume(mock_db, "camp", "admin"))
        monkeypatch.setattr(sms.msg91, "send_dlt_sms", lambda *args: captured.append(args[2]["reg_no"]) or "id-x")
        released = _post(client).json()

        assert (held["sent"], held["complete"], held["waiting"]) == (1, False, True)
        assert (released["complete"], released["waiting"]) == (True, False)
        assert sorted(captured) == [1000, 1001, 1002]

    def test_a_report_for_a_message_sent_before_resume_does_not_pause_again(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        asyncio.run(_seed_camp_household(mock_db, n_patients=1))
        _calls(monkeypatch)
        client = _reporting(monkeypatch, mock_db)
        _post(client)
        mock_db.reminder_ledger.docs[0]["created_at"] -= timedelta(minutes=5)
        _report(client, "id-1", status="2", reason="DLT failure")
        asyncio.run(sms.resume(mock_db, "camp", "admin"))

        _report(client, "id-1", status="2", reason="DLT failure")

        assert not asyncio.run(sms.paused(mock_db, "camp"))


class TestCanary:
    def test_one_reminder_goes_first_and_the_rest_wait_for_its_report(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        asyncio.run(_seed_camp_household(mock_db, n_patients=3))
        captured = _calls(monkeypatch)
        client = _reporting(monkeypatch, mock_db, canary=True)

        first = _post(client).json()
        second = _post(client).json()
        _report(client, "id-1")
        third = _post(client).json()

        assert (first["sent"], first["complete"], first["waiting"]) == (1, False, True)
        assert (second["sent"], second["waiting"]) == (0, True)
        assert (third["sent"], third["complete"], third["waiting"]) == (2, True, False)
        assert len(captured) == 3

    def test_a_canary_without_a_report_releases_the_batch_after_ten_minutes(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        asyncio.run(_seed_camp_household(mock_db, n_patients=3))
        _calls(monkeypatch)
        client = _client(monkeypatch, mock_db, canary=True)
        _post(client)
        mock_db.reminder_ledger.docs[0]["created_at"] -= routes_reminders.CANARY_WAIT

        assert _post(client).json()["sent"] == 2

    def test_a_dlt_failed_canary_costs_one_message_and_resume_sends_a_new_canary(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        asyncio.run(_seed_camp_household(mock_db, n_patients=4))
        captured = _calls(monkeypatch)
        client = _reporting(monkeypatch, mock_db, canary=True)
        _post(client)
        _report(client, "id-1", status="2", reason="DLT Template variable exceeded max length")

        paused = _post(client).json()
        asyncio.run(sms.resume(mock_db, "camp", "admin"))
        canary = _post(client).json()

        assert (paused["sent"], paused["waiting"]) == (0, True)
        assert (canary["sent"], canary["waiting"]) == (1, True)
        assert len(captured) == 2

    def test_a_waiting_camp_canary_does_not_hold_up_surgery_reminders(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)

        async def seed():
            _camp, _day, ids = await _seed_camp_household(mock_db, n_patients=2)
            await mock_db.deferred_slips.insert_one({
                "patient_id": ids[0], "item_type": "ot", "active": True, "cancelled": False,
                "collection_date": TOMORROW, "collection_venue": "OT Theatre", "version": 1,
            })

        asyncio.run(seed())
        captured = _calls(monkeypatch)
        client = _client(monkeypatch, mock_db, canary=True)

        _post(client)

        assert [c["type"] for c in captured] == ["camp", "ot"]


class TestSmsStatus:
    def test_admin_sees_each_type_and_todays_totals(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        asyncio.run(_seed_camp_household(mock_db, n_patients=2))
        _calls(monkeypatch)
        client = _reporting(monkeypatch, mock_db)
        monkeypatch.setattr(routes_sms, "today_ist_str", lambda: helpers.now_ist().date().isoformat())
        monkeypatch.delenv("MSG91_TEMPLATE_SPECS")
        _post(client)
        _report(client, "id-1", credit="0.5")
        _report(client, "id-2", status="2", reason="DLT Template variable exceeded max length", credit="0.5")

        status = asyncio.run(routes_sms.sms_status(actor=ADMIN))

        types = {t["message_type"]: t for t in status["types"]}
        assert list(types) == list(sms.MESSAGE_COPY)
        assert types["specs"]["configured"] is False
        assert types["camp"]["paused"] is True
        assert "exceeded" in types["camp"]["paused_reason"]
        assert status["today"] == {
            "submitted": 2, "delivered": 1, "dlt_failed": 1, "other_failed": 0, "uncertain": 0,
            "rejected": 0, "unsent": 0, "paused": 0, "credits": 1.0,
        }
        assert status["reports_enabled"] is True

        resumed = asyncio.run(routes_sms.resume_sms("camp", actor=ADMIN))
        assert {t["message_type"]: t["paused"] for t in resumed["types"]}["camp"] is False
        with pytest.raises(HTTPException) as error:
            asyncio.run(routes_sms.resume_sms("nonsense", actor=ADMIN))
        assert error.value.status_code == 404


class TestSpecsSmsVenue:
    def test_a_specs_day_takes_a_short_sms_venue_under_the_same_rule(self):
        base = {"camp_id": str(ObjectId()), "day_date": "2026-10-05", "end_date": "2026-11-06"}
        assert SpecsScheduleBody(**base, venue="Sikar Bhawan").venue_sms is None
        assert SpecsScheduleBody(**base, venue="A" * 60, venue_sms=" SNP  Office ").venue_sms == "SNP Office"
        for venue, venue_sms in (("NA", None), ("A" * 60, None), ("Hall", "call 9876543210")):
            with pytest.raises(ValidationError):
                SpecsScheduleBody(**base, venue=venue, venue_sms=venue_sms)
        with pytest.raises(ValidationError):
            OtScheduleBody(camp_id=base["camp_id"], day_date="2026-10-05", venue="Hospital", venue_sms="https://x.in", seat_limit=5)

    def test_the_specs_day_sms_venue_reaches_the_slip_and_the_reminder(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)

        async def seed():
            camp_id = ObjectId()
            pid = ObjectId()
            await mock_db.camps.insert_one({"_id": camp_id, "name": "C", "venue": "Hall A", "camp_number": 162, "is_active": True})
            await mock_db.patients.insert_one({
                "_id": pid, "camp_id": camp_id, "camp_day_id": ObjectId(), "reg_no": 42,
                "phone": HOUSEHOLD, "phone_normalized": HOUSEHOLD,
            })
            day = await routes_clinical.create_specs_day(SpecsScheduleBody(
                camp_id=str(camp_id), day_date=(helpers.now_ist() + timedelta(days=1)).date().isoformat(),
                venue="Sikar Zilla Welfare Trust office, main market road, Deoghar", venue_sms="SZWT Office, Deoghar",
            ), actor=ADMIN)
            await mock_db.deferred_slips.insert_one({
                "patient_id": pid, "item_type": "specs_made", "active": True, "cancelled": False,
                "collection_date": TOMORROW, "collection_venue": day["specs_day"]["venue"],
                "collection_venue_sms": day["specs_day"]["venue_sms"],
                "collection_start_time": "10:00", "collection_end_time": "17:00", "version": 1,
            })
            return day

        day = asyncio.run(seed())
        captured = _calls(monkeypatch)

        _post(_client(monkeypatch, mock_db))

        assert day["specs_day"]["venue_sms"] == "SZWT Office, Deoghar"
        assert [(c["type"], c["venue"]) for c in captured] == [("specs", "SZWT Office, Deoghar")]


class TestSendTimeGuard:
    def test_schedule_edits_on_the_same_date_each_send_once(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        patient = _registration_patient(mock_db)
        captured = _calls(monkeypatch)
        _client(monkeypatch, mock_db)

        outcomes = [asyncio.run(sms.deliver_patient_sms(
            mock_db, patient, "registration", TOMORROW, "Hansa Garden, Jasidih, Deoghar",
            event_key=revision,
        )) for revision in ("day-edit-1", "day-edit-2", "day-edit-2")]

        assert outcomes == ["sent", "sent", "skipped"]
        assert len(captured) == 2
        assert [row["event_date"] for row in mock_db.reminder_ledger.docs] == [TOMORROW, TOMORROW]
        assert [row["event_key"] for row in mock_db.reminder_ledger.docs] == ["day-edit-1", "day-edit-2"]

    @pytest.mark.parametrize("message_type", ["registration", "camp", "ot_token"])
    def test_registrar_phone_never_receives_patient_sms(self, monkeypatch, message_type):
        mock_db = setup_mock_db(monkeypatch)
        patient = _registration_patient(mock_db)
        registrar_id = ObjectId()
        patient["created_by"] = str(registrar_id)
        asyncio.run(mock_db.users.insert_one({
            "_id": registrar_id, "role": "volunteer", "phone": "+91 98765 00001",
        }))
        captured = _calls(monkeypatch)
        _client(monkeypatch, mock_db)

        outcome = asyncio.run(sms.deliver_patient_sms(
            mock_db, patient, message_type, TOMORROW, "Hansa Garden, Jasidih, Deoghar",
        ))

        assert outcome == "skipped"
        assert captured == []
        assert mock_db.reminder_ledger.docs == []

    def test_a_venue_is_sent_with_its_spacing_tidied(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        patient = _registration_patient(mock_db)
        captured = _calls(monkeypatch)
        _client(monkeypatch, mock_db)

        outcome = asyncio.run(sms.deliver_patient_sms(
            mock_db, patient, "registration", TOMORROW, "  Hansa Garden,  Jasidih, Deoghar ",
        ))

        assert outcome == "sent"
        assert captured[0]["venue"] == "Hansa Garden, Jasidih, Deoghar"
        assert mock_db.reminder_ledger.docs[0]["venue"] == "Hansa Garden, Jasidih, Deoghar"

    @pytest.mark.parametrize("venue", ["NA", "Hall 9876543210", "www.hall.in", "A" * 31])
    def test_a_venue_breaking_the_rule_is_never_submitted(self, monkeypatch, venue):
        mock_db = setup_mock_db(monkeypatch)
        patient = _registration_patient(mock_db)
        captured = _calls(monkeypatch)
        _client(monkeypatch, mock_db)

        assert asyncio.run(sms.deliver_patient_sms(mock_db, patient, "registration", TOMORROW, venue)) == "skipped"
        assert captured == []
        assert mock_db.reminder_ledger.docs == []
