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
from seed import ADMIN, TODAY, TOMORROW, day, patient_doc, recorder, seed_camp, user_doc
from test_reminders import HOUSEHOLD, _age_ledger, _ledger, _post, _run, _seed_camp_household

SECRET = "report-secret"


def _reporting(monkeypatch, body, **kwargs):
    monkeypatch.setenv("MSG91_WEBHOOK_SECRET", SECRET)
    return _run(monkeypatch, body, **kwargs)


async def _report(client, request_id, status="1", reason="", tel=f"91{HOUSEHOLD}", secret=SECRET, credit="0.75"):
    return await client.post(
        "/api/webhooks/msg91",
        headers={"X-SNP-Webhook-Secret": secret},
        json={"requestId": request_id, "status": status, "failureReason": reason, "telNum": tel, "credit": credit},
    )


async def _registration_patient(database):
    _camp_id, _day, [pid] = await _seed_camp_household(database, n_patients=1)
    return await database.patients.find_one({"_id": pid})


class TestDeliveryReports:
    def test_reports_need_the_configured_secret(self, monkeypatch):
        async def body(database, client):
            assert (await _report(client, "rq", secret="wrong")).status_code == 401
            assert (await _report(client, "rq", secret="")).status_code == 401
            monkeypatch.delenv("MSG91_WEBHOOK_SECRET")
            assert (await _report(client, "rq", secret="")).status_code == 401

        _reporting(monkeypatch, body)

    def test_a_delivered_report_records_delivery_and_credit(self, monkeypatch):
        recorder(monkeypatch)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=1)
            await _post(client)

            response = await _report(client, "id-1")

            assert response.json() == {"ok": True, "recorded": 1}
            [row] = await _ledger(database)
            assert (row["delivery"], row["dlt_failure"], row["credit"]) == ("delivered", False, 0.75)
            assert await database.sms_controls.find().to_list(None) == []

        _reporting(monkeypatch, body)

    @pytest.mark.parametrize("report", [
        {"request_id": "unknown"},
        {"status": "0"},
        {"tel": "919000000000"},
    ])
    def test_unknown_pending_or_mismatched_reports_change_nothing(self, monkeypatch, report):
        recorder(monkeypatch)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=1)
            await _post(client)

            response = await _report(
                client, report.get("request_id", "id-1"), status=report.get("status", "2"),
                reason="DLT Template variable exceeded max length", tel=report.get("tel", f"91{HOUSEHOLD}"),
            )

            assert response.json() == {"ok": True, "recorded": 0}
            [row] = await _ledger(database)
            assert "delivery" not in row
            assert await database.sms_controls.find().to_list(None) == []

        _reporting(monkeypatch, body)

    @pytest.mark.parametrize("reason", [
        "Absent Subscriber",
        "DND: Failed due to Preference Category on DLT",
    ])
    def test_a_number_level_failure_does_not_pause_sending(self, monkeypatch, reason):
        recorder(monkeypatch)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=1)
            await _post(client)

            await _report(client, "id-1", status="2", reason=reason)

            [row] = await _ledger(database)
            assert (row["delivery"], row["dlt_failure"]) == ("failed", False)
            assert not await sms.paused(database, "camp")

        _reporting(monkeypatch, body)

    @pytest.mark.parametrize("status,reason", [
        ("2", "DLT Template variable exceeded max length"),
        ("2", "Template content mismatch"),
        ("16", ""),
    ])
    def test_a_dlt_failure_pauses_only_that_message_type(self, monkeypatch, status, reason):
        recorder(monkeypatch)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=1)
            await _post(client)

            await _report(client, "id-1", status=status, reason=reason)

            [row] = await _ledger(database)
            assert row["dlt_failure"] is True
            assert await sms.paused(database, "camp")
            assert not await sms.paused(database, "registration")
            [control] = await database.sms_controls.find().to_list(None)
            assert control["paused_request_id"] == "id-1"
            assert control["paused_reason"] == (reason or "Operator status 16")

        _reporting(monkeypatch, body)


