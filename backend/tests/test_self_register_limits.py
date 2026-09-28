from datetime import timedelta

import httpx
import pytest
from fastapi import HTTPException

import limits
import routes_registration
import server
from conftest import advance_clock
from seed import day, recorder, run_camp, seed_camp
from test_public_limits import card


def _client(ip):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app, client=(ip, 1234)), base_url="http://testserver")


def _body(day_id, n, phone="9876500020"):
    return {"full_name": "x", "phone": phone, "camp_day_id": str(day_id),
            "qr_payload": card(f"Member {'abcdefghijklmnop'[n]}", f"55556666{1000 + n}")}


def test_a_limit_is_counted_in_the_database_and_refuses_past_it(monkeypatch):
    async def run(database):
        for _ in range(2):
            await limits.spend(database, "probe", "10.0.0.1", 2, timedelta(minutes=10))
        assert [c["count"] for c in await database.rate_limits.find({}).to_list(None)] == [2]
        with pytest.raises(HTTPException) as exc:
            await limits.spend(database, "probe", "10.0.0.1", 2, timedelta(minutes=10))
        assert exc.value.status_code == 429
        assert exc.value.detail["code"] == "TOO_MANY_ATTEMPTS_PLEASE_TRY_AGAIN_LATER"
        await limits.spend(database, "probe", "10.0.0.2", 2, timedelta(minutes=10))

    run_camp(monkeypatch, run)


def test_a_counter_expires_when_its_window_ends(monkeypatch):
    async def run(database):
        await limits.spend(database, "probe", "10.0.0.1", 1, timedelta(minutes=10))
        counter = await database.rate_limits.find_one({})
        assert timedelta(0) < counter["expires_at"] - limits.now_utc().replace(tzinfo=None) <= timedelta(minutes=10)
        ttl = {tuple(ix["key"]): ix.get("expireAfterSeconds") async for ix in await database.rate_limits.list_indexes()}
        assert ttl[("expires_at",)] == 0
        advance_clock(timedelta(minutes=10))
        await limits.spend(database, "probe", "10.0.0.1", 1, timedelta(minutes=10))

    run_camp(monkeypatch, run)


def test_the_phone_and_the_network_limits_trip_independently(monkeypatch):
    recorder()
    monkeypatch.setattr(routes_registration, "SELF_REGISTER_PER_PHONE", 2)
    monkeypatch.setattr(routes_registration, "SELF_REGISTER_PER_NETWORK", 3)

    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database, days=(day(1),))
        async with _client("10.0.0.1") as first, _client("10.0.0.2") as second:
            assert (await first.post("/api/self-register", json=_body(day_id, 0))).status_code == 200
            assert (await second.post("/api/self-register", json=_body(day_id, 1))).status_code == 200
            phone_limited = await second.post("/api/self-register", json=_body(day_id, 2))
            assert phone_limited.status_code == 429, phone_limited.text
            assert (await first.post("/api/self-register", json=_body(day_id, 3, "9876500021"))).status_code == 200
            assert (await first.post("/api/self-register", json=_body(day_id, 4, "9876500022"))).status_code == 200
            network_limited = await first.post("/api/self-register", json=_body(day_id, 6, "9876500024"))
            assert network_limited.status_code == 429, network_limited.text
            assert (await second.post("/api/self-register", json=_body(day_id, 5, "9876500023"))).status_code == 200
        assert await database.patients.count_documents({}) == 5

    run_camp(monkeypatch, run)


def test_the_camp_takes_a_ceiling_of_self_registrations_a_day(monkeypatch):
    recorder()
    monkeypatch.setattr(routes_registration, "SELF_REGISTER_PER_CAMP_DAY", 2)

    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database, days=(day(3),))
        async with _client("10.0.0.1") as client:
            refused_first = await client.post("/api/self-register", json={**_body(day_id, 0), "qr_payload": "no"})
            assert refused_first.status_code == 400
            for n, phone in ((1, "9876500031"), (2, "9876500032")):
                assert (await client.post("/api/self-register", json=_body(day_id, n, phone))).status_code == 200
            ceiling = await client.post("/api/self-register", json=_body(day_id, 3, "9876500033"))
            assert ceiling.status_code == 429, ceiling.text
            assert ceiling.json()["detail"]["code"] == "TOO_MANY_ATTEMPTS_PLEASE_TRY_AGAIN_LATER"
            advance_clock(timedelta(days=1))
            assert (await client.post("/api/self-register", json=_body(day_id, 3, "9876500033"))).status_code == 200
        assert await database.patients.count_documents({}) == 3

    run_camp(monkeypatch, run)
