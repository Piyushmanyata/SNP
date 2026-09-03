"""Empirical Adversarial Stress Harness for SNP Camps Backend.

Exhaustively stress-tests:
1. Registration conflict resolution, race conditions, capacity limits, and manual overwrite invariants.
2. Duplicate detection heuristics, boundary cases, phonetics, and phone/name normalization.
3. Fulfilment status transitions, state machine enforcement, deferral seat accounting under extreme concurrency.
4. Secure QR decoding robustness against fuzzed payloads, malformed delimiters, XML injection, and varied date/gender encodings.
"""
import sys
import os
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

os.environ["MONGO_URL"] = "mongodb://localhost:27017"
os.environ["DB_NAME"] = "snp_stress_test"

import pytest
import io
import gzip
import zlib
import asyncio
import copy
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from bson import ObjectId
from fastapi import HTTPException, Request

from aadhaar import (
    parse_xml_qr,
    decode_aadhaar,
    parse_secure_qr,
    _to_iso_dob,
    _calc_age,
    _normalize_gender,
    _clean_date_string,
    _decompress,
    _extract_delimited_segments,
    FIELDS,
)
from models import RegisterBody, FulfilmentBody, CorrectionBody
import routes_registration
import routes_clinical
import routes_desk
from routes_registration import (
    _create_registration,
    _check_registration_duplicates,
    _resolve_person,
    _validate_camp_and_day,
    _build_patient_document,
    _build_duplicate_queries,
    _duplicate_hits,
    _resolve_registration_conflict,
    _overwrite_manual,
    _assert_capacity,
)
from routes_clinical import (
    record_fulfilment,
    _validate_fulfilment_matrix,
    _process_deferral,
    _cleanup_prior_fulfilment,
    _make_slip,
    add_correction,
)
from routes_desk import (
    mark_seen,
    undo_seen,
)
from helpers import (
    normalize_name,
    normalize_phone,
    is_dummy_phone,
    person_key,
    now_utc,
    age_from_dob,
)
import db as db_module


# =====================================================================
# DETERMINISTIC ASYNC MONGO REPLICA FOR STRESS & CONCURRENCY
# =====================================================================

RX = {"r_sph": "-1.00", "l_sph": "-1.25", "add": "+2.00"}

class MockCursor:
    def __init__(self, docs):
        self._docs = [copy.deepcopy(d) for d in docs]

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    def sort(self, key, direction=1):
        if isinstance(key, list):
            for k, d in reversed(key):
                self._docs.sort(key=lambda x: x.get(k, ""), reverse=(d == -1))
        else:
            self._docs.sort(key=lambda x: x.get(key, ""), reverse=(direction == -1))
        return self

    async def to_list(self, length=None):
        if length is not None:
            return self._docs[:length]
        return self._docs


