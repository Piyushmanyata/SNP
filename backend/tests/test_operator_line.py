"""Operator line, fulfilment matrix, correction, and camp-records export."""
import pytest
from bson import ObjectId
from fastapi import HTTPException
from pydantic import ValidationError

from models import CorrectionBody, CreateStaffBody, PatchStaffLineBody
from routes_clinical import add_correction, record_fulfilment
from routes_reports import export_camp_records
from routes_staff import create_staff, list_staff, patch_staff_line
from seed import (
    ADMIN, CLINICAL, FIXED_POWER, MEDICINE, OTHER_DAY, TOMORROW, asgi_client, bearer, fulfil, recorder, run_camp, seed_camp,
    seen_patient, user_doc,
)

PASS = "ClinicLine1!"
LINES = ("rx", "medicine", "specs_fixed", "specs_made", "ot")


def _issue(seen, rev_id=None, **kw):
    return record_fulfilment(fulfil(seen["trans_id"], rev_id or seen["rev_id"], **kw), actor=CLINICAL, background_tasks=None)


async def _specs_day(database, camp_id):
    return (await database.specs_collection_days.insert_one({
        "camp_id": camp_id, "day_date": TOMORROW, "venue": "Optical Desk",
        "start_time": "10:00", "end_time": "17:00", "seat_limit": 2, "seats_taken": 0,
    })).inserted_id


class TestOperatorLine:
    def test_each_of_the_five_lines_is_accepted_on_a_clinical_account(self, monkeypatch):
        async def body(database):
            for line in LINES:
                out = await create_staff(CreateStaffBody(
                    email=f"{line}@snpcamps.org", password=PASS, name=line,
                    role="clinical_desk_operator", line=line,
                ), actor=ADMIN)
                assert out["staff"]["line"] == line
                assert out["staff"]["role"] == "clinical_desk_operator"

        run_camp(monkeypatch, body)

    def test_an_out_of_vocabulary_line_is_refused(self, monkeypatch):
        async def body(database):
            with pytest.raises(HTTPException) as exc:
                await create_staff(CreateStaffBody(
                    email="bad@snpcamps.org", password=PASS, name="Bad",
                    role="clinical_desk_operator", line="pharmacy",
                ), actor=ADMIN)
            assert exc.value.status_code == 400

        run_camp(monkeypatch, body)

    def test_a_line_on_a_non_clinical_role_is_stored_as_null(self, monkeypatch):
        async def body(database):
            out = await create_staff(CreateStaffBody(name="Vol", role="volunteer", line="medicine"), actor=ADMIN)
            assert out["staff"]["line"] is None
            stored = await database.users.find_one({"_id": ObjectId(out["staff"]["id"])})
            assert stored["line"] is None

        run_camp(monkeypatch, body)

    def test_patch_accepts_only_line_including_null(self, monkeypatch):
        async def body(database):
            created = await create_staff(CreateStaffBody(
                email="op@snpcamps.org", password=PASS, name="Op",
                role="clinical_desk_operator", line="rx",
            ), actor=ADMIN)
            sid = created["staff"]["id"]
            patched = await patch_staff_line(sid, PatchStaffLineBody(line="ot"), actor=ADMIN)
            assert patched["staff"]["line"] == "ot"
            cleared = await patch_staff_line(sid, PatchStaffLineBody(line=None), actor=ADMIN)
            assert cleared["staff"]["line"] is None
            stored = await database.users.find_one({"_id": ObjectId(sid)})
            assert stored["line"] is None

        run_camp(monkeypatch, body)

    def test_patch_refuses_a_non_admin(self, monkeypatch):
        client = asgi_client()

        async def body(database):
            created = await create_staff(CreateStaffBody(
                email="op@snpcamps.org", password=PASS, name="Op",
                role="clinical_desk_operator", line="rx",
            ), actor=ADMIN)
            await database.users.insert_one(user_doc(
                "Clin", role="clinical_desk_operator", line="rx", _id=CLINICAL["_id"],
            ))
            async with client:
                r = await client.patch(
                    f"/api/staff/{created['staff']['id']}",
                    json={"line": "ot"},
                    headers=bearer(CLINICAL["_id"], "Clin"),
                )
            assert r.status_code == 403

        run_camp(monkeypatch, body)

    def test_patch_refuses_any_field_other_than_line(self):
        with pytest.raises(ValidationError):
            PatchStaffLineBody(line="rx", name="nope")
        with pytest.raises(ValidationError):
            PatchStaffLineBody(line="rx", role="admin")

    def test_listing_and_login_carry_line(self, monkeypatch):
        client = asgi_client()

        async def body(database):
            created = await create_staff(CreateStaffBody(name="Med", role="clinical_desk_operator", line="medicine"), actor=ADMIN)
            listed = await list_staff(actor=ADMIN)
            row = next(s for s in listed["staff"] if s["name"] == "Med")
            assert row["line"] == "medicine"
            async with client:
                r = await client.post("/api/auth/login", json={"name": "Med", "pin": created["temporary_pin"]})
            assert r.status_code == 200, r.text
            assert r.json()["user"]["line"] == "medicine"

        run_camp(monkeypatch, body)


