"""Medicine and fixed-power catalogue: normalisation, power parsing, and snapshot resolution."""
import asyncio

import pytest
from bson import ObjectId
from fastapi import HTTPException

import routes_catalogue as routes
from catalogue import (
    format_power,
    medicine_key,
    normalize_medicine_name,
    parse_power,
    resolve_medicines,
    ser_power,
    stocked_power,
)
from conftest import run_db
from models import CatalogueActiveBody, FixedPowerBody, MedicineBody

ADMIN = {"_id": ObjectId(), "role": "admin"}


def _with_catalogue(check, medicines=(), powers=()):
    async def body(db):
        if medicines:
            await db.medicines.insert_many([{**m, "name_key": medicine_key(m["name"])} for m in medicines])
        if powers:
            await db.fixed_powers.insert_many([{"value": value} for value in powers])
        return await check(db)

    return run_db(body)


def test_medicine_name_collapses_whitespace_and_keys_case_insensitively():
    assert normalize_medicine_name("  Moxifloxacin   0.5%  ") == "Moxifloxacin 0.5%"
    assert medicine_key("Moxifloxacin") == medicine_key("  moxifloxacin ")


@pytest.mark.parametrize("raw", ["", "   ", None, "x" * 121])
def test_medicine_name_rejects_blank_and_overlong(raw):
    with pytest.raises(HTTPException) as exc:
        normalize_medicine_name(raw)
    assert exc.value.status_code == 400


@pytest.mark.parametrize(
    "raw,expected",
    [("+2.00", 2.0), ("-1.5", -1.5), (2, 2.0), (-0.001, 0.0), ("0", 0.0), (2.256, 2.26)],
)
def test_parse_power_accepts_signed_text_and_numbers(raw, expected):
    assert parse_power(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", None, True, "nan", "inf", 20.01, -20.01])
def test_parse_power_rejects_junk_and_out_of_range(raw):
    with pytest.raises(HTTPException) as exc:
        parse_power(raw)
    assert exc.value.status_code == 400


def test_format_power_always_carries_a_sign_and_two_decimals():
    assert format_power(2) == "+2.00"
    assert format_power("-1.5") == "-1.50"
    assert format_power(-0.001) == "+0.00"


def test_ser_power_labels_the_stored_value():
    assert ser_power({"_id": ObjectId(), "value": -1.25, "active": True})["label"] == "-1.25"


def test_resolve_medicines_snapshots_names_in_order_and_dedupes():
    a, b = ObjectId(), ObjectId()
    out = _with_catalogue(
        lambda db: resolve_medicines(db, [str(b), str(a), str(b)], active_only=True),
        medicines=[{"_id": a, "name": "Moxifloxacin"}, {"_id": b, "name": "Timolol"}],
    )
    assert out == [
        {"medicine_id": str(b), "name": "Timolol"},
        {"medicine_id": str(a), "name": "Moxifloxacin"},
    ]


def test_resolve_medicines_returns_empty_for_no_ids():
    assert asyncio.run(resolve_medicines(None, [], active_only=True)) == []


@pytest.mark.parametrize("bad", [["not-an-objectid"], [str(ObjectId())]])
def test_resolve_medicines_refuses_ids_outside_the_catalogue(bad):
    with pytest.raises(HTTPException) as exc:
        _with_catalogue(lambda db: resolve_medicines(db, bad, active_only=True), medicines=[{"_id": ObjectId(), "name": "Moxifloxacin"}])
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "unknown_medicine"


def test_stocked_power_passes_through_none_and_accepts_a_stocked_value():
    assert asyncio.run(stocked_power(None, None, active_only=True)) is None
    assert _with_catalogue(lambda db: stocked_power(db, "+2.00", active_only=True), powers=[2.0]) == 2.0


def test_stocked_power_refuses_a_power_the_camp_does_not_carry():
    with pytest.raises(HTTPException) as exc:
        _with_catalogue(lambda db: stocked_power(db, "+2.25", active_only=True), powers=[2.0])
    assert exc.value.detail["code"] == "unknown_power"


class TestCatalogueRoutes:
    def test_adding_a_medicine_twice_reactivates_rather_than_duplicating(self):
        async def run(db):
            first = await routes.add_medicine(MedicineBody(name="Moxifloxacin"), actor=ADMIN)
            await routes.set_medicine_active(
                first["medicine"]["id"], CatalogueActiveBody(active=False), actor=ADMIN,
            )
            assert (await routes.list_medicines(actor=ADMIN))["medicines"] == []
            again = await routes.add_medicine(MedicineBody(name="  moxifloxacin  "), actor=ADMIN)
            assert again["medicine"]["id"] == first["medicine"]["id"]
            assert again["medicine"]["active"] is True
            assert await db.medicines.count_documents({}) == 1
        run_db(run)

    def test_operators_see_only_active_entries_and_admins_can_see_all(self):
        async def run(db):
            kept = await routes.add_medicine(MedicineBody(name="Timolol"), actor=ADMIN)
            retired = await routes.add_medicine(MedicineBody(name="Atropine"), actor=ADMIN)
            await routes.set_medicine_active(
                retired["medicine"]["id"], CatalogueActiveBody(active=False), actor=ADMIN,
            )
            active = await routes.list_medicines(actor=ADMIN)
            assert [m["name"] for m in active["medicines"]] == [kept["medicine"]["name"]]
            everything = await routes.list_medicines(include_inactive=True, actor=ADMIN)
            assert {m["name"] for m in everything["medicines"]} == {"Timolol", "Atropine"}
        run_db(run)

    def test_powers_are_stored_once_per_value_and_listed_in_dioptre_order(self):
        async def run(db):
            for raw in (2.0, "-1.50", "+2.00", 0.25):
                await routes.add_power(FixedPowerBody(value=raw), actor=ADMIN)
            listed = await routes.list_powers(actor=ADMIN)
            assert [p["label"] for p in listed["powers"]] == ["-1.50", "+0.25", "+2.00"]
            assert await db.fixed_powers.count_documents({}) == 3
        run_db(run)

    def test_deactivating_something_that_does_not_exist_is_a_404(self):
        async def run(db):
            for bad in (str(ObjectId()), "not-an-objectid"):
                with pytest.raises(HTTPException) as exc:
                    await routes.set_power_active(bad, CatalogueActiveBody(active=False), actor=ADMIN)
                assert exc.value.status_code == 404
        run_db(run)