class MockCollection:
    def __init__(self, name, db):
        self.name = name
        self.db = db
        self.docs = []
        self._lock = asyncio.Lock()

    def _matches(self, doc, query):
        for k, v in query.items():
            if k == "_id":
                if doc.get("_id") != v:
                    return False
            elif k == "$expr":
                for op, args in v.items():
                    if op == "$lt":
                        f1, f2 = args
                        k1 = f1.replace("$", "")
                        k2 = f2.replace("$", "")
                        v1 = doc.get(k1, 0)
                        v2 = doc.get(k2, 0)
                        if not (v1 < v2):
                            return False
            elif k == "seats_taken":
                if isinstance(v, dict) and "$gt" in v:
                    if not (doc.get("seats_taken", 0) > v["$gt"]):
                        return False
                elif doc.get(k) != v:
                    return False
            elif isinstance(v, dict):
                # Handle basic Mongo operators like $in, $ne
                if "$in" in v:
                    if doc.get(k) not in v["$in"]:
                        return False
                elif "$ne" in v:
                    if doc.get(k) == v["$ne"]:
                        return False
                elif doc.get(k) != v:
                    return False
            else:
                if doc.get(k) != v:
                    return False
        return True

    async def find_one(self, query):
        async with self._lock:
            for d in self.docs:
                if self._matches(d, query):
                    return copy.deepcopy(d)
            return None

    def find(self, query=None):
        query = query or {}
        matched = [d for d in self.docs if self._matches(d, query)]
        return MockCursor(matched)

    async def insert_one(self, doc):
        async with self._lock:
            new_doc = copy.deepcopy(doc)
            if "_id" not in new_doc:
                new_doc["_id"] = ObjectId()
            self.docs.append(new_doc)
            class InsertResult:
                def __init__(self, inserted_id):
                    self.inserted_id = inserted_id
            return InsertResult(new_doc["_id"])

    async def update_one(self, query, update):
        async with self._lock:
            for d in self.docs:
                if self._matches(d, query):
                    self._apply_update(d, update)
                    return True
            return False

    async def update_many(self, query, update):
        async with self._lock:
            count = 0
            for d in self.docs:
                if self._matches(d, query):
                    self._apply_update(d, update)
                    count += 1
            return count

    async def find_one_and_update(self, query, update, upsert=False, return_document=False):
        async with self._lock:
            for d in self.docs:
                if self._matches(d, query):
                    old_doc = copy.deepcopy(d)
                    self._apply_update(d, update)
                    return copy.deepcopy(d) if return_document else old_doc
            if upsert:
                new_doc = {"_id": query.get("_id", ObjectId())}
                for k, v in query.items():
                    if k != "_id":
                        new_doc[k] = v
                self._apply_update(new_doc, update)
                self.docs.append(new_doc)
                return copy.deepcopy(new_doc)
            return None

    async def delete_many(self, query):
        async with self._lock:
            orig_len = len(self.docs)
            self.docs = [d for d in self.docs if not self._matches(d, query)]
            return orig_len - len(self.docs)

    async def count_documents(self, query):
        async with self._lock:
            return sum(1 for d in self.docs if self._matches(d, query))

    def _apply_update(self, doc, update):
        if "$set" in update:
            for k, v in update["$set"].items():
                doc[k] = copy.deepcopy(v)
        if "$inc" in update:
            for k, v in update["$inc"].items():
                doc[k] = doc.get(k, 0) + v


class MockDB:
    def __init__(self):
        self.collections = {}
        self._seqs = {}
        self._lock = asyncio.Lock()

    def __getattr__(self, name):
        if name not in self.collections:
            self.collections[name] = MockCollection(name, self)
        return self.collections[name]

    async def next_seq(self, name: str) -> int:
        async with self._lock:
            self._seqs[name] = self._seqs.get(name, 0) + 1
            return self._seqs[name]


def setup_stress_db(monkeypatch):
    mock_db = MockDB()
    monkeypatch.setattr(db_module, "get_db", lambda: mock_db)
    monkeypatch.setattr(routes_registration, "get_db", lambda: mock_db)
    monkeypatch.setattr(routes_clinical, "get_db", lambda: mock_db)
    monkeypatch.setattr(routes_desk, "get_db", lambda: mock_db)
    monkeypatch.setattr(routes_registration, "next_seq", mock_db.next_seq)
    monkeypatch.setattr(db_module, "next_seq", mock_db.next_seq)
    return mock_db


async def seed_active_camp(mock_db, seat_limit=50):
    camp_id = ObjectId()
    day_id = ObjectId()
    await mock_db.camps.insert_one({"_id": camp_id, "name": "Active Stress Camp", "is_active": True})
    await mock_db.camp_days.insert_one({
        "_id": day_id,
        "camp_id": camp_id,
        "day_date": "2026-09-01",
        "seat_limit": seat_limit,
        "printing_open": True,
    })
    return camp_id, day_id


# =====================================================================
# 1. REGISTRATION CONFLICT & OVERWRITE RESOLUTION STRESS
# =====================================================================