class TestFulfilmentMatrix:
    def test_each_item_type_accepts_only_its_matrix(self, monkeypatch):
        recorder(monkeypatch)

        async def body(database):
            seen = await seen_patient(database)
            for item_type, status in (("medicine", "fulfilled"), ("medicine", "not_available"), ("specs_fixed", "fulfilled")):
                out = await _issue(seen, item_type=item_type, status=status)
                assert out["fulfilment"]["item_type"] == item_type
                assert out["fulfilment"]["status"] == status
            for item_type, status in (
                ("specs_fixed", "deferred"), ("specs_fixed", "not_available"), ("specs_made", "fulfilled"),
                ("ot", "not_available"), ("ot", "fulfilled"), ("specs", "fulfilled"),
            ):
                with pytest.raises(HTTPException) as exc:
                    await _issue(seen, item_type=item_type, status=status)
                assert exc.value.status_code == 400

        run_camp(monkeypatch, body)

    def test_not_required_is_refused_for_every_type(self, monkeypatch):
        async def body(database):
            seen = await seen_patient(database)
            for item_type in ("specs_fixed", "specs_made", "ot"):
                with pytest.raises(HTTPException) as exc:
                    await _issue(seen, item_type=item_type, status="not_required")
                assert exc.value.status_code == 400

        run_camp(monkeypatch, body)

    def test_the_medicine_line_status_comes_from_the_outcomes_not_the_body(self, monkeypatch):
        async def body(database):
            seen = await seen_patient(database, fixed_power=None)
            out = await _issue(
                seen, item_type="medicine", status="not_required",
                medicine_outcomes=[{"medicine_id": MEDICINE["medicine_id"], "given": False}],
            )
            assert out["fulfilment"]["status"] == "not_available"

        run_camp(monkeypatch, body)

    def test_the_two_specs_lines_do_not_delete_each_other_and_409_naming_the_other(self, monkeypatch):
        recorder(monkeypatch)

        async def body(database):
            seen = await seen_patient(database)
            specs_day = await _specs_day(database, seen["camp_id"])
            first = await _issue(seen, item_type="specs_fixed", status="fulfilled")
            assert first["fulfilment"]["item_type"] == "specs_fixed"
            with pytest.raises(HTTPException) as exc:
                await _issue(seen, item_type="specs_made", status="deferred", specs_collection_day_id=str(specs_day))
            assert exc.value.status_code == 409
            assert "Fixed-power specs" in exc.value.detail["message"]
            remaining = await database.fulfilments.find({"transcription_id": seen["trans_id"]}).to_list(20)
            assert [f["item_type"] for f in remaining] == ["specs_fixed"]

            await database.fulfilments.delete_many({})
            await _issue(seen, item_type="specs_made", status="deferred", specs_collection_day_id=str(specs_day))
            with pytest.raises(HTTPException) as exc:
                await _issue(seen, item_type="specs_fixed", status="fulfilled")
            assert exc.value.status_code == 409
            assert "Spectacles to be made" in exc.value.detail["message"]
            remaining = await database.fulfilments.find({"transcription_id": seen["trans_id"]}).to_list(20)
            assert [f["item_type"] for f in remaining] == ["specs_made"]
            assert await database.deferred_slips.count_documents({"transcription_id": seen["trans_id"], "active": True}) == 1

        run_camp(monkeypatch, body)

    def test_only_specs_made_and_ot_consume_their_own_seats(self, monkeypatch):
        recorder(monkeypatch)

        async def body(database):
            seen = await seen_patient(database)
            specs_day = await _specs_day(database, seen["camp_id"])
            ot_day = (await database.ot_schedule_days.insert_one({
                "camp_id": seen["camp_id"], "day_date": OTHER_DAY, "venue": "OT Theatre", "seat_limit": 5, "seats_taken": 0,
            })).inserted_id
            await _issue(seen, item_type="specs_fixed", status="fulfilled")
            await _issue(seen, item_type="medicine", status="fulfilled")
            assert (await database.specs_collection_days.find_one({"_id": specs_day}))["seats_taken"] == 0
            assert (await database.ot_schedule_days.find_one({"_id": ot_day}))["seats_taken"] == 0

            await database.fulfilments.delete_many({})
            await _issue(seen, item_type="specs_made", status="deferred", specs_collection_day_id=str(specs_day))
            assert (await database.specs_collection_days.find_one({"_id": specs_day}))["seats_taken"] == 0
            assert (await database.ot_schedule_days.find_one({"_id": ot_day}))["seats_taken"] == 0

            await database.fulfilments.delete_many({})
            await _issue(seen, item_type="ot", status="deferred", ot_schedule_day_id=str(ot_day))
            assert (await database.ot_schedule_days.find_one({"_id": ot_day}))["seats_taken"] == 1

        run_camp(monkeypatch, body)

    def test_missing_powers_refuse_both_specs_lines_and_allow_medicine_and_ot(self, monkeypatch):
        recorder(monkeypatch)

        async def body(database):
            seen = await seen_patient(database, measurements=None, fixed_power=None)
            specs_day = await _specs_day(database, seen["camp_id"])
            ot_day = (await database.ot_schedule_days.insert_one({
                "camp_id": seen["camp_id"], "day_date": TOMORROW, "venue": "OT Theatre", "seat_limit": 2, "seats_taken": 0,
            })).inserted_id
            for item_type, status, extra, code in (
                ("specs_fixed", "fulfilled", {}, "FIXED_POWER_REQUIRED"),
                ("specs_made", "deferred", {"specs_collection_day_id": str(specs_day)}, "SPECS_MEASUREMENTS_REQUIRED"),
            ):
                with pytest.raises(HTTPException) as exc:
                    await _issue(seen, item_type=item_type, status=status, **extra)
                assert exc.value.status_code == 400
                assert exc.value.detail["code"] == code
            med = await _issue(seen, item_type="medicine", status="fulfilled")
            assert med["fulfilment"]["status"] == "fulfilled"
            ot = await _issue(seen, item_type="ot", status="deferred", ot_schedule_day_id=str(ot_day))
            assert ot["fulfilment"]["status"] == "deferred"

        run_camp(monkeypatch, body)

    def test_a_fixed_power_correction_unblocks_specs(self, monkeypatch):
        recorder(monkeypatch)

        async def body(database):
            seen = await seen_patient(database, fixed_power=None)
            with pytest.raises(HTTPException) as exc:
                await _issue(seen, item_type="specs_fixed", status="fulfilled")
            assert exc.value.detail["code"] == "FIXED_POWER_REQUIRED"
            corr = await add_correction(CorrectionBody(
                transcription_id=str(seen["trans_id"]),
                reason="Missed powers",
                changes={"fixed_power_r": FIXED_POWER, "fixed_power_l": FIXED_POWER},
                prescribed_lines=["medicine", "specs_fixed"], ot_outcome=None, ot_eye=None,
                expected_generation=1,
                operation_id="op-corr-powers",
                full_transcription_confirmed=True,
            ), actor=CLINICAL)
            assert (await database.transcriptions.find_one({"_id": seen["trans_id"]}))["fixed_power_r"] == FIXED_POWER
            out = await _issue(
                seen, corr["revision"]["id"], item_type="specs_fixed", status="fulfilled",
                reviewed_generation=corr["registration"]["clinical_generation"],
            )
            assert out["fulfilment"]["item_type"] == "specs_fixed"
            assert out["fulfilment"]["status"] == "fulfilled"

        run_camp(monkeypatch, body)

    def test_export_columns_for_the_two_specs_lines_are_independent(self, monkeypatch):
        recorder(monkeypatch)

        async def body(database):
            camp_id, _ = await seed_camp(database, days=())
            seen = await seen_patient(database, camp_id)
            await _issue(seen, item_type="specs_fixed", status="fulfilled")

            async def csv_rows():
                resp = await export_camp_records(camp_id=str(camp_id), actor=ADMIN)
                chunks = [chunk if isinstance(chunk, str) else chunk.decode() async for chunk in resp.body_iterator]
                return "".join(chunks).strip().splitlines()

            rows = await csv_rows()
            assert "fixed_power_specs,spectacles_to_be_made" in rows[0]
            headers = rows[0].split(",")
            fixed_i = headers.index("fixed_power_specs")
            made_i = headers.index("spectacles_to_be_made")
            data = rows[1].split(",")
            assert data[fixed_i] == "fulfilled"
            assert data[made_i] == ""

            await database.fulfilments.delete_many({})
            specs_day = await _specs_day(database, camp_id)
            await _issue(seen, item_type="specs_made", status="deferred", specs_collection_day_id=str(specs_day))
            data = (await csv_rows())[1].split(",")
            assert data[fixed_i] == ""
            assert data[made_i] == "deferred"

        run_camp(monkeypatch, body)