class TestSmsPause:
    def test_a_paused_type_holds_back_event_sends_and_does_not_send_them_later(self, monkeypatch):
        captured = recorder(monkeypatch)

        async def body(database, client):
            patient = await _registration_patient(database)
            await database.sms_controls.insert_one({"_id": "registration", "paused": True})

            assert not await sms.send_patient_sms(database, patient, "registration", TOMORROW, "Hall A")
            assert captured == []
            [row] = await _ledger(database)
            assert row["status"] == "paused"

            await sms.resume(database, "registration", "admin")
            assert await sms.deliver_patient_sms(database, patient, "ot_token", TOMORROW, "Hall A") == "sent"
            assert [c["type"] for c in captured] == ["ot_token"]

        _run(monkeypatch, body)

    def test_a_paused_reminder_batch_waits_and_goes_out_after_resume(self, monkeypatch):
        captured = recorder(monkeypatch)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=2)
            await database.sms_controls.insert_one({"_id": "camp", "paused": True})

            held = (await _post(client)).json()
            await sms.resume(database, "camp", "admin")
            released = (await _post(client)).json()

            assert (held["sent"], held["complete"], held["waiting"], held["ok"]) == (0, False, True, True)
            assert (released["sent"], released["complete"]) == (2, True)
            assert len(captured) == 2

        _run(monkeypatch, body)

    def test_a_pause_during_an_open_batch_holds_the_rest_until_resume(self, monkeypatch):
        recorder(monkeypatch)
        captured = []

        async def body(database, client):
            await _seed_camp_household(database, n_patients=3)
            loop = asyncio.get_running_loop()

            def send_then_pause(message_type, mobile, variables):
                captured.append(variables["reg_no"])
                asyncio.run_coroutine_threadsafe(database.sms_controls.replace_one(
                    {"_id": "camp"}, {"paused": True}, upsert=True,
                ), loop).result(5)
                return f"id-{len(captured)}"

            monkeypatch.setattr(sms.msg91, "send_dlt_sms", send_then_pause)

            held = (await _post(client)).json()
            await sms.resume(database, "camp", "admin")
            monkeypatch.setattr(sms.msg91, "send_dlt_sms", lambda *args: captured.append(args[2]["reg_no"]) or "id-x")
            released = (await _post(client)).json()

            assert (held["sent"], held["complete"], held["waiting"]) == (1, False, True)
            assert (released["complete"], released["waiting"]) == (True, False)
            assert sorted(captured) == [1000, 1001, 1002]

        _run(monkeypatch, body)

    def test_a_report_for_a_message_sent_before_resume_does_not_pause_again(self, monkeypatch):
        recorder(monkeypatch)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=1)
            await _post(client)
            await _age_ledger(database, timedelta(minutes=5))
            await _report(client, "id-1", status="2", reason="DLT failure")
            await sms.resume(database, "camp", "admin")

            await _report(client, "id-1", status="2", reason="DLT failure")

            assert not await sms.paused(database, "camp")

        _reporting(monkeypatch, body)


class TestCanary:
    def test_one_reminder_goes_first_and_the_rest_wait_for_its_report(self, monkeypatch):
        captured = recorder(monkeypatch)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=3)

            first = (await _post(client)).json()
            second = (await _post(client)).json()
            await _report(client, "id-1")
            third = (await _post(client)).json()

            assert (first["sent"], first["complete"], first["waiting"]) == (1, False, True)
            assert (second["sent"], second["waiting"]) == (0, True)
            assert (third["sent"], third["complete"], third["waiting"]) == (2, True, False)
            assert len(captured) == 3

        _reporting(monkeypatch, body, canary=True)

    def test_a_canary_without_a_report_releases_the_batch_after_ten_minutes(self, monkeypatch):
        recorder(monkeypatch)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=3)
            await _post(client)
            await _age_ledger(database, routes_reminders.CANARY_WAIT)

            assert (await _post(client)).json()["sent"] == 2

        _run(monkeypatch, body, canary=True)

    def test_a_dlt_failed_canary_costs_one_message_and_resume_sends_a_new_canary(self, monkeypatch):
        captured = recorder(monkeypatch)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=4)
            await _post(client)
            await _report(client, "id-1", status="2", reason="DLT Template variable exceeded max length")

            paused = (await _post(client)).json()
            await _age_ledger(database, timedelta(minutes=1))
            await sms.resume(database, "camp", "admin")
            canary = (await _post(client)).json()

            assert (paused["sent"], paused["waiting"]) == (0, True)
            assert (canary["sent"], canary["waiting"]) == (1, True)
            assert len(captured) == 2

        _reporting(monkeypatch, body, canary=True)

    def test_a_waiting_camp_canary_does_not_hold_up_surgery_reminders(self, monkeypatch):
        captured = recorder(monkeypatch)

        async def body(database, client):
            _camp, _day, ids = await _seed_camp_household(database, n_patients=2)
            await database.deferred_slips.insert_one({
                "patient_id": ids[0], "item_type": "ot", "active": True, "cancelled": False,
                "collection_date": TOMORROW, "collection_venue": "OT Theatre", "version": 1,
            })

            await _post(client)

            assert [c["type"] for c in captured] == ["ot", "camp"]

        _run(monkeypatch, body, canary=True)


class TestSmsStatus:
    def test_admin_sees_each_type_and_todays_totals(self, monkeypatch):
        recorder(monkeypatch)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=2)
            monkeypatch.delenv("MSG91_TEMPLATE_SPECS")
            await _post(client)
            await _report(client, "id-1", credit="0.5")
            await _report(client, "id-2", status="2", reason="DLT Template variable exceeded max length", credit="0.5")

            status = await routes_sms.sms_status(actor=ADMIN)

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

            resumed = await routes_sms.resume_sms("camp", actor=ADMIN)
            assert {t["message_type"]: t["paused"] for t in resumed["types"]}["camp"] is False
            with pytest.raises(HTTPException) as error:
                await routes_sms.resume_sms("nonsense", actor=ADMIN)
            assert error.value.status_code == 404

        _reporting(monkeypatch, body)