class TestRegistrationConflictAndOverwriteStress:
    def test_overwrite_manual_preserves_reg_no_and_updates_card_data(self, monkeypatch):
        """Scanned Aadhaar registering over an existing manual entry must preserve reg_no and update details."""
        async def _run():
            mock_db = setup_stress_db(monkeypatch)
            camp_id, day_id = await seed_active_camp(mock_db)

            # 1. Create a manual entry first
            manual_body = RegisterBody(
                camp_day_id=str(day_id),
                full_name="Prakash Sharma",
                phone="9876500001",
                age=45,
                gender="M",
                manual_entry=True,
                aadhaar_last4="1234",
                dob="1981-05-10",
            )
            reg_manual, created = await _create_registration(manual_body, actor_id=ObjectId(), is_self=False, request=None)
            assert created is True
            assert reg_manual["reg_no"] == 1
            assert reg_manual["manual_entry"] is True
            assert reg_manual["aadhaar_scanned"] is False

            # 2. Scanned card with matching aadhaar_last4 and DOB arrives at desk
            scanned_body = RegisterBody(
                camp_day_id=str(day_id),
                full_name="Prakash K. Sharma",
                phone="9876500001",
                age=45,
                gender="M",
                dob="1981-05-10",
                aadhaar_last4="1234",
                aadhaar_scanned=True,
            )
            reg_scanned, created2 = await _create_registration(scanned_body, actor_id=ObjectId(), is_self=False, request=None)
            assert created2 is False, "Overwrite must update in-place without creating second registration"
            assert reg_scanned["reg_no"] == 1, "Must preserve original registration number"
            assert reg_scanned["full_name"] == "Prakash K. Sharma"
            assert reg_scanned["aadhaar_scanned"] is True
            assert reg_scanned["manual_entry"] is False
            assert len(mock_db.patients.docs) == 1, "Must not create extra patient row"

        asyncio.run(_run())

    def test_ambiguous_manual_entries_rejects_with_409_listing_both(self, monkeypatch):
        """If multiple manual entries match the scanned card, system must reject with AMBIGUOUS_MANUAL_ENTRY."""
        async def _run():
            mock_db = setup_stress_db(monkeypatch)
            camp_id, day_id = await seed_active_camp(mock_db)

            # Insert two distinct manual patients with same aadhaar_last4 and normalized name
            p1_id = ObjectId()
            p2_id = ObjectId()
            await mock_db.patients.insert_one({
                "_id": p1_id,
                "camp_id": camp_id,
                "camp_day_id": day_id,
                "reg_no": 1,
                "full_name": "Ramesh Kumar",
                "full_name_normalized": "ramesh kumar",
                "aadhaar_last4": "5555",
                "dob": "1980-01-01",
                "manual_entry": True,
                "aadhaar_scanned": False,
                "queue_status": "registered",
            })
            await mock_db.patients.insert_one({
                "_id": p2_id,
                "camp_id": camp_id,
                "camp_day_id": day_id,
                "reg_no": 2,
                "full_name": "Ramesh Kumar",
                "full_name_normalized": "ramesh kumar",
                "aadhaar_last4": "5555",
                "dob": "1980-01-01",
                "manual_entry": True,
                "aadhaar_scanned": False,
                "queue_status": "registered",
            })

            # Desk card scan arrives matching both
            scanned_body = RegisterBody(
                camp_day_id=str(day_id),
                full_name="Ramesh Kumar",
                phone="9876500002",
                dob="1980-01-01",
                aadhaar_last4="5555",
                aadhaar_scanned=True,
            )
            with pytest.raises(HTTPException) as exc:
                await _create_registration(scanned_body, actor_id=ObjectId(), is_self=False, request=None)
            assert exc.value.status_code == 409
            assert exc.value.detail["code"] == "AMBIGUOUS_MANUAL_ENTRY"
            assert len(exc.value.detail["registrations"]) == 2

        asyncio.run(_run())

    def test_self_register_cannot_overwrite_manual_entry(self, monkeypatch):
        """Self-registration matching a manual entry must NOT overwrite it; it must reject with DUPLICATE_IN_CAMP."""
        async def _run():
            mock_db = setup_stress_db(monkeypatch)
            camp_id, day_id = await seed_active_camp(mock_db)

            # Manual entry by desk
            p_id = ObjectId()
            await mock_db.patients.insert_one({
                "_id": p_id,
                "camp_id": camp_id,
                "camp_day_id": day_id,
                "reg_no": 10,
                "full_name": "Kavita Singh",
                "full_name_normalized": "kavita singh",
                "aadhaar_last4": "7777",
                "dob": "1990-03-15",
                "manual_entry": True,
                "aadhaar_scanned": False,
                "queue_status": "registered",
            })

            # Online / Self-register attempt with scanned Aadhaar
            self_body = RegisterBody(
                camp_day_id=str(day_id),
                full_name="Kavita Singh",
                dob="1990-03-15",
                aadhaar_last4="7777",
                aadhaar_scanned=True,
            )
            with pytest.raises(HTTPException) as exc:
                await _create_registration(self_body, actor_id=None, is_self=True, request=None)
            assert exc.value.status_code == 409
            assert exc.value.detail["code"] == "DUPLICATE_IN_CAMP"
            # Verify patient record was not altered
            doc = await mock_db.patients.find_one({"_id": p_id})
            assert doc["manual_entry"] is True
            assert doc["aadhaar_scanned"] is False

        asyncio.run(_run())

    def test_full_capacity_camp_day_blocks_new_registration(self, monkeypatch):
        """When seat_limit is reached, new registrations are rejected with CAMP_DAY_FULL."""
        async def _run():
            mock_db = setup_stress_db(monkeypatch)
            camp_id, day_id = await seed_active_camp(mock_db, seat_limit=2)

            # Fill 2 seats
            for i in range(1, 3):
                body = RegisterBody(
                    camp_day_id=str(day_id),
                    full_name=f"Patient {i}",
                    phone=f"987650000{i}",
                    age=30 + i,
                )
                await _create_registration(body, actor_id=ObjectId(), is_self=False, request=None)

            # 3rd registration must fail
            body3 = RegisterBody(
                camp_day_id=str(day_id),
                full_name="Patient 3",
                phone="9876500003",
                age=33,
            )
            with pytest.raises(HTTPException) as exc:
                await _create_registration(body3, actor_id=ObjectId(), is_self=False, request=None)
            assert exc.value.status_code == 409
            assert exc.value.detail["code"] == "CAMP_DAY_FULL"

        asyncio.run(_run())

    def test_overwrite_manual_on_full_day_succeeds_without_overbooking(self, monkeypatch):
        """Overwriting an existing manual registration on a full camp day must succeed because no new seat is consumed."""
        async def _run():
            mock_db = setup_stress_db(monkeypatch)
            camp_id, day_id = await seed_active_camp(mock_db, seat_limit=1)

            # Create 1 manual entry (capacity now at 1/1)
            manual_body = RegisterBody(
                camp_day_id=str(day_id),
                full_name="Sunil Dutt",
                phone="9876500010",
                age=50,
                aadhaar_last4="9999",
                dob="1976-08-20",
                manual_entry=True,
            )
            await _create_registration(manual_body, actor_id=ObjectId(), is_self=False, request=None)

            # Overwrite via scanned Aadhaar card
            scanned_body = RegisterBody(
                camp_day_id=str(day_id),
                full_name="Sunil Dutt",
                phone="9876500010",
                aadhaar_last4="9999",
                dob="1976-08-20",
                aadhaar_scanned=True,
            )
            reg, created = await _create_registration(scanned_body, actor_id=ObjectId(), is_self=False, request=None)
            assert created is False
            assert reg["aadhaar_scanned"] is True
            assert reg["manual_entry"] is False
            assert len(mock_db.patients.docs) == 1

        asyncio.run(_run())


