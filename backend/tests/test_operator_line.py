"""Operator line, fulfilment matrix, correction, and camp-records export."""
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
os.environ.setdefault("COOKIE_SECURE", "false")

import pytest
from bson import ObjectId
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

import db as db_module
import routes_auth
import routes_clinical
import routes_reports
import routes_staff
import security
import server as server_mod
from models import CorrectionBody, CreateStaffBody, PatchStaffLineBody
from routes_clinical import add_correction, record_fulfilment
from routes_reports import export_camp_records
from routes_staff import create_staff, list_staff, patch_staff_line
from test_adversarial_challenger import setup_mock_db
from test_camp_lifecycle import (
    FIXED_POWER, MEDICINE, RX, _fulfil, _mock, _recorder, _seen_patient_with_transcription,
)

PASS = "ClinicLine1!"
ADMIN = {"_id": ObjectId(), "role": "admin"}
CLINICAL = {"_id": ObjectId(), "role": "clinical_desk_operator"}
LINES = ("rx", "medicine", "specs_fixed", "specs_made", "ot")


def _async_noop():
    async def _inner(*_a, **_k):
        return None
    return _inner


def _patch_db(monkeypatch, mock_db):
    mock_db = mock_db or setup_mock_db(monkeypatch)
    for mod in (db_module, routes_staff, routes_auth, routes_clinical, routes_reports, security):
        monkeypatch.setattr(mod, "get_db", lambda: mock_db)
    return mock_db


def _client(monkeypatch, mock_db):
    monkeypatch.setattr(server_mod, "init_indexes", _async_noop())
    monkeypatch.setattr(server_mod, "seed_admin", _async_noop())
    _patch_db(monkeypatch, mock_db)
    server_mod.app.router.on_startup.clear()
    return TestClient(server_mod.app, raise_server_exceptions=True)


