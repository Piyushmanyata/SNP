"""Specs collection days are date/venue/time windows with no capacity."""
import httpx
import pytest
from bson import ObjectId
from fastapi import HTTPException

import helpers
import routes_clinical
import security
import server
from routes_clinical import record_fulfilment
from seed import CLINICAL, TODAY, day, fulfil, recorder, run_camp, seed_camp, seen_patient, user_doc

FUTURE = day(7)


def _headers(monkeypatch, user_id, role):
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-of-at-least-32-bytes")
    return {"Authorization": f"Bearer {security.create_access_token(str(user_id), role, role)}"}


def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test")


def _post_specs_day(client, headers, camp_id, **fields):
    return client.post("/api/clinical/specs-days", json={
        "camp_id": str(camp_id), "day_date": FUTURE, **fields,
    }, headers=headers)


async def _camp_with_admin(database, admin_id):
    await database.users.insert_one(user_doc("admin", role="admin", _id=admin_id))
    camp_id, _ = await seed_camp(database, days=())
    return camp_id


def _defer(seen, day_id, operation_id):
    return record_fulfilment(fulfil(
        seen["trans_id"], seen["rev_id"], item_type="specs_made", status="deferred",
        specs_collection_day_id=str(day_id), operation_id=operation_id,
    ), actor=CLINICAL, background_tasks=None)


def test_specs_create_update_list_window_contract(monkeypatch):
    admin_id = ObjectId()
    headers = _headers(monkeypatch, admin_id, "admin")

    async def body(database):
        camp_id = await _camp_with_admin(database, admin_id)
        async with _client() as client:
            created = await _post_specs_day(client, headers, camp_id, venue="Optical")
            assert created.status_code == 200
            assert created.json()["specs_day"]["start_time"] == "10:00"
            assert created.json()["specs_day"]["end_time"] == "17:00"

            inverted = await _post_specs_day(client, headers, camp_id, venue="  Optical Desk  ",
                                             start_time="14:00", end_time="14:00")
            assert inverted.status_code == 400

            created = await _post_specs_day(client, headers, camp_id, venue="  Optical Desk  ", seat_limit=12)
            assert created.status_code == 200
            row = created.json()["specs_day"]
            assert row["venue"] == "Optical Desk"
            assert row["start_time"] == "10:00"
            assert row["end_time"] == "17:00"
            assert row["day_date"] == FUTURE
            assert "seat_limit" not in row
            assert "seats_taken" not in row
            assert "seats_free" not in row
            stored = await database.specs_collection_days.find_one({"_id": ObjectId(row["id"])})
            assert "seat_limit" not in stored
            assert "seats_taken" not in stored

            rejected = await _post_specs_day(client, headers, camp_id, venue="New Optical",
                                             start_time="11:00", end_time="13:00")
            assert rejected.status_code == 400
            updated = await _post_specs_day(client, headers, camp_id, venue="New Optical")
            assert updated.status_code == 200
            assert updated.json()["specs_day"]["id"] == row["id"]
            assert updated.json()["specs_day"]["venue"] == "New Optical"
            assert updated.json()["specs_day"]["start_time"] == "10:00"
            listed = await client.get("/api/clinical/specs-days", headers=headers)
            assert listed.status_code == 200
            days = listed.json()["specs_days"]
            assert len(days) == 1
            assert "seat_limit" not in days[0]
            assert days[0]["end_time"] == "17:00"

    run_camp(monkeypatch, body)


def test_specs_rejects_inactive_past_malformed_and_same_day_ended_window(monkeypatch):
    admin_id = ObjectId()
    headers = _headers(monkeypatch, admin_id, "admin")

    async def body(database):
        camp_id = await _camp_with_admin(database, admin_id)
        other = (await database.camps.insert_one({"name": "Other", "venue": "X", "is_active": False})).inserted_id
        window = {"venue": "Hall", "start_time": "09:00", "end_time": "11:00"}
        async with _client() as client:
            assert (await _post_specs_day(client, headers, other, **window)).status_code == 400
            assert (await _post_specs_day(client, headers, "not-an-id", **window)).status_code == 400
            assert (await _post_specs_day(client, headers, camp_id, **{**window, "day_date": day(-1)})).status_code == 400
            ended = await _post_specs_day(client, headers, camp_id, day_date=TODAY, venue="Hall",
                                          start_time="08:00", end_time="08:59")
            assert ended.status_code == 400

    run_camp(monkeypatch, body)


def test_many_specs_assignments_do_not_refuse_or_mutate_seats(monkeypatch):
    async def body(database):
        camp_id = ObjectId()
        first, second = await seen_patient(database, camp_id), await seen_patient(database, camp_id)
        day_id = (await database.specs_collection_days.insert_one({
            "camp_id": camp_id, "day_date": FUTURE, "venue": "Optical Desk", "start_time": "10:00", "end_time": "17:00",
        })).inserted_id
        assert (await _defer(first, day_id, "op-a"))["slip"]["collection_date"]
        assert (await _defer(second, day_id, "op-b"))["slip"]["collection_date"]
        assert "seats_taken" not in await database.specs_collection_days.find_one({"_id": day_id})

    run_camp(monkeypatch, body)