# =====================================================================
# 2. DUPLICATE DETECTION HEURISTICS & NORMALIZATION BOUNDARIES
# =====================================================================

class TestDuplicateDetectionHeuristicsStress:
    def test_phone_normalization_variations(self):
        """Test varied Indian phone input formats are normalized to 10 digits."""
        assert normalize_phone("+919876543210") == "9876543210"
        assert normalize_phone("+91-98765-43210") == "9876543210"
        assert normalize_phone("09876543210") == "9876543210"
        assert normalize_phone("98765 43210") == "9876543210"
        assert normalize_phone("98765-43210") == "9876543210"
        assert normalize_phone("(+91) 9876543210") == "9876543210"
        assert normalize_phone("98765") == "98765"
        assert normalize_phone("") is None
        assert normalize_phone(None) is None

    def test_dummy_phone_detection_exhaustive(self):
        """Ensure dummy / test phone patterns are properly flagged."""
        assert is_dummy_phone("9999999999") is True
        assert is_dummy_phone("0000000000") is True
        assert is_dummy_phone("1111111111") is True
        assert is_dummy_phone("12345") is True  # short phone rejected
        assert is_dummy_phone("") is True
        assert is_dummy_phone("9876543210") is False
        assert is_dummy_phone("9811223344") is False

    def test_name_normalization_diacritics_and_whitespace(self):
        """Name normalization strips leading/trailing spaces, collapses multi-spaces, lowercases, removes punctuation."""
        assert normalize_name("  Ravi   Kumar  ") == "ravi kumar"
        assert normalize_name("DR.  ANITA   DESHMUKH") == "dr anita deshmukh"
        assert normalize_name("O'Connor-Smith") == "oconnorsmith"
        assert normalize_name("   ") == ""
        assert normalize_name(None) == ""

    def test_duplicate_matching_phone_name_age_match(self, monkeypatch):
        """Match by (full_name_normalized, age, phone_normalized) triggers duplicate."""
        async def _run():
            mock_db = setup_stress_db(monkeypatch)
            camp_id, day_id = await seed_active_camp(mock_db)

            body1 = RegisterBody(
                camp_day_id=str(day_id),
                full_name="Deepak Verma",
                phone="9876512345",
                age=38,
            )
            await _create_registration(body1, actor_id=ObjectId(), is_self=False, request=None)

            body2 = RegisterBody(
                camp_day_id=str(day_id),
                full_name="  deepak   verma  ",
                phone="+91-98765-12345",
                age=38,
            )
            with pytest.raises(HTTPException) as exc:
                await _create_registration(body2, actor_id=ObjectId(), is_self=False, request=None)
            assert exc.value.status_code == 409
            assert exc.value.detail["code"] == "DUPLICATE_IN_CAMP"

        asyncio.run(_run())

    def test_same_phone_different_person_allowed(self, monkeypatch):
        """Same household phone with different family member name/age is NOT hard-blocked."""
        async def _run():
            mock_db = setup_stress_db(monkeypatch)
            camp_id, day_id = await seed_active_camp(mock_db)

            # Husband
            b1 = RegisterBody(
                camp_day_id=str(day_id),
                full_name="Sanjay Patel",
                phone="9876500099",
                age=45,
            )
            p1, c1 = await _create_registration(b1, actor_id=ObjectId(), is_self=False, request=None)
            assert c1 is True

            # Wife (same phone, different name & age)
            b2 = RegisterBody(
                camp_day_id=str(day_id),
                full_name="Meena Patel",
                phone="9876500099",
                age=42,
            )
            p2, c2 = await _create_registration(b2, actor_id=ObjectId(), is_self=False, request=None)
            assert c2 is True
            assert p2["reg_no"] == 2
            assert len(mock_db.patients.docs) == 2

        asyncio.run(_run())


