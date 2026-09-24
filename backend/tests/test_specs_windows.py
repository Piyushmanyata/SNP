"""Specs collection days are a date range and a venue with fixed 10:00–17:00 hours and no capacity."""
import pytest
from bson import ObjectId
from fastapi import HTTPException

import helpers
from routes_clinical import record_fulfilment
from seed import CLINICAL, asgi_client, bearer, day, fulfil, recorder, run_camp, seed_camp, seen_patient, user_doc

FUTURE = day(7)


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


def test_specs_days_are_dates_and_a_venue_with_no_hours_or_seats(monkeypatch):
    admin_id = ObjectId()
    headers = bearer(admin_id, "admin", "admin")

    async def body(database):
        camp_id = await _camp_with_admin(database, admin_id)
        async with asgi_client() as client:
            created = await _post_specs_day(client, headers, camp_id, venue="  Optical Desk  ", seat_limit=12)
            assert created.status_code == 200
            row = created.json()["specs_day"]
            assert row["venue"] == "Optical Desk"
            assert row["day_date"] == FUTURE
            assert not {"seat_limit", "seats_taken", "seats_free", "start_time", "end_time"} & set(row)
            stored = await database.specs_collection_days.find_one({"_id": ObjectId(row["id"])})
            assert not {"seat_limit", "seats_taken", "start_time", "end_time"} & set(stored)

            again = await _post_specs_day(client, headers, camp_id, venue="New Optical")
            assert again.status_code == 409 and again.json()["detail"]["code"] == "DAY_EXISTS"
            updated = await client.patch(f"/api/clinical/specs-days/{row['id']}", json={
                "camp_id": str(camp_id), "day_date": FUTURE, "venue": "New Optical",
            }, headers=headers)
            assert updated.status_code == 200
            assert updated.json()["specs_day"]["venue"] == "New Optical"
            listed = await client.get("/api/clinical/specs-days", headers=headers)
            assert [d["venue"] for d in listed.json()["specs_days"]] == ["New Optical"]

    run_camp(monkeypatch, body)


def test_specs_rejects_inactive_past_and_malformed(monkeypatch):
    admin_id = ObjectId()
    headers = bearer(admin_id, "admin", "admin")

    async def body(database):
        camp_id = await _camp_with_admin(database, admin_id)
        other = (await database.camps.insert_one({"name": "Other", "venue": "X", "is_active": False})).inserted_id
        async with asgi_client() as client:
            assert (await _post_specs_day(client, headers, other, venue="Hall")).status_code == 400
            assert (await _post_specs_day(client, headers, "not-an-id", venue="Hall")).status_code == 400
            assert (await _post_specs_day(client, headers, camp_id, venue="Hall", day_date=day(-1))).status_code == 400

    run_camp(monkeypatch, body)


def test_many_specs_assignments_do_not_refuse_or_mutate_seats(monkeypatch):
    async def body(database):
        camp_id = ObjectId()
        first, second = await seen_patient(database, camp_id), await seen_patient(database, camp_id)
        day_id = (await database.specs_collection_days.insert_one({
            "camp_id": camp_id, "day_date": FUTURE, "venue": "Optical Desk",
        })).inserted_id
        assert (await _defer(first, day_id, "op-a"))["slip"]["collection_date"]
        assert (await _defer(second, day_id, "op-b"))["slip"]["collection_date"]
        assert "seats_taken" not in await database.specs_collection_days.find_one({"_id": day_id})

    run_camp(monkeypatch, body)


def test_clinical_specs_picker_rejects_ended_cross_camp_and_malformed(monkeypatch):
    async def body(database):
        seen = await seen_patient(database)
        camp_id = seen["camp_id"]
        days = await database.specs_collection_days.insert_many([
            {"camp_id": camp_id, "day_date": day(-1), "venue": "Old Hall"},
            {"camp_id": ObjectId(), "day_date": day(7), "venue": "Other Camp"},
            {"camp_id": camp_id, "day_date": day(10), "venue": "Optical Desk"},
        ])
        ended, other_camp, valid = days.inserted_ids
        for bad_id in (str(ended), "not-an-id", str(other_camp)):
            with pytest.raises(HTTPException) as exc:
                await _defer(seen, bad_id, bad_id)
            assert exc.value.status_code == 400

        ok = await _defer(seen, valid, "op-ok")
        assert ok["slip"]["collection_venue"] == "Optical Desk"
        assert "collection_start_time" not in ok["slip"]

    run_camp(monkeypatch, body)


def test_a_specs_day_edit_replaces_the_token_and_the_old_one_reprints_as_replaced(monkeypatch):
    admin_id, operator_id = ObjectId(), ObjectId()
    headers = bearer(admin_id, "admin", "admin")
    operator = bearer(operator_id, "clinical_desk_operator", "clinical_desk_operator")

    async def body(database):
        camp_id = await _camp_with_admin(database, admin_id)
        await database.users.insert_one(user_doc("Op", role="clinical_desk_operator", _id=operator_id))
        seen = await seen_patient(database, camp_id)
        async with asgi_client() as client:
            created = (await _post_specs_day(client, headers, camp_id, venue="Optical Desk")).json()["specs_day"]
            out = await _defer(seen, created["id"], "op-snap")
            moved = await client.patch(f"/api/clinical/specs-days/{created['id']}", json={
                "camp_id": str(camp_id), "day_date": FUTURE, "venue": "Moved Hall",
            }, headers=headers)
            assert moved.status_code == 200
            old = (await client.get(f"/api/clinical/slip/{out['slip']['id']}", headers=operator)).json()["slip"]
            assert old["collection_venue"] == "Optical Desk" and old["superseded"] is True
            current = await database.deferred_slips.find_one({"transcription_id": seen["trans_id"], "active": True})
            assert current["collection_venue"] == "Moved Hall"
            reprint = (await client.get(f"/api/clinical/slip/{current['_id']}", headers=operator)).json()["slip"]
            assert reprint["replaces"] == out["slip"]["id"] and reprint["superseded"] is False

    run_camp(monkeypatch, body)


def test_specs_window_spans_days_from_a_morning_start_to_an_evening_end(monkeypatch):
    admin_id = ObjectId()
    headers = bearer(admin_id, "admin", "admin")
    until = day(14)

    async def body(database):
        camp_id = await _camp_with_admin(database, admin_id)
        async with asgi_client() as client:
            def post(**overrides):
                return _post_specs_day(client, headers, camp_id, **{
                    "end_date": until, "venue": "SNP कार्यालय, देवघर", **overrides,
                })

            assert (await post(end_date=day(6))).status_code == 400
            assert (await post(end_date="14-09-2026")).status_code == 400
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
            "venue": "SNP कार्यालय, देवघर",
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