class TestOperatorLine:
    def test_each_of_the_five_lines_is_accepted_on_a_clinical_account(self, monkeypatch):
        async def run():
            _patch_db(monkeypatch, setup_mock_db(monkeypatch))
            for line in LINES:
                out = await create_staff(CreateStaffBody(
                    email=f"{line}@snpcamps.org", password=PASS, name=line,
                    role="clinical_desk_operator", line=line,
                ), actor=ADMIN)
                assert out["staff"]["line"] == line
                assert out["staff"]["role"] == "clinical_desk_operator"
        asyncio.run(run())

    def test_an_out_of_vocabulary_line_is_refused(self, monkeypatch):
        async def run():
            _patch_db(monkeypatch, setup_mock_db(monkeypatch))
            with pytest.raises(HTTPException) as exc:
                await create_staff(CreateStaffBody(
                    email="bad@snpcamps.org", password=PASS, name="Bad",
                    role="clinical_desk_operator", line="pharmacy",
                ), actor=ADMIN)
            assert exc.value.status_code == 400
        asyncio.run(run())

    def test_a_line_on_a_non_clinical_role_is_stored_as_null(self, monkeypatch):
        async def run():
            mock_db = _patch_db(monkeypatch, setup_mock_db(monkeypatch))
            out = await create_staff(CreateStaffBody(
                name="Vol", role="volunteer", line="medicine",
            ), actor=ADMIN)
            assert out["staff"]["line"] is None
            stored = await mock_db.users.find_one({"_id": ObjectId(out["staff"]["id"])})
            assert stored["line"] is None
        asyncio.run(run())

    def test_patch_accepts_only_line_including_null(self, monkeypatch):
        async def run():
            mock_db = _patch_db(monkeypatch, setup_mock_db(monkeypatch))
            created = await create_staff(CreateStaffBody(
                email="op@snpcamps.org", password=PASS, name="Op",
                role="clinical_desk_operator", line="rx",
            ), actor=ADMIN)
            sid = created["staff"]["id"]
            patched = await patch_staff_line(sid, PatchStaffLineBody(line="ot"), actor=ADMIN)
            assert patched["staff"]["line"] == "ot"
            cleared = await patch_staff_line(sid, PatchStaffLineBody(line=None), actor=ADMIN)
            assert cleared["staff"]["line"] is None
            stored = await mock_db.users.find_one({"_id": ObjectId(sid)})
            assert stored["line"] is None
        asyncio.run(run())

    def test_patch_refuses_a_non_admin(self, monkeypatch):
        async def run():
            mock_db = _patch_db(monkeypatch, setup_mock_db(monkeypatch))
            created = await create_staff(CreateStaffBody(
                email="op@snpcamps.org", password=PASS, name="Op",
                role="clinical_desk_operator", line="rx",
            ), actor=ADMIN)
            client = _client(monkeypatch, mock_db)
            token = security.create_access_token(str(CLINICAL["_id"]), "Clin")
            await mock_db.users.insert_one({
                "_id": CLINICAL["_id"], "name": "Clin", "name_normalized": "clin",
                "pin_hash": security.hash_pin("1234"),
                "role": "clinical_desk_operator", "line": "rx", "disabled_at": None,
            })
            r = client.patch(
                f"/api/staff/{created['staff']['id']}",
                json={"line": "ot"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 403
        asyncio.run(run())

    def test_patch_refuses_any_field_other_than_line(self):
        with pytest.raises(ValidationError):
            PatchStaffLineBody(line="rx", name="nope")
        with pytest.raises(ValidationError):
            PatchStaffLineBody(line="rx", role="admin")

    def test_listing_and_login_carry_line(self, monkeypatch):
        async def run():
            mock_db = _patch_db(monkeypatch, setup_mock_db(monkeypatch))
            await create_staff(CreateStaffBody(
                name="Med", role="clinical_desk_operator", line="medicine",
            ), actor=ADMIN)
            listed = await list_staff(actor=ADMIN)
            row = next(s for s in listed["staff"] if s["name"] == "Med")
            assert row["line"] == "medicine"
            client = _client(monkeypatch, mock_db)
            r = client.post("/api/auth/login", json={"name": "Med", "pin": "1234"})
            assert r.status_code == 200, r.text
            assert r.json()["user"]["line"] == "medicine"
        asyncio.run(run())


class TestFulfilmentMatrix:
    def test_each_item_type_accepts_only_its_matrix(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _recorder(monkeypatch)
            _camp, _pid, trans_id = await _seen_patient_with_transcription(
                mock_db, RX, fixed_power=FIXED_POWER,
            )
            allowed = [
                ("medicine", "fulfilled"),
                ("medicine", "not_available"),
                ("specs_fixed", "fulfilled"),
            ]
            for item_type, status in allowed:
                out = await record_fulfilment(
                    _fulfil(trans_id, mock_db.last_rev_id, item_type=item_type, status=status),
                    actor=CLINICAL,
                 background_tasks=None)
                assert out["fulfilment"]["item_type"] == item_type
                assert out["fulfilment"]["status"] == status
            refused = [
                ("specs_fixed", "deferred"),
                ("specs_fixed", "not_available"),
                ("specs_made", "fulfilled"),
                ("ot", "not_available"),
                ("ot", "fulfilled"),
                ("specs", "fulfilled"),
            ]
            for item_type, status in refused:
                with pytest.raises(HTTPException) as exc:
                    await record_fulfilment(
                        _fulfil(trans_id, mock_db.last_rev_id, item_type=item_type, status=status),
                        actor=CLINICAL,
                     background_tasks=None)
                assert exc.value.status_code == 400
        asyncio.run(run())

    def test_not_required_is_refused_for_every_type(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _camp, _pid, trans_id = await _seen_patient_with_transcription(
                mock_db, RX, fixed_power=FIXED_POWER,
            )
            for item_type in ("specs_fixed", "specs_made", "ot"):
                with pytest.raises(HTTPException) as exc:
                    await record_fulfilment(
                        _fulfil(trans_id, mock_db.last_rev_id, item_type=item_type, status="not_required"),
                        actor=CLINICAL,
                     background_tasks=None)
                assert exc.value.status_code == 400
        asyncio.run(run())

    def test_the_medicine_line_status_comes_from_the_outcomes_not_the_body(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _camp, _pid, trans_id = await _seen_patient_with_transcription(mock_db, RX)
            out = await record_fulfilment(_fulfil(
                trans_id, mock_db.last_rev_id, item_type="medicine", status="not_required",
                medicine_outcomes=[{"medicine_id": MEDICINE["medicine_id"], "given": False}],
            ), actor=CLINICAL, background_tasks=None)
            assert out["fulfilment"]["status"] == "not_available"
        asyncio.run(run())

    def test_the_two_specs_lines_do_not_delete_each_other_and_409_naming_the_other(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _recorder(monkeypatch)
            camp_id, _pid, trans_id = await _seen_patient_with_transcription(
                mock_db, RX, fixed_power=FIXED_POWER,
            )
            specs_day = ObjectId()
            await mock_db.specs_collection_days.insert_one({
                "_id": specs_day, "camp_id": camp_id, "day_date": "2026-09-20",
                "venue": "Optical Desk", "start_time": "10:00", "end_time": "17:00", "seat_limit": 2, "seats_taken": 0,
            })
            first = await record_fulfilment(
                _fulfil(trans_id, mock_db.last_rev_id, item_type="specs_fixed", status="fulfilled"),
                actor=CLINICAL,
             background_tasks=None)
            assert first["fulfilment"]["item_type"] == "specs_fixed"
            with pytest.raises(HTTPException) as exc:
                await record_fulfilment(
                    _fulfil(trans_id, mock_db.last_rev_id, item_type="specs_made", status="deferred",
                            specs_collection_day_id=str(specs_day)),
                    actor=CLINICAL,
                 background_tasks=None)
            assert exc.value.status_code == 409
            assert "Fixed-power specs" in exc.value.detail["message"]
            remaining = await mock_db.fulfilments.find({"transcription_id": trans_id}).to_list(20)
            assert [f["item_type"] for f in remaining] == ["specs_fixed"]

            mock_db.fulfilments.docs.clear()
            await record_fulfilment(
                _fulfil(trans_id, mock_db.last_rev_id, item_type="specs_made", status="deferred",
                        specs_collection_day_id=str(specs_day)),
                actor=CLINICAL,
             background_tasks=None)
            with pytest.raises(HTTPException) as exc:
                await record_fulfilment(
                    _fulfil(trans_id, mock_db.last_rev_id, item_type="specs_fixed", status="fulfilled"),
                    actor=CLINICAL,
                 background_tasks=None)
            assert exc.value.status_code == 409
            assert "Spectacles to be made" in exc.value.detail["message"]
            remaining = await mock_db.fulfilments.find({"transcription_id": trans_id}).to_list(20)
            assert [f["item_type"] for f in remaining] == ["specs_made"]
        asyncio.run(run())

    def test_only_specs_made_and_ot_consume_their_own_seats(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _recorder(monkeypatch)
            camp_id, _pid, trans_id = await _seen_patient_with_transcription(
                mock_db, RX, fixed_power=FIXED_POWER,
            )
            specs_day, ot_day = ObjectId(), ObjectId()
            await mock_db.specs_collection_days.insert_one({
                "_id": specs_day, "camp_id": camp_id, "day_date": "2026-09-20",
                "venue": "Optical Desk", "start_time": "10:00", "end_time": "17:00", "seat_limit": 5, "seats_taken": 0,
            })
            await mock_db.ot_schedule_days.insert_one({
                "_id": ot_day, "camp_id": camp_id, "day_date": "2026-10-02",
                "venue": "OT Theatre", "seat_limit": 5, "seats_taken": 0,
            })
            await record_fulfilment(
                _fulfil(trans_id, mock_db.last_rev_id, item_type="specs_fixed", status="fulfilled"),
                actor=CLINICAL,
             background_tasks=None)
            await record_fulfilment(
                _fulfil(trans_id, mock_db.last_rev_id, item_type="medicine", status="fulfilled"),
                actor=CLINICAL,
             background_tasks=None)
            assert (await mock_db.specs_collection_days.find_one({"_id": specs_day}))["seats_taken"] == 0
            assert (await mock_db.ot_schedule_days.find_one({"_id": ot_day}))["seats_taken"] == 0

            mock_db.fulfilments.docs.clear()
            await record_fulfilment(
                _fulfil(trans_id, mock_db.last_rev_id, item_type="specs_made", status="deferred",
                        specs_collection_day_id=str(specs_day)),
                actor=CLINICAL,
             background_tasks=None)
            assert (await mock_db.specs_collection_days.find_one({"_id": specs_day})).get("seats_taken") in (None, 0)
            assert (await mock_db.ot_schedule_days.find_one({"_id": ot_day}))["seats_taken"] == 0

            mock_db.fulfilments.docs.clear()
            await record_fulfilment(
                _fulfil(trans_id, mock_db.last_rev_id, item_type="ot", status="deferred",
                        ot_schedule_day_id=str(ot_day)),
                actor=CLINICAL,
             background_tasks=None)
            assert (await mock_db.ot_schedule_days.find_one({"_id": ot_day}))["seats_taken"] == 1
        asyncio.run(run())

    def test_missing_powers_refuse_both_specs_lines_and_allow_medicine_and_ot(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _recorder(monkeypatch)
            camp_id, _pid, trans_id = await _seen_patient_with_transcription(mock_db)
            specs_day, ot_day = ObjectId(), ObjectId()
            await mock_db.specs_collection_days.insert_one({
                "_id": specs_day, "camp_id": camp_id, "day_date": "2026-09-20",
                "venue": "Optical Desk", "start_time": "10:00", "end_time": "17:00", "seat_limit": 2, "seats_taken": 0,
            })
            await mock_db.ot_schedule_days.insert_one({
                "_id": ot_day, "camp_id": camp_id, "day_date": "2026-10-02",
                "venue": "OT Theatre", "seat_limit": 2, "seats_taken": 0,
            })
            for item_type, status, extra, code in (
                ("specs_fixed", "fulfilled", {}, "FIXED_POWER_REQUIRED"),
                ("specs_made", "deferred",
                 {"specs_collection_day_id": str(specs_day)}, "SPECS_MEASUREMENTS_REQUIRED"),
            ):
                with pytest.raises(HTTPException) as exc:
                    await record_fulfilment(
                        _fulfil(trans_id, mock_db.last_rev_id, item_type=item_type, status=status, **extra),
                        actor=CLINICAL,
                     background_tasks=None)
                assert exc.value.status_code == 400
                assert exc.value.detail["code"] == code
            med = await record_fulfilment(
                _fulfil(trans_id, mock_db.last_rev_id, item_type="medicine", status="fulfilled"),
                actor=CLINICAL,
             background_tasks=None)
            assert med["fulfilment"]["status"] == "fulfilled"
            ot = await record_fulfilment(
                _fulfil(trans_id, mock_db.last_rev_id, item_type="ot", status="deferred",
                        ot_schedule_day_id=str(ot_day)),
                actor=CLINICAL,
             background_tasks=None)
            assert ot["fulfilment"]["status"] == "deferred"
        asyncio.run(run())

    def test_a_fixed_power_correction_unblocks_specs(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _recorder(monkeypatch)
            _camp, _pid, trans_id = await _seen_patient_with_transcription(mock_db, RX)
            body = _fulfil(trans_id, mock_db.last_rev_id, item_type="specs_fixed", status="fulfilled")
            with pytest.raises(HTTPException) as exc:
                await record_fulfilment(body, actor=CLINICAL, background_tasks=None)
            assert exc.value.detail["code"] == "FIXED_POWER_REQUIRED"
            corr = await add_correction(CorrectionBody(
                transcription_id=str(trans_id),
                reason="Missed powers",
                changes={"fixed_power_r": FIXED_POWER, "fixed_power_l": FIXED_POWER},
                prescribed_lines=["medicine", "specs_fixed"], ot_outcome=None, ot_eye=None,
                expected_generation=1,
                operation_id="op-corr-powers",
                full_transcription_confirmed=True,
            ), actor=CLINICAL)
            t = await mock_db.transcriptions.find_one({"_id": trans_id})
            assert t["fixed_power_r"] == FIXED_POWER
            body = _fulfil(
                trans_id, corr["revision"]["id"], item_type="specs_fixed", status="fulfilled",
                reviewed_generation=corr["registration"]["clinical_generation"],
            )
            out = await record_fulfilment(body, actor=CLINICAL, background_tasks=None)
            assert out["fulfilment"]["item_type"] == "specs_fixed"
            assert out["fulfilment"]["status"] == "fulfilled"
        asyncio.run(run())

    def test_export_columns_for_the_two_specs_lines_are_independent(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            _recorder(monkeypatch)
            camp_id, _pid, trans_id = await _seen_patient_with_transcription(
                mock_db, RX, fixed_power=FIXED_POWER,
            )
            await mock_db.camps.insert_one({"_id": camp_id, "name": "C", "venue": "Hall", "is_active": True})
            await record_fulfilment(
                _fulfil(trans_id, mock_db.last_rev_id, item_type="specs_fixed", status="fulfilled"),
                actor=CLINICAL,
             background_tasks=None)
            monkeypatch.setattr(routes_reports, "get_db", lambda: mock_db)
            async def csv_text():
                resp = await export_camp_records(camp_id=str(camp_id), actor=ADMIN)
                chunks = []
                async for chunk in resp.body_iterator:
                    chunks.append(chunk if isinstance(chunk, str) else chunk.decode())
                return "".join(chunks)

            text = await csv_text()
            rows = text.strip().splitlines()
            assert "fixed_power_specs,spectacles_to_be_made" in rows[0]
            data = rows[1].split(",")
            headers = rows[0].split(",")
            fixed_i = headers.index("fixed_power_specs")
            made_i = headers.index("spectacles_to_be_made")
            assert data[fixed_i] == "fulfilled"
            assert data[made_i] == ""

            mock_db.fulfilments.docs.clear()
            specs_day = ObjectId()
            await mock_db.specs_collection_days.insert_one({
                "_id": specs_day, "camp_id": camp_id, "day_date": "2026-09-20",
                "venue": "Optical Desk", "start_time": "10:00", "end_time": "17:00", "seat_limit": 2, "seats_taken": 0,
            })
            await record_fulfilment(
                _fulfil(trans_id, mock_db.last_rev_id, item_type="specs_made", status="deferred",
                        specs_collection_day_id=str(specs_day)),
                actor=CLINICAL,
             background_tasks=None)
            text = await csv_text()
            data = text.strip().splitlines()[1].split(",")
            assert data[fixed_i] == ""
            assert data[made_i] == "deferred"
        asyncio.run(run())