# =====================================================================
# 3. FULFILMENT STATUS TRANSITIONS & DESK STATE MACHINE INTEGRITY
# =====================================================================

class TestFulfilmentStateMachineAndDeskStress:
    def test_desk_actions_state_progression_invariants(self, monkeypatch):
        """Desk flow: Registered -> Arrived -> Printed Rx -> Mark Seen -> Undo Seen rules."""
        async def _run():
            mock_db = setup_stress_db(monkeypatch)
            camp_id, day_id = await seed_active_camp(mock_db)

            # 1. Register patient
            p_id = ObjectId()
            await mock_db.patients.insert_one({
                "_id": p_id,
                "camp_id": camp_id,
                "camp_day_id": day_id,
                "reg_no": 5,
                "full_name": "Test Patient",
                "queue_status": "registered",
                "printed_at": None,
                "seen_at": None,
            })

            # 2. Mark seen fails before Arrival
            with pytest.raises(HTTPException) as exc:
                await mark_seen(str(p_id), actor={"_id": ObjectId(), "role": "volunteer"})
            assert exc.value.status_code == 409
            assert exc.value.detail["code"] == "NOT_ARRIVED"

            # 3. Arrival, then mark seen still fails if never printed
            await mock_db.patients.update_one(
                {"_id": p_id}, {"$set": {"arrived_at": now_utc(), "queue_status": "arrived"}}
            )
            with pytest.raises(HTTPException) as exc:
                await mark_seen(str(p_id), actor={"_id": ObjectId(), "role": "volunteer"})
            assert exc.value.status_code == 409
            assert exc.value.detail["code"] == "never_printed"

            # 4. Simulate Print Rx (sets printed_at)
            await mock_db.patients.update_one({"_id": p_id}, {"$set": {"printed_at": now_utc()}})

            # 5. Mark Seen succeeds
            res_seen = await mark_seen(str(p_id), actor={"_id": ObjectId(), "role": "volunteer"})
            assert res_seen["registration"]["queue_status"] == "seen"
            assert res_seen["registration"]["seen_at"] is not None

            # 6. Undo Seen returns to Arrived, never behind Arrival
            res_undo = await undo_seen(str(p_id), actor={"_id": ObjectId(), "role": "admin"})
            assert res_undo["registration"]["queue_status"] == "arrived"
            assert res_undo["registration"]["seen_at"] is None
            assert res_undo["registration"]["printed_at"] is not None, "printed_at must remain intact"

        asyncio.run(_run())

    def test_undo_seen_blocked_after_transcription_created(self, monkeypatch):
        """Cannot undo seen if doctor/optometrist has already created a clinical transcription."""
        async def _run():
            mock_db = setup_stress_db(monkeypatch)
            camp_id, day_id = await seed_active_camp(mock_db)

            p_id = ObjectId()
            await mock_db.patients.insert_one({
                "_id": p_id,
                "camp_id": camp_id,
                "camp_day_id": day_id,
                "reg_no": 8,
                "queue_status": "seen",
                "printed_at": now_utc(),
                "seen_at": now_utc(),
            })
            # Doctor started transcription
            await mock_db.transcriptions.insert_one({
                "_id": ObjectId(),
                "patient_id": p_id,
                "camp_id": camp_id,
                "locked": False, "specs_measurements": RX,
            })

            # Undo seen must be blocked
            with pytest.raises(HTTPException) as exc:
                await undo_seen(str(p_id), actor={"_id": ObjectId(), "role": "admin"})
            assert exc.value.status_code == 409
            assert "transcription exists" in exc.value.detail.lower()

        asyncio.run(_run())

    def test_medicine_fulfilment_locks_transcription(self, monkeypatch):
        """Medicine fulfilment locks transcription to prevent further direct edits."""
        async def _run():
            mock_db = setup_stress_db(monkeypatch)
            p_id = ObjectId()
            t_id = ObjectId()
            await mock_db.patients.insert_one({
                "_id": p_id, "queue_status": "seen", "printed_at": now_utc(), "seen_at": now_utc(),
            })
            await mock_db.transcriptions.insert_one({
                "_id": t_id, "patient_id": p_id, "locked": False, "specs_measurements": RX,
            })

            body = FulfilmentBody(transcription_id=str(t_id), item_type="medicine", status="fulfilled")
            await record_fulfilment(body, actor={"_id": ObjectId(), "role": "pharmacist"})

            t_doc = await mock_db.transcriptions.find_one({"_id": t_id})
            assert t_doc["locked"] is True

        asyncio.run(_run())

    def test_correction_append_only_audit_log(self, monkeypatch):
        """Corrections modify only allowed fields and persist an immutable record in corrections collection."""
        async def _run():
            mock_db = setup_stress_db(monkeypatch)
            p_id = ObjectId()
            t_id = ObjectId()
            await mock_db.patients.insert_one({
                "_id": p_id, "queue_status": "seen", "printed_at": now_utc(), "seen_at": now_utc(),
            })
            await mock_db.transcriptions.insert_one({
                "_id": t_id, "patient_id": p_id, "locked": True, "blood_sugar": "110", "bp": "120/80",
            })

            body = CorrectionBody(
                transcription_id=str(t_id),
                reason="Correcting BP reading per doctor re-check",
                changes={"bp": "135/85", "unauthorized_field": "hacked"},
            )
            res = await add_correction(body, actor={"_id": ObjectId(), "role": "doctor"})
            assert "correction_id" in res

            # Allowed field bp updated, unauthorized field ignored
            t_doc = await mock_db.transcriptions.find_one({"_id": t_id})
            assert t_doc["bp"] == "135/85"
            assert "unauthorized_field" not in t_doc

            # Audit record stored
            corr = await mock_db.corrections.find_one({"transcription_id": t_id})
            assert corr["reason"] == "Correcting BP reading per doctor re-check"
            assert corr["changes"]["bp"] == "135/85"

        asyncio.run(_run())

    def test_massive_concurrent_specs_deferral_race_50_workers(self, monkeypatch):
        """50 concurrent requests competing for 3 seats -> exactly 3 succeed, 47 fail with 409."""
        async def _run():
            mock_db = setup_stress_db(monkeypatch)
            specs_day_id = ObjectId()
            await mock_db.specs_collection_days.insert_one({
                "_id": specs_day_id,
                "camp_id": ObjectId(),
                "day_date": "2026-09-25",
                "venue": "Vision Center",
                "seat_limit": 3,
                "seats_taken": 0,
            })

            trans_ids = []
            for i in range(50):
                tid = ObjectId()
                pid = ObjectId()
                await mock_db.patients.insert_one({
                    "_id": pid, "queue_status": "seen", "printed_at": now_utc(), "seen_at": now_utc(),
                })
                await mock_db.transcriptions.insert_one({"_id": tid, "patient_id": pid, "locked": False, "specs_measurements": RX})
                trans_ids.append(tid)

            async def book_worker(tid):
                body = FulfilmentBody(
                    transcription_id=str(tid),
                    item_type="specs_made",
                    status="deferred",
                    specs_collection_day_id=str(specs_day_id),
                )
                try:
                    await record_fulfilment(body, actor={"_id": ObjectId(), "role": "optometrist"})
                    return "OK"
                except HTTPException as e:
                    return f"FAIL_{e.status_code}"

            results = await asyncio.gather(*[book_worker(tid) for tid in trans_ids])
            ok_count = sum(1 for r in results if r == "OK")
            fail_count = sum(1 for r in results if r == "FAIL_409")

            assert ok_count == 3, f"Expected exactly 3 winners, got {ok_count}"
            assert fail_count == 47, f"Expected 47 409 failures, got {fail_count}"

            day_doc = await mock_db.specs_collection_days.find_one({"_id": specs_day_id})
            assert day_doc["seats_taken"] == 3

        asyncio.run(_run())


