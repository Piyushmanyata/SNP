import json
import re
import string
from datetime import timedelta
from pathlib import Path

import httpx
from bson import ObjectId

import msg91
import routes_reminders
import server
import sms
from seed import TOMORROW, day, patient_doc, recorder, run_camp, seed_camp
from sms import (
    CAMP_REMINDER,
    OT_REMINDER,
    OT_TOKEN,
    REGISTRATION_CONFIRMATION,
    SPECS_REMINDER,
    SPECS_TOKEN,
)

backend_dir = Path(__file__).resolve().parents[1]
TOMORROW_SHOWN = "06-10-2026"
SECRET = "cron-test-secret"
HOUSEHOLD = "9876500001"

TEMPLATE_ENV = {
    "MSG91_TEMPLATE_REGISTRATION": "tmpl-registration",
    "MSG91_TEMPLATE_CAMP": "tmpl-camp",
    "MSG91_TEMPLATE_OT_TOKEN": "tmpl-ot-token",
    "MSG91_TEMPLATE_OT": "tmpl-ot",
    "MSG91_TEMPLATE_SPECS_TOKEN": "tmpl-specs-token",
    "MSG91_TEMPLATE_SPECS": "tmpl-specs",
}


async def _open_canary(*_args):
    return "open"


def _run(monkeypatch, body, *, msg91_on=True, canary=False):
    if not canary:
        monkeypatch.setattr(routes_reminders, "_canary", _open_canary)
    monkeypatch.setenv("CRON_SECRET", SECRET)
    if msg91_on:
        monkeypatch.setenv("MSG91_AUTH_KEY", "auth")
        for name, value in TEMPLATE_ENV.items():
            monkeypatch.setenv(name, value)
    else:
        monkeypatch.delenv("MSG91_AUTH_KEY", raising=False)
        for name in TEMPLATE_ENV:
            monkeypatch.delenv(name, raising=False)

    async def with_client(database):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            return await body(database, client)

    return run_camp(monkeypatch, with_client)


async def _seed_camp_household(database, n_patients=4, phone=HOUSEHOLD, venue="Hall A", camp_number=162):
    camp_id, (day_id,) = await seed_camp(
        database, days=(TOMORROW,), name="Nadia Camp", venue=venue, camp_number=camp_number,
    )
    ids = [ObjectId() for _ in range(n_patients)]
    if ids:
        await database.patients.insert_many([
            patient_doc(
                _id=pid, camp_id=camp_id, camp_day_id=day_id, phone=phone, phone_normalized=phone,
                full_name=f"P{i}", reg_no=1000 + i,
            )
            for i, pid in enumerate(ids)
        ])
    return camp_id, day_id, ids


async def _numbered_camp(database):
    camp_id = ObjectId()
    await database.camps.insert_one({"_id": camp_id, "name": "C", "venue": "Hall A", "camp_number": 162})
    return camp_id


async def _post(client, secret=SECRET):
    return await client.post("/api/cron/reminders", headers={"X-Cron-Secret": secret})


async def _ledger(database):
    return await database.reminder_ledger.find().sort("_id", 1).to_list(None)


