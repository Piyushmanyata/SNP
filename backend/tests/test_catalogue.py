"""Medicine and fixed-power catalogue: normalisation, power parsing, and snapshot resolution."""
import asyncio
import os
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "snp_test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("AADHAAR_HASH_PEPPER", "test-pepper")

import pytest
from bson import ObjectId
from fastapi import HTTPException

from catalogue import (
    format_power,
    medicine_key,
    normalize_medicine_name,
    parse_power,
    resolve_medicines,
    ser_power,
    stocked_power,
)
from models import CatalogueActiveBody, FixedPowerBody, MedicineBody


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    async def to_list(self, _limit):
        return self._rows


class _Medicines:
    def __init__(self, rows):
        self._rows = rows

    def find(self, query):
        wanted = {str(o) for o in query["_id"]["$in"]}
        return _Cursor([r for r in self._rows if str(r["_id"]) in wanted])


class _Powers:
    def __init__(self, values):
        self._values = values

    async def find_one(self, query):
        value = query["value"]
        return {"value": value} if value in self._values else None


class _Db:
    def __init__(self, medicines=(), powers=()):
        self.medicines = _Medicines(list(medicines))
        self.fixed_powers = _Powers(set(powers))


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
    db = _Db(medicines=[{"_id": a, "name": "Moxifloxacin"}, {"_id": b, "name": "Timolol"}])
    out = asyncio.run(resolve_medicines(db, [str(b), str(a), str(b)]))
    assert out == [
        {"medicine_id": str(b), "name": "Timolol"},
        {"medicine_id": str(a), "name": "Moxifloxacin"},
    ]


def test_resolve_medicines_returns_empty_for_no_ids():
    assert asyncio.run(resolve_medicines(_Db(), [])) == []


@pytest.mark.parametrize("bad", [["not-an-objectid"], [str(ObjectId())]])
def test_resolve_medicines_refuses_ids_outside_the_catalogue(bad):
    db = _Db(medicines=[{"_id": ObjectId(), "name": "Moxifloxacin"}])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(resolve_medicines(db, bad))
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "unknown_medicine"


def test_stocked_power_passes_through_none_and_accepts_a_stocked_value():
    db = _Db(powers=[2.0])
    assert asyncio.run(stocked_power(db, None)) is None
    assert asyncio.run(stocked_power(db, "+2.00")) == 2.0


def test_stocked_power_refuses_a_power_the_camp_does_not_carry():
    db = _Db(powers=[2.0])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(stocked_power(db, "+2.25"))
    assert exc.value.detail["code"] == "unknown_power"


ADMIN = {"_id": ObjectId(), "role": "admin"}


def _routes(monkeypatch):
    import routes_catalogue
    from test_adversarial_challenger import MockDB

    mock_db = MockDB()
    monkeypatch.setattr(routes_catalogue, "get_db", lambda: mock_db)
    return routes_catalogue, mock_db


class TestCatalogueRoutes:
    def test_adding_a_medicine_twice_reactivates_rather_than_duplicating(self, monkeypatch):
        routes, mock_db = _routes(monkeypatch)

        async def run():
            first = await routes.add_medicine(MedicineBody(name="Moxifloxacin"), actor=ADMIN)
            await routes.set_medicine_active(
                first["medicine"]["id"], CatalogueActiveBody(active=False), actor=ADMIN,
            )
            assert (await routes.list_medicines(actor=ADMIN))["medicines"] == []
            again = await routes.add_medicine(MedicineBody(name="  moxifloxacin  "), actor=ADMIN)
            assert again["medicine"]["id"] == first["medicine"]["id"]
            assert again["medicine"]["active"] is True
            assert len(mock_db.medicines.docs) == 1
        asyncio.run(run())

    def test_operators_see_only_active_entries_and_admins_can_see_all(self, monkeypatch):
        routes, _mock_db = _routes(monkeypatch)

        async def run():
            kept = await routes.add_medicine(MedicineBody(name="Timolol"), actor=ADMIN)
            retired = await routes.add_medicine(MedicineBody(name="Atropine"), actor=ADMIN)
            await routes.set_medicine_active(
                retired["medicine"]["id"], CatalogueActiveBody(active=False), actor=ADMIN,
            )
            active = await routes.list_medicines(actor=ADMIN)
            assert [m["name"] for m in active["medicines"]] == [kept["medicine"]["name"]]
            everything = await routes.list_medicines(include_inactive=True, actor=ADMIN)
            assert {m["name"] for m in everything["medicines"]} == {"Timolol", "Atropine"}
        asyncio.run(run())

    def test_powers_are_stored_once_per_value_and_listed_in_dioptre_order(self, monkeypatch):
        routes, _mock_db = _routes(monkeypatch)

        async def run():
            for raw in (2.0, "-1.50", "+2.00", 0.25):
                await routes.add_power(FixedPowerBody(value=raw), actor=ADMIN)
            listed = await routes.list_powers(actor=ADMIN)
            assert [p["label"] for p in listed["powers"]] == ["-1.50", "+0.25", "+2.00"]
        asyncio.run(run())

    def test_deactivating_something_that_does_not_exist_is_a_404(self, monkeypatch):
        routes, _mock_db = _routes(monkeypatch)

        async def run():
            for bad in (str(ObjectId()), "not-an-objectid"):
                with pytest.raises(HTTPException) as exc:
                    await routes.set_power_active(bad, CatalogueActiveBody(active=False), actor=ADMIN)
                assert exc.value.status_code == 404
        asyncio.run(run())