class TestSpecsSmsVenue:
    def test_a_specs_day_takes_a_short_sms_venue_under_the_same_rule(self):
        base = {"camp_id": str(ObjectId()), "day_date": TODAY, "end_date": day(32)}
        assert SpecsScheduleBody(**base, venue="Sikar Bhawan").venue_sms is None
        assert SpecsScheduleBody(**base, venue="A" * 60, venue_sms=" SNP  Office ").venue_sms == "SNP Office"
        for venue, venue_sms in (("NA", None), ("A" * 60, None), ("Hall", "call 9876543210")):
            with pytest.raises(ValidationError):
                SpecsScheduleBody(**base, venue=venue, venue_sms=venue_sms)
        with pytest.raises(ValidationError):
            OtScheduleBody(camp_id=base["camp_id"], day_date=TODAY, venue="Hospital", venue_sms="https://x.in", seat_limit=5)

    def test_the_specs_day_sms_venue_reaches_the_slip_and_the_reminder(self, monkeypatch):
        captured = recorder(monkeypatch)

        async def body(database, client):
            camp_id, _ = await seed_camp(database, days=(), name="C", venue="Hall A")
            pid = ObjectId()
            await database.patients.insert_one(patient_doc(
                _id=pid, camp_id=camp_id, camp_day_id=ObjectId(), reg_no=42,
                phone=HOUSEHOLD, phone_normalized=HOUSEHOLD,
            ))
            specs = await routes_clinical.create_specs_day(SpecsScheduleBody(
                camp_id=str(camp_id), day_date=(helpers.now_ist() + timedelta(days=1)).date().isoformat(),
                venue="Sikar Zilla Welfare Trust office, main market road, Deoghar", venue_sms="SZWT Office, Deoghar",
            ), actor=ADMIN)
            await database.deferred_slips.insert_one({
                "patient_id": pid, "item_type": "specs_made", "active": True, "cancelled": False,
                "collection_date": TOMORROW, "collection_venue": specs["specs_day"]["venue"],
                "collection_venue_sms": specs["specs_day"]["venue_sms"],
                "collection_start_time": "10:00", "collection_end_time": "17:00", "version": 1,
            })

            await _post(client)

            assert specs["specs_day"]["venue_sms"] == "SZWT Office, Deoghar"
            assert [(c["type"], c["venue"]) for c in captured] == [("specs", "SZWT Office, Deoghar")]

        _run(monkeypatch, body)


class TestSendTimeGuard:
    def test_schedule_edits_on_the_same_date_each_send_once(self, monkeypatch):
        captured = recorder(monkeypatch)

        async def body(database, client):
            patient = await _registration_patient(database)

            outcomes = [await sms.deliver_patient_sms(
                database, patient, "registration", TOMORROW, "Hansa Garden, Jasidih, Deoghar",
                event_key=revision,
            ) for revision in ("day-edit-1", "day-edit-2", "day-edit-2")]

            assert outcomes == ["sent", "sent", "skipped"]
            assert len(captured) == 2
            rows = await _ledger(database)
            assert [row["event_date"] for row in rows] == [TOMORROW, TOMORROW]
            assert [row["event_key"] for row in rows] == ["day-edit-1", "day-edit-2"]

        _run(monkeypatch, body)

    @pytest.mark.parametrize("message_type", ["registration", "camp", "ot_token"])
    def test_registrar_phone_never_receives_patient_sms(self, monkeypatch, message_type):
        captured = recorder(monkeypatch)

        async def body(database, client):
            patient = await _registration_patient(database)
            registrar_id = ObjectId()
            patient["created_by"] = str(registrar_id)
            await database.users.insert_one(user_doc("Registrar", _id=registrar_id, phone="+91 98765 00001"))

            outcome = await sms.deliver_patient_sms(
                database, patient, message_type, TOMORROW, "Hansa Garden, Jasidih, Deoghar",
            )

            assert outcome == "skipped"
            assert captured == []
            assert await _ledger(database) == []

        _run(monkeypatch, body)

    def test_a_venue_is_sent_with_its_spacing_tidied(self, monkeypatch):
        captured = recorder(monkeypatch)

        async def body(database, client):
            patient = await _registration_patient(database)

            outcome = await sms.deliver_patient_sms(
                database, patient, "registration", TOMORROW, "  Hansa Garden,  Jasidih, Deoghar ",
            )

            assert outcome == "sent"
            assert captured[0]["venue"] == "Hansa Garden, Jasidih, Deoghar"
            [row] = await _ledger(database)
            assert row["venue"] == "Hansa Garden, Jasidih, Deoghar"

        _run(monkeypatch, body)

    @pytest.mark.parametrize("venue", ["NA", "Hall 9876543210", "www.hall.in", "A" * 31])
    def test_a_venue_breaking_the_rule_is_never_submitted(self, monkeypatch, venue):
        captured = recorder(monkeypatch)

        async def body(database, client):
            patient = await _registration_patient(database)

            assert await sms.deliver_patient_sms(database, patient, "registration", TOMORROW, venue) == "skipped"
            assert captured == []
            assert await _ledger(database) == []

        _run(monkeypatch, body)