async def _age_ledger(database, by):
    await database.reminder_ledger.update_many(
        {}, [{"$set": {"created_at": {"$subtract": ["$created_at", by // timedelta(milliseconds=1)]}}}],
    )


class TestMessageCopy:
    def test_six_approved_devanagari_strings(self):
        assert REGISTRATION_CONFIRMATION == "Sikar Zilla Welfare Trust के {camp_no}वें नेत्र शिविर में आपका पंजीकरण हो गया है। क्रमांक: {reg_no} दिनांक: {date} शिविर स्थल: {venue}। कृपया शिविर के दिन अपना आधार कार्ड अवश्य साथ लाएँ।"
        assert CAMP_REMINDER == "कल ({date}) को Sikar Zilla Welfare Trust के {camp_no} वें नेत्र शिविर में आपका नेत्र परीक्षण है। कृपया समय पर {venue} पहुँचें। यह टोकन शिविर स्थल पर दिखाएँ। क्रमांक: {reg_no}। कृपया शिविर के दिन अपना आधार कार्ड अवश्य साथ लाएँ।"
        assert OT_TOKEN == "Sikar Zilla Welfare Trust के {camp_no} वें नेत्र शिविर में आपका ऑपरेशन {date} को निर्धारित हुआ है। पर्चा, टोकन ({reg_no}), आधार कार्ड, राशन कार्ड और मोबाइल नंबर अवश्य साथ लाएँ। स्थल: {venue}।"
        assert OT_REMINDER == "कल ({date}) को Sikar Zilla Welfare Trust के {camp_no} वें नेत्र शिविर में आपका नेत्र ऑपरेशन निर्धारित है। पर्चा, टोकन ({reg_no}), आधार कार्ड, राशन कार्ड और मोबाइल नंबर साथ अवश्य लाएँ। स्थल: {venue}।"
        assert SPECS_TOKEN == "Sikar Zilla Welfare Trust के {camp_no} वें नेत्र शिविर में आपको चश्मा {date} से {end_date} तक प्रतिदिन 10:00 AM से 5:00 PM तक {venue} में दिया जाएगा। कृपया चश्मे का टोकन ({reg_no}) लेकर अवश्य आएँ।"
        assert SPECS_REMINDER == "Sikar Zilla Welfare Trust के {camp_no} वे शिविर के चश्मे बनकर तैयार हैं। चश्मे {date} से {end_date} तक प्रतिदिन 10:00 AM से 5:00 PM तक {venue} आकर ले जाएँ। टोकन क्रमांक {reg_no} अवश्य साथ लाएँ।"

    def test_the_dlt_reference_registers_exactly_the_code_copy(self):
        doc = json.loads((backend_dir / "docs" / "msg91-templates.json").read_text(encoding="utf-8"))
        assert [t["key"] for t in doc["templates"]] == list(sms.MESSAGE_COPY)
        for t in doc["templates"]:
            body = sms.MESSAGE_COPY[t["key"]]
            assert t["body"] == body
            assert t["variables"] == [name for _, name, _, _ in string.Formatter().parse(body) if name]
            assert t["dlt_body"] == re.sub(r"\{(\w+)\}", r"##\1##", body)
            assert t["dlt_portal_body"] == re.sub(r"\{\w+\}", "{#var#}", body)

    def test_complete_surgery_copy_keeps_all_required_documents(self):
        rendered = [
            copy.format(reg_no=999999, camp_no="162", date="02-09-2026", end_date="09-09-2026",
                        start_time="10:00", end_time="05:00", venue="Sikar Bhawan Kolkata")
            for copy in sms.MESSAGE_COPY.values()
        ]
        assert all(len(text) <= 335 for text in rendered), [len(t) for t in rendered]
        assert "आधार कार्ड, राशन कार्ड और मोबाइल नंबर" in rendered[2]
        assert "आधार कार्ड, राशन कार्ड और मोबाइल नंबर" in rendered[3]


class TestReminderCronHttp:
    def test_failed_provider_call_is_reported_and_retried_without_duplicate_success(self, monkeypatch):
        captured = recorder(monkeypatch)
        provider = msg91.send_dlt_sms

        def fail(*args, **kwargs):
            raise msg91.Unsent("connection refused")

        async def body(database, client):
            await _seed_camp_household(database, n_patients=1)
            monkeypatch.setattr(msg91, "send_dlt_sms", fail)
            first = (await _post(client)).json()
            assert first["ok"] is False
            assert first["failed"] == 1
            monkeypatch.setattr(msg91, "send_dlt_sms", provider)
            await _age_ledger(database, sms.RETRY_AFTER)
            retry = (await _post(client)).json()
            assert retry["ok"] is True
            assert retry["sent"] == 1
            assert await database.reminder_ledger.count_documents({}) == 1
            assert (await _post(client)).json()["sent"] == 0
            assert len(captured) == 1

        _run(monkeypatch, body)

    def test_wrong_secret_refused(self, monkeypatch):
        async def body(database, client):
            assert (await _post(client, secret="nope")).status_code == 401

        _run(monkeypatch, body)

    def test_missing_secret_refused(self, monkeypatch):
        async def body(database, client):
            assert (await client.post("/api/cron/reminders")).status_code == 401

        _run(monkeypatch, body)

    def test_msg91_unset_does_not_500(self, monkeypatch):
        async def body(database, client):
            r = await _post(client)
            assert r.status_code == 200, r.text
            assert r.json()["ok"] is True
            assert r.json()["sent"] == 0

        _run(monkeypatch, body, msg91_on=False)

    def test_approved_reminder_sends_while_specs_template_is_unavailable(self, monkeypatch):
        configured = msg91.configured
        captured = recorder(monkeypatch)
        monkeypatch.setattr(msg91, "configured", configured)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=1)
            monkeypatch.delenv("MSG91_TEMPLATE_SPECS_TOKEN")
            monkeypatch.delenv("MSG91_TEMPLATE_SPECS")

            response = await _post(client)

            assert response.status_code == 200, response.text
            assert response.json()["sent"] == 1
            assert [call["type"] for call in captured] == ["camp"]
            patient = await database.patients.find_one()
            assert await sms.deliver_patient_sms(
                database, patient, "specs", TOMORROW, "Hall A", "10:00", "17:00",
            ) == "skipped"
            assert [row["message_type"] for row in await _ledger(database)] == ["camp"]

        _run(monkeypatch, body)

    def test_household_of_four_sends_four_camp_reminders(self, monkeypatch):
        captured = recorder(monkeypatch)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=4, phone=HOUSEHOLD, venue="Hall A")
            r = await _post(client)
            assert r.status_code == 200, r.text
            assert r.json()["sent"] == 4
            assert [c["mobile"] for c in captured] == [HOUSEHOLD] * 4
            assert sorted(c["reg_no"] for c in captured) == [1000, 1001, 1002, 1003]
            assert {c["type"] for c in captured} == {"camp"}
            assert {c["date"] for c in captured} == {TOMORROW_SHOWN}
            assert await database.reminder_ledger.count_documents({}) == 4

        _run(monkeypatch, body)

    def test_camp_reminder_ledger_row_carries_reg_no_copy(self, monkeypatch):
        recorder(monkeypatch)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=1, phone=HOUSEHOLD, venue="Hall A")
            assert (await _post(client)).status_code == 200
            [row] = await _ledger(database)
            assert row["message_type"] == "camp"
            assert row["event_date"] == TOMORROW
            assert row["number"] == HOUSEHOLD
            assert row["status"] == "sent"
            assert row["provider_id"] == "id-1"
            assert row["copy"] == CAMP_REMINDER.format(reg_no=1000, camp_no=162, date=TOMORROW_SHOWN, venue="Hall A")

        _run(monkeypatch, body)

    def test_same_patient_camp_and_ot_sends_two(self, monkeypatch):
        captured = recorder(monkeypatch)

        async def body(database, client):
            camp_id, _day_id, ids = await _seed_camp_household(database, n_patients=1, phone=HOUSEHOLD, venue="Hall A")
            ot_day = ObjectId()
            await database.ot_schedule_days.insert_one({
                "_id": ot_day, "camp_id": camp_id, "day_date": TOMORROW,
                "venue": "OT Theatre", "seat_limit": 5, "seats_taken": 1,
            })
            await database.deferred_slips.insert_one({
                "patient_id": ids[0], "item_type": "ot", "active": True, "cancelled": False,
                "collection_date": TOMORROW, "collection_venue": "stale",
                "ot_schedule_day_id": ot_day, "version": 1,
            })
            r = await _post(client)
            assert r.status_code == 200, r.text
            assert r.json()["sent"] == 2
            assert {(c["type"], c["venue"]) for c in captured} == {("camp", "Hall A"), ("ot", "OT Theatre")}

        _run(monkeypatch, body)

    def test_cancelled_token_excluded_from_ot_and_specs(self, monkeypatch):
        captured = recorder(monkeypatch)

        async def body(database, client):
            camp_id = await _numbered_camp(database)
            pid = ObjectId()
            await database.patients.insert_one(patient_doc(
                _id=pid, camp_id=camp_id, camp_day_id=ObjectId(), reg_no=7,
                phone=HOUSEHOLD, phone_normalized=HOUSEHOLD,
            ))
            await database.deferred_slips.insert_many([
                {
                    "patient_id": pid, "item_type": "ot", "active": False, "cancelled": True,
                    "collection_date": TOMORROW, "collection_venue": "OT Theatre", "version": 1,
                },
                {
                    "patient_id": pid, "item_type": "specs_made", "active": False, "cancelled": True,
                    "collection_date": TOMORROW, "collection_venue": "Optical", "version": 1,
                    "collection_start_time": "10:00", "collection_end_time": "17:00",
                },
            ])
            r = await _post(client)
            assert r.status_code == 200, r.text
            assert captured == []
            assert r.json()["sent"] == 0

        _run(monkeypatch, body)

    def test_missing_and_invalid_numbers_skipped(self, monkeypatch):
        captured = recorder(monkeypatch)

        async def body(database, client):
            camp_id, (day_id,) = await seed_camp(database, days=(TOMORROW,), venue="Hall A")
            await database.patients.insert_many([
                patient_doc(camp_id=camp_id, camp_day_id=day_id, reg_no=reg_no, phone=phone, phone_normalized=phone)
                for reg_no, phone in ((1, None), (2, "9999999999"), (3, "123"))
            ])
            r = await _post(client)
            assert r.status_code == 200, r.text
            assert captured == []
            assert await _ledger(database) == []

        _run(monkeypatch, body)

    def test_second_run_same_event_date_emits_nothing_extra(self, monkeypatch):
        captured = recorder(monkeypatch)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=4, phone=HOUSEHOLD, venue="Hall A")
            r1 = await _post(client)
            r2 = await _post(client)
            assert r1.json()["sent"] == 4
            assert r2.json()["sent"] == 0
            assert len(captured) == 4
            assert await database.reminder_ledger.count_documents({}) == 4

        _run(monkeypatch, body)

    def test_specs_reminder_states_the_token_window_range_and_hours(self, monkeypatch):
        captured = recorder(monkeypatch)

        async def body(database, client):
            pid = ObjectId()
            camp_id = await _numbered_camp(database)
            specs_day = ObjectId()
            await database.patients.insert_one(patient_doc(
                _id=pid, camp_id=camp_id, camp_day_id=ObjectId(), reg_no=42,
                phone=HOUSEHOLD, phone_normalized=HOUSEHOLD,
            ))
            await database.specs_collection_days.insert_one({
                "_id": specs_day, "day_date": TOMORROW, "end_date": day(11), "venue": "Optical Desk",
                "start_time": "09:00", "end_time": "16:00", "camp_id": camp_id,
            })
            await database.deferred_slips.insert_one({
                "patient_id": pid, "item_type": "specs_made", "active": True, "cancelled": False,
                "collection_date": TOMORROW, "collection_end_date": day(8),
                "collection_venue": "Token Hall",
                "collection_start_time": "10:00", "collection_end_time": "17:00",
                "specs_collection_day_id": specs_day, "version": 1,
            })
            r = await _post(client)
            assert r.status_code == 200, r.text
            assert captured == [{
                "type": "specs", "mobile": HOUSEHOLD, "reg_no": 42, "camp_no": "162",
                "date": TOMORROW_SHOWN, "end_date": "13-10-2026",
                "venue": "Token Hall",
            }]
            [row] = await _ledger(database)
            assert row["copy"] == (
                "Sikar Zilla Welfare Trust के 162 वे शिविर के चश्मे बनकर तैयार हैं। चश्मे 06-10-2026 से 13-10-2026 तक "
                "प्रतिदिन 10:00 AM से 5:00 PM तक Token Hall आकर ले जाएँ। टोकन क्रमांक 42 अवश्य साथ लाएँ।"
            )

        _run(monkeypatch, body)

    def test_a_single_day_legacy_token_reads_as_a_one_day_range(self, monkeypatch):
        captured = recorder(monkeypatch)

        async def body(database, client):
            pid = ObjectId()
            camp_id = await _numbered_camp(database)
            await database.patients.insert_one(patient_doc(
                _id=pid, camp_id=camp_id, camp_day_id=ObjectId(), reg_no=42,
                phone=HOUSEHOLD, phone_normalized=HOUSEHOLD,
            ))
            await database.deferred_slips.insert_one({
                "patient_id": pid, "item_type": "specs_made", "active": True, "cancelled": False,
                "collection_date": TOMORROW, "collection_venue": "Token Hall",
                "collection_start_time": "10:00", "collection_end_time": "17:00", "version": 1,
            })
            await _post(client)
            assert [(c["date"], c["end_date"]) for c in captured] == [
                (TOMORROW_SHOWN, TOMORROW_SHOWN),
            ]

        _run(monkeypatch, body)

    def test_camp_without_a_number_sends_nothing_until_the_admin_sets_it(self, monkeypatch):
        captured = recorder(monkeypatch)

        async def body(database, client):
            camp_id, _day, _ids = await _seed_camp_household(database, n_patients=1, camp_number=None)
            assert (await _post(client)).json()["sent"] == 0
            assert captured == []
            assert await _ledger(database) == []
            await database.camps.update_one({"_id": camp_id}, {"$set": {"camp_number": 162}})
            assert (await _post(client)).json()["sent"] == 1
            assert captured[0]["camp_no"] == "162"

        _run(monkeypatch, body)

    def test_venue_over_dlt_variable_limit_is_not_submitted_or_charged(self, monkeypatch):
        captured = recorder(monkeypatch)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=1, venue="A" * 31)

            result = (await _post(client)).json()

            assert result["sent"] == 0
            assert captured == []
            assert await _ledger(database) == []

        _run(monkeypatch, body)

    def test_camp_reminder_uses_short_sms_venue(self, monkeypatch):
        captured = recorder(monkeypatch)

        async def body(database, client):
            camp_id, _day, _ids = await _seed_camp_household(database, n_patients=1, venue="A" * 64)
            await database.camps.update_one({"_id": camp_id}, {"$set": {"venue_sms": "Short Camp Venue"}})

            result = (await _post(client)).json()

            assert result["sent"] == 1
            assert captured[0]["venue"] == "Short Camp Venue"

        _run(monkeypatch, body)

    def test_ot_reminder_prefers_the_short_sms_venue(self, monkeypatch):
        long_venue = "Vimla Ramkrishna Bajaj Eye Hospital, Near Canara Bank, Bilasi Mod, Deoghar 814112 (Jharkhand)"
        captured = recorder(monkeypatch)

        async def body(database, client):
            pid = ObjectId()
            ot_day = ObjectId()
            camp_id = await _numbered_camp(database)
            await database.patients.insert_one(patient_doc(
                _id=pid, camp_id=camp_id, camp_day_id=ObjectId(), reg_no=11,
                phone=HOUSEHOLD, phone_normalized=HOUSEHOLD,
            ))
            await database.ot_schedule_days.insert_one({
                "_id": ot_day, "day_date": TOMORROW, "camp_id": ObjectId(),
                "venue": long_venue, "venue_sms": "बजाज हॉस्पिटल, देवघर",
            })
            await database.deferred_slips.insert_one({
                "patient_id": pid, "item_type": "ot", "active": True, "cancelled": False,
                "collection_date": TOMORROW, "collection_venue": long_venue,
                "ot_schedule_day_id": ot_day, "version": 1,
            })
            r = await _post(client)
            assert r.status_code == 200, r.text
            assert captured == [{
                "type": "ot", "mobile": HOUSEHOLD, "reg_no": 11, "camp_no": "162",
                "date": TOMORROW_SHOWN, "venue": "बजाज हॉस्पिटल, देवघर",
            }]
            [row] = await _ledger(database)
            assert long_venue not in row["copy"]

        _run(monkeypatch, body)