# =====================================================================
# 4. SECURE QR DECODING FUZZING & PAYLOAD EDGE CASES
# =====================================================================

class TestSecureQrDecodingFuzzAndEdgeCases:
    def test_secure_qr_gzip_and_raw_deflate_compatibility(self):
        """Secure QR decoding works with gzip headers and raw zlib streams."""
        fields = [
            "2", "123420210101120000", "Bhavna Jain", "1994-06-25", "F", "W/O V Jain",
            "Udaipur", "City Palace", "12", "Old City", "313001", "Udaipur HO",
            "Rajasthan", "Palace Rd", "Girwa", "Udaipur"
        ]
        raw_bytes = b"\xff".join(f.encode("ISO-8859-1") for f in fields) + b"\xff" + b"SIG" * 15

        # Test with raw deflate
        comp_deflate = zlib.compress(raw_bytes)
        big_int_deflate = str(int.from_bytes(comp_deflate, "big"))
        res1 = decode_aadhaar(big_int_deflate)
        assert res1["outcome"] == "card"
        assert res1["data"]["full_name"] == "Bhavna Jain"
        assert res1["data"]["aadhaar_last4"] == "1234"

        # Test with gzip
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as f:
            f.write(raw_bytes)
        comp_gzip = buf.getvalue()
        big_int_gzip = str(int.from_bytes(comp_gzip, "big"))
        res2 = decode_aadhaar(big_int_gzip)
        assert res2["outcome"] == "card"
        assert res2["data"]["full_name"] == "Bhavna Jain"

    def test_secure_qr_corrupted_stream_graceful_garbage_response(self):
        """Corrupted compressed payloads return outcome='garbage' without unhandled exceptions."""
        garbage_numbers = "987654321098765432109876543210987654321098765432109876543210"
        res = decode_aadhaar(garbage_numbers)
        assert res["outcome"] == "garbage"
        assert "Could not decode" in res["message"] or "Could not read" in res["message"]

    def test_secure_qr_missing_name_field_returns_garbage(self):
        """Decompressed stream with empty name returns garbage outcome."""
        fields = [
            "2", "123420210101120000", "", "1994-06-25", "F", "W/O V Jain",
            "Udaipur", "City Palace", "12", "Old City", "313001", "Udaipur HO",
            "Rajasthan", "Palace Rd", "Girwa", "Udaipur"
        ]
        raw_bytes = b"\xff".join(f.encode("ISO-8859-1") for f in fields) + b"\xff" + b"SIG" * 15
        comp = zlib.compress(raw_bytes)
        big_int = str(int.from_bytes(comp, "big"))
        res = decode_aadhaar(big_int)
        assert res["outcome"] == "garbage"

    def test_extract_delimited_segments_insufficient_delimiters(self):
        """When fewer delimiters than fields are present, extracts available fields safely."""
        data = b"ind\xffref1234\xffJohn Doe\xff1990-01-01"
        res = _extract_delimited_segments(data, ["indicator", "referenceid", "name", "dob", "gender", "careof"])
        assert res["indicator"] == "ind"
        assert res["referenceid"] == "ref1234"
        assert res["name"] == "John Doe"
        assert "gender" not in res

    def test_date_cleaning_and_iso_dob_fuzzing(self):
        """Verify _clean_date_string and _to_iso_dob under noisy inputs."""
        assert _clean_date_string(" '1990-05-12' ") == "1990-05-12"
        assert _clean_date_string("`15/08/1947`") == "15/08/1947"
        assert _clean_date_string("1980-01-01T15:30:00.000Z") == "1980-01-01"
        assert _clean_date_string("1980-01-01 00:00:00") == "1980-01-01"
        assert _clean_date_string("1985 (approx)") == "1985"

        assert _to_iso_dob(" '1990-05-12' ") == "1990-05-12"
        assert _to_iso_dob("15/08/1947") == "1947-08-15"
        assert _to_iso_dob("01-Jan-2000") == "2000-01-01"
        assert _to_iso_dob("15 December 1995") == "1995-12-15"
        assert _to_iso_dob("1975") == "1975-01-01"
        assert _to_iso_dob("gibberish-string") is None