def test_clinical_specs_picker_rejects_ended_cross_camp_legacy_and_malformed(monkeypatch):
    async def body(database):
        seen = await seen_patient(database)
        camp_id = seen["camp_id"]
        window = {"start_time": "10:00", "end_time": "17:00"}
        days = await database.specs_collection_days.insert_many([
            {"camp_id": camp_id, "day_date": day(-1), "venue": "Old Hall", "start_time": "09:00", "end_time": "10:00"},
            {"camp_id": camp_id, "day_date": day(7), "venue": "Needs Window"},
            {"camp_id": camp_id, "day_date": day(8), "venue": "Saved Before The Hours Rule",
             "start_time": "14:00", "end_time": "17:00"},
            {"camp_id": camp_id, "day_date": day(9), "venue": "Old Hours", "start_time": "10:00", "end_time": "15:00"},
            {"camp_id": ObjectId(), "day_date": day(7), "venue": "Other Camp", "start_time": "09:00", "end_time": "13:00"},
            {"camp_id": camp_id, "day_date": day(10), "venue": "Optical Desk", **window},
        ])
        ended, legacy, afternoon, old_hours, other_camp, valid = days.inserted_ids
        for hours_rule_breaker in (afternoon, old_hours):
            stored = await database.specs_collection_days.find_one({"_id": hours_rule_breaker})
            assert routes_clinical.ser_specs_day(stored)["window_required"] is True

        for bad_id in (str(ended), str(legacy), str(afternoon), str(old_hours), "not-an-id", str(other_camp)):
            with pytest.raises(HTTPException) as exc:
                await _defer(seen, bad_id, bad_id)
            assert exc.value.status_code == 400

        ok = await _defer(seen, valid, "op-ok")
        assert ok["slip"]["collection_start_time"] == "10:00"
        assert ok["slip"]["collection_end_time"] == "17:00"
        assert ok["slip"]["collection_venue"] == "Optical Desk"

    run_camp(monkeypatch, body)


def test_specs_token_snapshot_survives_later_schedule_edit(monkeypatch):
    admin_id, operator_id = ObjectId(), ObjectId()
    headers = _headers(monkeypatch, admin_id, "admin")
    operator = _headers(monkeypatch, operator_id, "clinical_desk_operator")

    async def body(database):
        camp_id = await _camp_with_admin(database, admin_id)
        await database.users.insert_one(user_doc("Op", role="clinical_desk_operator", _id=operator_id))
        seen = await seen_patient(database, camp_id)
        async with _client() as client:
            created = await _post_specs_day(client, headers, camp_id, venue="Optical Desk")
            out = await _defer(seen, created.json()["specs_day"]["id"], "op-snap")
            assert out["slip"]["collection_start_time"] == "10:00"
            assert out["slip"]["collection_end_time"] == "17:00"
            moved = await _post_specs_day(client, headers, camp_id, venue="Moved Hall")
            assert moved.status_code == 200
            slip = await database.deferred_slips.find_one({"_id": ObjectId(out["slip"]["id"])})
            assert slip["collection_venue"] == "Optical Desk"
            assert slip["collection_start_time"] == "10:00"
            assert slip["collection_end_time"] == "17:00"
            reprint = await client.get(f"/api/clinical/slip/{out['slip']['id']}", headers=operator)
            assert reprint.status_code == 200
            assert reprint.json()["slip"]["collection_start_time"] == "10:00"
            assert reprint.json()["slip"]["collection_venue"] == "Optical Desk"

    run_camp(monkeypatch, body)


def test_specs_window_spans_days_from_a_morning_start_to_an_evening_end(monkeypatch):
    admin_id = ObjectId()
    headers = _headers(monkeypatch, admin_id, "admin")
    until = day(14)

    async def body(database):
        camp_id = await _camp_with_admin(database, admin_id)
        async with _client() as client:
            def post(**overrides):
                return _post_specs_day(client, headers, camp_id, **{
                    "end_date": until, "venue": "SNP कार्यालय, देवघर", "start_time": "10:00", "end_time": "17:00",
                    **overrides,
                })

            assert (await post(end_date=day(6))).status_code == 400
            assert (await post(end_date="14-09-2026")).status_code == 400
            assert (await post(start_time="13:00")).status_code == 400
            assert (await post(end_time="11:30")).status_code == 400
            created = await post()
            assert created.status_code == 200, created.text
            assert created.json()["specs_day"]["end_date"] == until
            single = await post(day_date=until, end_date=None)
            assert single.status_code == 200, single.text
            assert single.json()["specs_day"]["end_date"] == until

    run_camp(monkeypatch, body)


def test_started_window_stays_selectable_and_token_sms_states_the_range(monkeypatch):
    sent = recorder(monkeypatch)

    async def body(database):
        camp_id, _ = await seed_camp(database, days=())
        seen = await seen_patient(database, camp_id, reg_no=501)
        yesterday, until = day(-1), FUTURE
        day_id = (await database.specs_collection_days.insert_one({
            "camp_id": camp_id, "day_date": yesterday, "end_date": until,
            "venue": "SNP कार्यालय, देवघर", "start_time": "10:00", "end_time": "17:00",
        })).inserted_id
        out = await _defer(seen, day_id, "op-range")
        assert out["slip"]["collection_date"] == yesterday
        assert out["slip"]["collection_end_date"] == until
        assert sent == [{
            "type": "specs_token", "mobile": "9876500001", "reg_no": 501, "camp_no": "162",
            "date": helpers.display_date(yesterday), "end_date": helpers.display_date(until),
            "venue": "SNP कार्यालय, देवघर",
        }]

    run_camp(monkeypatch, body)
