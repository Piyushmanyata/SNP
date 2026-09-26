import base64
import random
from io import BytesIO

import pytest
from bson import ObjectId
from fastapi import HTTPException
from PIL import Image

from models import ScanBody, ScanConfirmBody
from routes_desk import arrive, preview_prescription, print_prescription, scan, scan_confirm
from routes_templates import save_logos
from seed import ACTOR, ADMIN, CARD, NOW, register, run_camp, seed_camp


def _data_url(image, fmt):
    buffer = BytesIO()
    image.save(buffer, fmt)
    return f"data:image/{fmt.lower()};base64," + base64.b64encode(buffer.getvalue()).decode()


def _noisy():
    return Image.frombytes("RGB", (450, 225), random.Random(1).randbytes(450 * 225 * 3)).resize((1800, 900), Image.NEAREST)


def test_a_door_scan_that_arrives_carries_its_prescription(monkeypatch):
    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database)
        booked = await register(day_id, full_name="Sunita Devi", gender="F", dob="1975-06-14",
                                aadhaar_last4="1234", aadhaar_scanned=True)
        out = await scan(ScanBody(payload=CARD), actor=ACTOR)
        assert out["outcome"] == "arrived"
        rx = out["prescription"]
        assert rx["reg_no"] == booked["reg_no"] and rx["full_name"] == "Sunita Devi" and rx["patient_qr"]
        assert rx["camp_id"] and rx["date"]

    run_camp(monkeypatch, run)


def test_confirm_and_arrive_carry_the_prescription_only_when_it_can_print(monkeypatch):
    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database)
        manual = await register(day_id, full_name="Sunita Devi", age=51, aadhaar_last4="1234")
        confirmed = await scan_confirm(ScanConfirmBody(patient_id=manual["id"], payload=CARD), actor=ACTOR)
        assert confirmed["prescription"]["reg_no"] == manual["reg_no"]

        held = await register(day_id, full_name="Held Patient", age=40, phone="9876500041")
        await database.patients.update_one({"_id": ObjectId(held["id"])}, {"$set": {"no_card_print": {"reason": "no_card"}}})
        assert (await arrive(held["id"], actor=ACTOR))["prescription"] is None

        seen = await register(day_id, full_name="Seen Patient", age=60, phone="9876500042", aadhaar_scanned=True,
                              aadhaar_last4="4242", dob="1966-01-01")
        await database.patients.update_one({"_id": ObjectId(seen["id"])}, {"$set": {
            "arrived_at": NOW, "printed_at": NOW, "queue_status": "seen",
        }})
        assert (await arrive(seen["id"], actor=ACTOR))["prescription"] is None

        walk_in = await register(day_id, full_name="Walk In", age=33, phone="9876500043", aadhaar_scanned=True,
                                 aadhaar_last4="4343", dob="1993-01-01")
        assert (await arrive(walk_in["id"], actor=ACTOR))["prescription"]["full_name"] == "Walk In"

    run_camp(monkeypatch, run)


def test_a_saved_logo_is_resized_to_600_px_and_150_kb(monkeypatch):
    async def run(database):
        camp_id, _days = await seed_camp(database)
        big = _data_url(_noisy(), "PNG")
        assert len(big) > 2 * 150 * 1024
        saved = (await save_logos({"camp_id": str(camp_id), "logos": [
            {"id": "a", "name": "a.png", "data_url": big, "order": 0},
        ]}, actor=ADMIN))["logos"][0]
        header, b64 = saved["data_url"].split(",", 1)
        raw = base64.b64decode(b64)
        assert len(raw) <= 150 * 1024
        assert max(Image.open(BytesIO(raw)).size) == 600
        again = (await save_logos({"camp_id": str(camp_id), "logos": [saved]}, actor=ADMIN))["logos"][0]
        assert again["data_url"] == saved["data_url"]

    run_camp(monkeypatch, run)


def test_a_small_png_logo_stays_a_png(monkeypatch):
    async def run(database):
        camp_id, _days = await seed_camp(database)
        small = _data_url(Image.new("RGBA", (300, 100), (0, 0, 0, 0)), "PNG")
        saved = (await save_logos({"camp_id": str(camp_id), "logos": [
            {"id": "a", "name": "a.png", "data_url": small, "order": 0},
        ]}, actor=ADMIN))["logos"][0]
        assert saved["data_url"].startswith("data:image/png;base64,")

    run_camp(monkeypatch, run)


@pytest.mark.parametrize("logos, message", [
    ([{"id": str(i), "name": f"{i}.png", "data_url": "data:image/png;base64,AAAA", "order": i} for i in range(7)], "At most 6"),
    ([{"id": "x", "name": "x.png", "data_url": "https://example.com/x.png", "order": 0}], "Invalid image"),
    ([{"id": "x", "name": "x.png", "data_url": "data:image/png;base64,bm90IGFuIGltYWdl", "order": 0}], "Invalid image"),
])
def test_logos_beyond_the_limits_are_refused_not_dropped(monkeypatch, logos, message):
    async def run(database):
        camp_id, _days = await seed_camp(database)
        with pytest.raises(HTTPException) as exc:
            await save_logos({"camp_id": str(camp_id), "logos": logos}, actor=ADMIN)
        assert exc.value.status_code == 400 and message in str(exc.value.detail)
        assert await database.prescription_templates.count_documents({}) == 0

    run_camp(monkeypatch, run)


def test_the_sheet_is_refused_by_the_same_rules_as_the_stamp(monkeypatch):
    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database)
        held = await register(day_id, full_name="Held Patient", age=40, phone="9876500044")
        await database.patients.update_one({"_id": ObjectId(held["id"])}, {"$set": {"arrived_at": NOW}})
        for call in (preview_prescription, print_prescription):
            with pytest.raises(HTTPException) as exc:
                await call(held["id"], actor=ACTOR)
            assert exc.value.status_code == 409 and exc.value.detail["code"] == "NEEDS_DOOR_SCAN"

    run_camp(monkeypatch, run)
