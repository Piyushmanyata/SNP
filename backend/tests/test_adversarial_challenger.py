import sys
import os
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

os.environ["MONGO_URL"] = "mongodb://localhost:27017"
os.environ["DB_NAME"] = "snp_test"

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
    _parse_xml_attributes,
    _extract_xml_address,
    _decode_demo_payload,
)
from models import RegisterBody, FulfilmentBody
import routes_registration
import routes_clinical
from routes_registration import (
    _create_registration,
    _check_registration_duplicates,
    _resolve_person,
    _validate_camp_and_day,
    _build_patient_document,
)
from routes_clinical import (
    record_fulfilment,
    _validate_fulfilment_matrix,
    _process_deferral,
    _cleanup_prior_fulfilment,
    _make_slip,
)
import db as db_module

# =====================================================================
# IN-MEMORY ASYNC MONGO MOCK
# =====================================================================

class MockCursor:
    def __init__(self, docs):
        self._docs = [copy.deepcopy(d) for d in docs]

    def limit(self, n):
        self._docs = self._docs[:n]
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

    def find(self, query):
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


def setup_mock_db(monkeypatch):
    mock_db = MockDB()
    monkeypatch.setattr(db_module, "get_db", lambda: mock_db)
    monkeypatch.setattr(routes_registration, "get_db", lambda: mock_db)
    monkeypatch.setattr(routes_clinical, "get_db", lambda: mock_db)
    monkeypatch.setattr(routes_registration, "next_seq", mock_db.next_seq)
    monkeypatch.setattr(db_module, "next_seq", mock_db.next_seq)
    return mock_db


async def insert_seen_patient(mock_db, p_id=None):
    p_id = p_id or ObjectId()
    await mock_db.patients.insert_one({
        "_id": p_id,
        "queue_status": "seen",
        "printed_at": "2026-09-01T00:00:00Z",
        "seen_at": "2026-09-01T00:00:01Z",
    })
    return p_id


# =====================================================================
# 1. ADVERSARIAL TESTS FOR parse_xml_qr & decode_aadhaar
# =====================================================================

class TestXmlAndAadhaarStress:
    def test_xml_qr_valid_complete(self):
        xml = '''<?xml version="1.0" encoding="UTF-8"?>
        <PrintLetterBarcodeData uid="999988881234" name="Rajesh Kumar" gender="M"
            dob="15/08/1985" house="Flat 402" street="Gandhi Path" landmark="Near Post Office"
            loc="Civil Lines" po="GPO" vtc="Jaipur" subdist="Jaipur" dist="Jaipur" state="Rajasthan" pc="302001"/>'''
        res = parse_xml_qr(xml)
        assert res["full_name"] == "Rajesh Kumar"
        assert res["gender"] == "M"
        assert res["dob"] == "1985-08-15"
        assert res["aadhaar_last4"] == "1234"
        assert "Flat 402" in res["address"]
        assert "Rajasthan" in res["address"]
        assert "302001" in res["address"]

    def test_xml_qr_unescaped_ampersand_in_address(self):
        xml = '<PrintLetterBarcodeData uid="123412345678" name="Sita & Gita Traders" house="Shop & Office 5" gender="F" yob="1990" dist="Delhi" pc="110001"/>'
        res = parse_xml_qr(xml)
        assert res["full_name"] == "Sita & Gita Traders"
        assert res["gender"] == "F"
        assert res["dob"] == "1990-01-01"
        assert "Shop & Office 5" in res["address"]

    def test_xml_qr_missing_name_raises_value_error(self):
        xml = '<PrintLetterBarcodeData uid="123412345678" gender="M" yob="1990" dist="Delhi"/>'
        with pytest.raises(ValueError, match="No name in XML QR"):
            parse_xml_qr(xml)

    def test_xml_qr_empty_name_whitespace_raises(self):
        xml = '<PrintLetterBarcodeData uid="123412345678" name="   " gender="M" yob="1990"/>'
        with pytest.raises(ValueError, match="No name in XML QR"):
            parse_xml_qr(xml)

    def test_xml_qr_fallback_regex_on_malformed_xml_syntax(self):
        broken_xml = '<PrintLetterBarcodeData uid="987654321098" name="Kavita Rao" gender="FEMALE" dob="1995-12-30" dist="Bengaluru" unclosed'
        res = parse_xml_qr(broken_xml)
        assert res["full_name"] == "Kavita Rao"
        assert res["gender"] == "F"
        assert res["dob"] == "1995-12-30"
        assert res["aadhaar_last4"] == "1098"
        assert "Bengaluru" in res["address"]

    def test_xml_qr_unicode_characters_and_hindi_script(self):
        xml = '<PrintLetterBarcodeData uid="555566667777" name="राजेश शर्मा" gender="M" yob="1982" dist="वाराणसी" pc="221001"/>'
        res = parse_xml_qr(xml)
        assert res["full_name"] == "राजेश शर्मा"
        assert res["gender"] == "M"
        assert res["dob"] == "1982-01-01"
        assert "वाराणसी" in res["address"]

    def test_xml_qr_short_uid_handling(self):
        xml = '<PrintLetterBarcodeData uid="12" name="Anil" gender="M"/>'
        res = parse_xml_qr(xml)
        assert res["aadhaar_last4"] == "12"

    def test_xml_qr_no_uid(self):
        xml = '<PrintLetterBarcodeData name="Sunita" gender="F"/>'
        res = parse_xml_qr(xml)
        assert res["aadhaar_last4"] == ""

    def test_xml_qr_alternative_attribute_names(self):
        xml = '<PrintLetterBarcodeData uid="111122223333" name="Mohan Lal" gender="Male" lm="Shiv Mandir" loc="Sector 2" village="Khed" subdist="Haveli" dist="Pune" pc="411001"/>'
        res = parse_xml_qr(xml)
        assert "Shiv Mandir" in res["address"]
        assert "Sector 2" in res["address"]
        assert "Khed" in res["address"]
        assert "Haveli" in res["address"]
        assert "Pune" in res["address"]
        assert "411001" in res["address"]

    def test_xml_qr_xxe_safety(self):
        xxe_xml = '''<?xml version="1.0"?>
        <!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
        <PrintLetterBarcodeData uid="111122224444" name="&xxe; Hacked" gender="M"/>'''
        try:
            res = parse_xml_qr(xxe_xml)
            assert res["aadhaar_last4"] == "4444"
        except Exception as e:
            assert isinstance(e, (ValueError, ET.ParseError))

    def test_decode_aadhaar_edge_cases(self):
        assert decode_aadhaar("")["outcome"] == "not-aadhaar"
        assert decode_aadhaar(None)["outcome"] == "not-aadhaar"
        assert decode_aadhaar("   \t\n  ")["outcome"] == "not-aadhaar"
        assert decode_aadhaar("\ufeff")["outcome"] == "not-aadhaar"
        assert decode_aadhaar("snp:patient-12345")["outcome"] == "not-aadhaar"
        assert decode_aadhaar("https://camps.snp.org/p/64f1234567890abc")["outcome"] == "not-aadhaar"
        assert decode_aadhaar("THIS IS RANDOM GARBAGE TEXT 12345")["outcome"] == "garbage"
        assert decode_aadhaar("1234567890")["outcome"] == "garbage"
        assert decode_aadhaar("<PrintLetterBarcodeData />")["outcome"] == "garbage"
        assert decode_aadhaar("AADHAAR|Only|Three|Fields")["outcome"] == "garbage"

    def test_to_iso_dob_variations(self):
        assert _to_iso_dob("15-08-1985") == "1985-08-15"
        assert _to_iso_dob("15/08/1985") == "1985-08-15"
        assert _to_iso_dob("1985-08-15") == "1985-08-15"
        assert _to_iso_dob("15.08.1985") == "1985-08-15"
        assert _to_iso_dob("15-Aug-1985") == "1985-08-15"
        assert _to_iso_dob("15 August 1985") == "1985-08-15"
        assert _to_iso_dob("1985") == "1985-01-01"
        assert _to_iso_dob("1985-08-15T00:00:00") == "1985-08-15"
        assert _to_iso_dob("1985-08-15 12:30:00") == "1985-08-15"
        assert _to_iso_dob("invalid-date") is None
        assert _to_iso_dob("") is None
        assert _to_iso_dob(None) is None

    def test_normalize_gender(self):
        assert _normalize_gender("M") == "M"
        assert _normalize_gender("Male") == "M"
        assert _normalize_gender("m") == "M"
        assert _normalize_gender("F") == "F"
        assert _normalize_gender("Female") == "F"
        assert _normalize_gender("f") == "F"
        assert _normalize_gender("Other") == "O"
        assert _normalize_gender("Transgender") == "O"
        assert _normalize_gender("") == "O"
        assert _normalize_gender(None) == "O"

    def test_calc_age(self):
        assert _calc_age(None) is None
        assert _calc_age("invalid") is None
        age_2000 = _calc_age("2000-01-01")
        assert age_2000 is not None and age_2000 >= 20

    def test_secure_qr_v2_decompression_and_parsing(self):
        fields = [
            "2", "999920200101120000", "Aditi Rao", "05-11-1992", "F", "D/O S Rao",
            "Bengaluru", "Opp Park", "101", "Indiranagar", "560038", "Indiranagar PO",
            "Karnataka", "100 Feet Rd", "Bengaluru East", "Bengaluru"
        ]
        raw_bytes = b"\xff".join(f.encode("ISO-8859-1") for f in fields) + b"\xff" + b"SIG" * 20
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as f:
            f.write(raw_bytes)
        comp = buf.getvalue()
        big_int_str = str(int.from_bytes(comp, "big"))

        res = parse_secure_qr(big_int_str)
        assert res["full_name"] == "Aditi Rao"
        assert res["gender"] == "F"
        assert res["dob"] == "1992-11-05"
        assert res["aadhaar_last4"] == "9999"
        assert "Indiranagar" in res["address"]
        assert "560038" in res["address"]

        wrap_res = decode_aadhaar(big_int_str)
        assert wrap_res["outcome"] == "card"
        assert wrap_res["source"] == "secure_qr"
        assert wrap_res["data"]["full_name"] == "Aditi Rao"


# =====================================================================
# 2. ADVERSARIAL INVARIANT TESTS FOR _create_registration
# =====================================================================

class TestRegistrationDecomposedAndInvariants:
    def test_no_active_camp_raises_409(self, monkeypatch):
        async def _run():
            mock_db = setup_mock_db(monkeypatch)
            body = RegisterBody(camp_day_id=str(ObjectId()), full_name="Test User", phone="9876543210", age=30)
            with pytest.raises(HTTPException) as exc:
                await _create_registration(body, actor_id=ObjectId(), is_self=False, request=None)
            assert exc.value.status_code == 409
            assert "No active camp" in exc.value.detail
        asyncio.run(_run())

    def test_invalid_camp_day_raises_404(self, monkeypatch):
        async def _run():
            mock_db = setup_mock_db(monkeypatch)
            camp_id = ObjectId()
            await mock_db.camps.insert_one({"_id": camp_id, "name": "Active Camp", "is_active": True})

            body = RegisterBody(camp_day_id=str(ObjectId()), full_name="Test User", phone="9876543210", age=30)
            with pytest.raises(HTTPException) as exc:
                await _create_registration(body, actor_id=ObjectId(), is_self=False, request=None)
            assert exc.value.status_code == 404
            assert "Camp day not found" in exc.value.detail
        asyncio.run(_run())

    def test_registration_idempotency_returns_existing_without_recreation(self, monkeypatch):
        async def _run():
            mock_db = setup_mock_db(monkeypatch)
            camp_id = ObjectId()
            day_id = ObjectId()
            await mock_db.camps.insert_one({"_id": camp_id, "name": "Camp", "is_active": True})
            await mock_db.camp_days.insert_one({"_id": day_id, "camp_id": camp_id, "day_date": "2026-09-01"})
            
            req_id = "unique-request-token-123"
            await mock_db.patients.insert_one({
                "_id": ObjectId(),
                "camp_id": camp_id,
                "camp_day_id": day_id,
                "reg_no": 101,
                "full_name": "Idempotent Patient",
                "registration_request_id": req_id,
                "queue_status": "registered",
                "patient_qr": "patient-qr-uuid-1",
            })

            body = RegisterBody(
                camp_day_id=str(day_id),
                full_name="Idempotent Patient",
                phone="9876543210",
                age=40,
                registration_request_id=req_id
            )
            patient, created = await _create_registration(body, actor_id=ObjectId(), is_self=False, request=None)
            assert created is False
            assert patient["reg_no"] == 101
            assert len(mock_db.patients.docs) == 1
        asyncio.run(_run())

    def test_concurrent_idempotent_registrations(self, monkeypatch):
        async def _run():
            mock_db = setup_mock_db(monkeypatch)
            camp_id = ObjectId()
            day_id = ObjectId()
            await mock_db.camps.insert_one({"_id": camp_id, "is_active": True})
            await mock_db.camp_days.insert_one({"_id": day_id, "camp_id": camp_id, "day_date": "2026-09-01"})

            req_id = "concurrent-idemp-token-456"
            body = RegisterBody(
                camp_day_id=str(day_id),
                full_name="Concurrency User",
                phone="9876543210",
                age=28,
                registration_request_id=req_id
            )

            p1, c1 = await _create_registration(body, actor_id=ObjectId(), is_self=False, request=None)
            assert c1 is True

            tasks = [_create_registration(body, actor_id=ObjectId(), is_self=False, request=None) for _ in range(5)]
            results = await asyncio.gather(*tasks)
            for p, c in results:
                assert c is False
                assert p["reg_no"] == p1["reg_no"]
            assert len(mock_db.patients.docs) == 1
        asyncio.run(_run())

    def test_dummy_phone_rejection_at_desk(self, monkeypatch):
        async def _run():
            mock_db = setup_mock_db(monkeypatch)
            camp_id = ObjectId()
            day_id = ObjectId()
            await mock_db.camps.insert_one({"_id": camp_id, "is_active": True})
            await mock_db.camp_days.insert_one({"_id": day_id, "camp_id": camp_id, "day_date": "2026-09-01"})

            body = RegisterBody(camp_day_id=str(day_id), full_name="User", phone="9999999999", age=35)
            with pytest.raises(HTTPException) as exc:
                await _create_registration(body, actor_id=ObjectId(), is_self=False, request=None)
            assert exc.value.status_code == 400
            assert "valid 10-digit mobile number" in exc.value.detail
        asyncio.run(_run())

    def test_aadhaar_person_resolution_and_camp_dedup(self, monkeypatch):
        async def _run():
            mock_db = setup_mock_db(monkeypatch)
            camp_id = ObjectId()
            day_id = ObjectId()
            await mock_db.camps.insert_one({"_id": camp_id, "is_active": True})
            await mock_db.camp_days.insert_one({"_id": day_id, "camp_id": camp_id, "day_date": "2026-09-01"})

            body = RegisterBody(
                camp_day_id=str(day_id),
                full_name="Suresh Raina",
                gender="M",
                dob="1986-11-27",
                phone="9876543210",
                aadhaar_scanned=True,
                aadhaar_last4="7890",
            )
            patient1, created1 = await _create_registration(body, actor_id=ObjectId(), is_self=False, request=None)
            assert created1 is True
            assert patient1["person_id"] is not None
            assert patient1["reg_no"] == 1
            assert patient1["queue_status"] == "registered"

            # Registering again with same Aadhaar in same camp is a hard Duplicate in camp
            with pytest.raises(HTTPException) as exc:
                await _create_registration(body, actor_id=ObjectId(), is_self=False, request=None)
            assert exc.value.status_code == 409
            assert exc.value.detail["code"] == "DUPLICATE_IN_CAMP"
            assert exc.value.detail["registration"]["id"] == patient1["id"]
            assert len(mock_db.patients.docs) == 1
        asyncio.run(_run())

    def test_duplicate_aadhaar_last4_and_name_without_person_raises_409(self, monkeypatch):
        async def _run():
            mock_db = setup_mock_db(monkeypatch)
            camp_id = ObjectId()
            day_id = ObjectId()
            await mock_db.camps.insert_one({"_id": camp_id, "is_active": True})
            await mock_db.camp_days.insert_one({"_id": day_id, "camp_id": camp_id, "day_date": "2026-09-01"})
            mock_db._seqs["reg_no"] = 1
            await mock_db.patients.insert_one({
                "_id": ObjectId(),
                "camp_id": camp_id,
                "camp_day_id": day_id,
                "reg_no": 1,
                "full_name": "Rohan Gupta",
                "full_name_normalized": "rohan gupta",
                "aadhaar_last4": "4321",
                "queue_status": "registered",
                "patient_qr": "qr-1",
            })

            body = RegisterBody(
                camp_day_id=str(day_id),
                full_name="Rohan Gupta",
                age=30,
                phone="9876543210",
                aadhaar_last4="4321",
                aadhaar_scanned=False,
            )
            with pytest.raises(HTTPException) as exc:
                await _create_registration(body, actor_id=ObjectId(), is_self=False, request=None)
            assert exc.value.status_code == 409
            assert exc.value.detail["code"] == "DUPLICATE_IN_CAMP"

            body.override_duplicate = True
            with pytest.raises(HTTPException) as exc2:
                await _create_registration(body, actor_id=ObjectId(), is_self=False, request=None)
            assert exc2.value.status_code == 409
            assert exc2.value.detail["code"] == "DUPLICATE_IN_CAMP"
            assert len(mock_db.patients.docs) == 1
        asyncio.run(_run())


# =====================================================================
# 3. ADVERSARIAL INVARIANT & CONCURRENCY TESTS FOR record_fulfilment
# =====================================================================

class TestFulfilmentDecomposedAndInvariants:
    def test_transcription_not_found_raises_404(self, monkeypatch):
        async def _run():
            mock_db = setup_mock_db(monkeypatch)

            body = FulfilmentBody(
                transcription_id=str(ObjectId()),
                item_type="medicine",
                status="fulfilled"
            )
            with pytest.raises(HTTPException) as exc:
                await record_fulfilment(body, actor={"_id": ObjectId(), "role": "optometrist"})
            assert exc.value.status_code == 404
            assert "Transcription not found" in exc.value.detail
        asyncio.run(_run())

    def test_fulfilment_rejects_when_patient_not_seen(self, monkeypatch):
        async def _run():
            mock_db = setup_mock_db(monkeypatch)
            t_id = ObjectId()
            p_id = ObjectId()
            await mock_db.patients.insert_one({
                "_id": p_id, "queue_status": "registered", "printed_at": None,
            })
            await mock_db.transcriptions.insert_one({
                "_id": t_id, "patient_id": p_id, "locked": False,
            })
            body = FulfilmentBody(
                transcription_id=str(t_id),
                item_type="medicine",
                status="fulfilled",
            )
            with pytest.raises(HTTPException) as exc:
                await record_fulfilment(body, actor={"_id": ObjectId(), "role": "optometrist"})
            assert exc.value.status_code == 409
        asyncio.run(_run())

    def test_fulfilment_matrix_validation(self):
        _validate_fulfilment_matrix("medicine", "fulfilled")
        _validate_fulfilment_matrix("medicine", "not_available")
        _validate_fulfilment_matrix("medicine", "not_required")
        _validate_fulfilment_matrix("specs", "fulfilled")
        _validate_fulfilment_matrix("specs", "deferred")
        _validate_fulfilment_matrix("specs", "not_required")
        _validate_fulfilment_matrix("ot", "fulfilled")
        _validate_fulfilment_matrix("ot", "deferred")
        _validate_fulfilment_matrix("ot", "not_required")

        with pytest.raises(HTTPException) as exc:
            _validate_fulfilment_matrix("medicine", "deferred")
        assert exc.value.status_code == 400

        with pytest.raises(HTTPException) as exc:
            _validate_fulfilment_matrix("specs", "not_available")
        assert exc.value.status_code == 400

        with pytest.raises(HTTPException) as exc:
            _validate_fulfilment_matrix("ot", "unknown_status")
        assert exc.value.status_code == 400

    def test_specs_deferral_creates_slip_and_increments_version(self, monkeypatch):
        async def _run():
            mock_db = setup_mock_db(monkeypatch)
            t_id = ObjectId()
            p_id = ObjectId()
            day1 = ObjectId()
            day2 = ObjectId()
            await insert_seen_patient(mock_db, p_id)
            await mock_db.transcriptions.insert_one({"_id": t_id, "patient_id": p_id, "locked": False})
            await mock_db.specs_collection_days.insert_one({
                "_id": day1, "camp_id": ObjectId(), "day_date": "2026-09-15",
                "venue": "District Hospital", "seat_limit": 5, "seats_taken": 0,
            })
            await mock_db.specs_collection_days.insert_one({
                "_id": day2, "camp_id": ObjectId(), "day_date": "2026-09-20",
                "venue": "Community Health Center", "seat_limit": 5, "seats_taken": 0,
            })

            bad_body = FulfilmentBody(transcription_id=str(t_id), item_type="specs", status="deferred")
            with pytest.raises(HTTPException) as exc:
                await record_fulfilment(bad_body, actor={"_id": ObjectId(), "role": "optometrist"})
            assert exc.value.status_code == 400

            freeform = FulfilmentBody(
                transcription_id=str(t_id),
                item_type="specs",
                status="deferred",
                collection_date="2026-09-15",
                collection_venue="District Hospital",
            )
            with pytest.raises(HTTPException) as exc:
                await record_fulfilment(freeform, actor={"_id": ObjectId(), "role": "optometrist"})
            assert exc.value.status_code == 400

            good_body = FulfilmentBody(
                transcription_id=str(t_id),
                item_type="specs",
                status="deferred",
                specs_collection_day_id=str(day1),
            )
            res1 = await record_fulfilment(good_body, actor={"_id": ObjectId(), "role": "optometrist"})
            assert res1["slip"]["version"] == 1
            assert res1["slip"]["active"] is True
            assert res1["slip"]["collection_date"] == "2026-09-15"
            assert res1["slip"]["collection_venue"] == "District Hospital"
            assert res1["fulfilment"]["status"] == "deferred"
            d1 = await mock_db.specs_collection_days.find_one({"_id": day1})
            assert d1["seats_taken"] == 1

            update_body = FulfilmentBody(
                transcription_id=str(t_id),
                item_type="specs",
                status="deferred",
                specs_collection_day_id=str(day2),
            )
            res2 = await record_fulfilment(update_body, actor={"_id": ObjectId(), "role": "optometrist"})
            assert res2["slip"]["version"] == 2
            assert res2["slip"]["collection_date"] == "2026-09-20"

            active_slips = [s for s in mock_db.deferred_slips.docs if s["active"]]
            cancelled_slips = [s for s in mock_db.deferred_slips.docs if s["cancelled"]]
            assert len(active_slips) == 1
            assert len(cancelled_slips) == 1
            assert active_slips[0]["version"] == 2
            d1_after = await mock_db.specs_collection_days.find_one({"_id": day1})
            d2_after = await mock_db.specs_collection_days.find_one({"_id": day2})
            assert d1_after["seats_taken"] == 0
            assert d2_after["seats_taken"] == 1
        asyncio.run(_run())

    def test_specs_deferral_atomic_seat_limit_and_overbooking_prevention(self, monkeypatch):
        async def _run():
            mock_db = setup_mock_db(monkeypatch)
            t_id = ObjectId()
            p_id = ObjectId()
            specs_day_id = ObjectId()

            await insert_seen_patient(mock_db, p_id)
            await mock_db.transcriptions.insert_one({"_id": t_id, "patient_id": p_id, "locked": False})
            await mock_db.specs_collection_days.insert_one({
                "_id": specs_day_id,
                "camp_id": ObjectId(),
                "day_date": "2026-09-10",
                "venue": "Optical Desk",
                "seat_limit": 1,
                "seats_taken": 0,
            })

            body1 = FulfilmentBody(
                transcription_id=str(t_id),
                item_type="specs",
                status="deferred",
                specs_collection_day_id=str(specs_day_id),
            )
            res1 = await record_fulfilment(body1, actor={"_id": ObjectId(), "role": "optometrist"})
            assert res1["fulfilment"]["status"] == "deferred"

            specs_day = await mock_db.specs_collection_days.find_one({"_id": specs_day_id})
            assert specs_day["seats_taken"] == 1

            t_id2 = ObjectId()
            p_id2 = await insert_seen_patient(mock_db)
            await mock_db.transcriptions.insert_one({"_id": t_id2, "patient_id": p_id2, "locked": False})
            body2 = FulfilmentBody(
                transcription_id=str(t_id2),
                item_type="specs",
                status="deferred",
                specs_collection_day_id=str(specs_day_id),
            )
            with pytest.raises(HTTPException) as exc:
                await record_fulfilment(body2, actor={"_id": ObjectId(), "role": "optometrist"})
            assert exc.value.status_code == 409
        asyncio.run(_run())

    def test_specs_rebooking_releases_prior_seat(self, monkeypatch):
        async def _run():
            mock_db = setup_mock_db(monkeypatch)
            t_id = ObjectId()
            p_id = ObjectId()
            day1 = ObjectId()
            day2 = ObjectId()

            await insert_seen_patient(mock_db, p_id)
            await mock_db.transcriptions.insert_one({"_id": t_id, "patient_id": p_id, "locked": False})
            await mock_db.specs_collection_days.insert_one({
                "_id": day1, "camp_id": ObjectId(), "day_date": "2026-09-10",
                "venue": "Optical 1", "seat_limit": 5, "seats_taken": 0,
            })
            await mock_db.specs_collection_days.insert_one({
                "_id": day2, "camp_id": ObjectId(), "day_date": "2026-09-11",
                "venue": "Optical 2", "seat_limit": 5, "seats_taken": 0,
            })

            body1 = FulfilmentBody(
                transcription_id=str(t_id), item_type="specs", status="deferred",
                specs_collection_day_id=str(day1),
            )
            await record_fulfilment(body1, actor={"_id": ObjectId(), "role": "optometrist"})

            d1 = await mock_db.specs_collection_days.find_one({"_id": day1})
            assert d1["seats_taken"] == 1

            body2 = FulfilmentBody(
                transcription_id=str(t_id), item_type="specs", status="deferred",
                specs_collection_day_id=str(day2),
            )
            await record_fulfilment(body2, actor={"_id": ObjectId(), "role": "optometrist"})

            d1_after = await mock_db.specs_collection_days.find_one({"_id": day1})
            d2_after = await mock_db.specs_collection_days.find_one({"_id": day2})
            assert d1_after["seats_taken"] == 0
            assert d2_after["seats_taken"] == 1
        asyncio.run(_run())

    def test_specs_fulfilled_cancels_token_and_releases_seat(self, monkeypatch):
        async def _run():
            mock_db = setup_mock_db(monkeypatch)
            t_id = ObjectId()
            day_id = ObjectId()
            p_id = await insert_seen_patient(mock_db)
            await mock_db.transcriptions.insert_one({"_id": t_id, "patient_id": p_id, "locked": False})
            await mock_db.specs_collection_days.insert_one({
                "_id": day_id, "camp_id": ObjectId(), "day_date": "2026-09-10",
                "venue": "Optical", "seat_limit": 1, "seats_taken": 0,
            })
            await record_fulfilment(
                FulfilmentBody(transcription_id=str(t_id), item_type="specs", status="deferred",
                               specs_collection_day_id=str(day_id)),
                actor={"_id": ObjectId(), "role": "optometrist"},
            )
            res = await record_fulfilment(
                FulfilmentBody(transcription_id=str(t_id), item_type="specs", status="fulfilled"),
                actor={"_id": ObjectId(), "role": "optometrist"},
            )
            assert res["slip"] is None
            day = await mock_db.specs_collection_days.find_one({"_id": day_id})
            assert day["seats_taken"] == 0
            assert all(not s["active"] for s in mock_db.deferred_slips.docs)
            assert all(s["cancelled"] for s in mock_db.deferred_slips.docs)
        asyncio.run(_run())

    def test_specs_same_day_rerecord_on_full_day(self, monkeypatch):
        async def _run():
            mock_db = setup_mock_db(monkeypatch)
            t_id = ObjectId()
            day_id = ObjectId()
            p_id = await insert_seen_patient(mock_db)
            await mock_db.transcriptions.insert_one({"_id": t_id, "patient_id": p_id, "locked": False})
            await mock_db.specs_collection_days.insert_one({
                "_id": day_id, "camp_id": ObjectId(), "day_date": "2026-09-10",
                "venue": "Optical", "seat_limit": 1, "seats_taken": 0,
            })
            await record_fulfilment(
                FulfilmentBody(transcription_id=str(t_id), item_type="specs", status="deferred",
                               specs_collection_day_id=str(day_id)),
                actor={"_id": ObjectId(), "role": "optometrist"},
            )
            res = await record_fulfilment(
                FulfilmentBody(transcription_id=str(t_id), item_type="specs", status="deferred",
                               specs_collection_day_id=str(day_id)),
                actor={"_id": ObjectId(), "role": "optometrist"},
            )
            assert res["slip"]["version"] == 2
            day = await mock_db.specs_collection_days.find_one({"_id": day_id})
            assert day["seats_taken"] == 1
        asyncio.run(_run())

    def test_specs_fulfil_then_redefer_consumes_and_blocks_overbook(self, monkeypatch):
        async def _run():
            mock_db = setup_mock_db(monkeypatch)
            t_a = ObjectId()
            t_b = ObjectId()
            day_id = ObjectId()
            p_a = await insert_seen_patient(mock_db)
            p_b = await insert_seen_patient(mock_db)
            await mock_db.transcriptions.insert_one({"_id": t_a, "patient_id": p_a, "locked": False})
            await mock_db.transcriptions.insert_one({"_id": t_b, "patient_id": p_b, "locked": False})
            await mock_db.specs_collection_days.insert_one({
                "_id": day_id, "camp_id": ObjectId(), "day_date": "2026-09-10",
                "venue": "Optical", "seat_limit": 1, "seats_taken": 0,
            })
            actor = {"_id": ObjectId(), "role": "optometrist"}
            await record_fulfilment(
                FulfilmentBody(transcription_id=str(t_a), item_type="specs", status="deferred",
                               specs_collection_day_id=str(day_id)),
                actor=actor,
            )
            await record_fulfilment(
                FulfilmentBody(transcription_id=str(t_a), item_type="specs", status="fulfilled",
                               specs_collection_day_id=str(day_id)),
                actor=actor,
            )
            day = await mock_db.specs_collection_days.find_one({"_id": day_id})
            assert day["seats_taken"] == 0
            res = await record_fulfilment(
                FulfilmentBody(transcription_id=str(t_a), item_type="specs", status="deferred",
                               specs_collection_day_id=str(day_id)),
                actor=actor,
            )
            assert res["slip"]["active"] is True
            day = await mock_db.specs_collection_days.find_one({"_id": day_id})
            assert day["seats_taken"] == 1
            with pytest.raises(HTTPException) as exc:
                await record_fulfilment(
                    FulfilmentBody(transcription_id=str(t_b), item_type="specs", status="deferred",
                                   specs_collection_day_id=str(day_id)),
                    actor=actor,
                )
            assert exc.value.status_code == 409
            day = await mock_db.specs_collection_days.find_one({"_id": day_id})
            assert day["seats_taken"] == 1
        asyncio.run(_run())

    def test_ot_deferral_atomic_seat_limit_and_overbooking_prevention(self, monkeypatch):
        async def _run():
            mock_db = setup_mock_db(monkeypatch)
            t_id = ObjectId()
            p_id = ObjectId()
            ot_day_id = ObjectId()
            
            await insert_seen_patient(mock_db, p_id)
            await mock_db.transcriptions.insert_one({"_id": t_id, "patient_id": p_id, "locked": False})
            await mock_db.ot_schedule_days.insert_one({
                "_id": ot_day_id,
                "camp_id": ObjectId(),
                "day_date": "2026-09-10",
                "venue": "Civil Hospital OT 1",
                "seat_limit": 1,
                "seats_taken": 0,
            })

            body1 = FulfilmentBody(
                transcription_id=str(t_id),
                item_type="ot",
                status="deferred",
                ot_schedule_day_id=str(ot_day_id)
            )
            res1 = await record_fulfilment(body1, actor={"_id": ObjectId(), "role": "doctor"})
            assert res1["fulfilment"]["status"] == "deferred"
            
            ot_day = await mock_db.ot_schedule_days.find_one({"_id": ot_day_id})
            assert ot_day["seats_taken"] == 1

            t_id2 = ObjectId()
            p_id2 = await insert_seen_patient(mock_db)
            await mock_db.transcriptions.insert_one({"_id": t_id2, "patient_id": p_id2, "locked": False})
            body2 = FulfilmentBody(
                transcription_id=str(t_id2),
                item_type="ot",
                status="deferred",
                ot_schedule_day_id=str(ot_day_id)
            )
            with pytest.raises(HTTPException) as exc:
                await record_fulfilment(body2, actor={"_id": ObjectId(), "role": "doctor"})
            assert exc.value.status_code == 409
            assert "OT day is full" in exc.value.detail
        asyncio.run(_run())

    def test_ot_rebooking_releases_prior_seat(self, monkeypatch):
        async def _run():
            mock_db = setup_mock_db(monkeypatch)
            t_id = ObjectId()
            p_id = ObjectId()
            ot_day1 = ObjectId()
            ot_day2 = ObjectId()
            
            await insert_seen_patient(mock_db, p_id)
            await mock_db.transcriptions.insert_one({"_id": t_id, "patient_id": p_id, "locked": False})
            await mock_db.ot_schedule_days.insert_one({
                "_id": ot_day1, "camp_id": ObjectId(), "day_date": "2026-09-10", "venue": "OT 1", "seat_limit": 5, "seats_taken": 0
            })
            await mock_db.ot_schedule_days.insert_one({
                "_id": ot_day2, "camp_id": ObjectId(), "day_date": "2026-09-11", "venue": "OT 2", "seat_limit": 5, "seats_taken": 0
            })

            body1 = FulfilmentBody(transcription_id=str(t_id), item_type="ot", status="deferred", ot_schedule_day_id=str(ot_day1))
            await record_fulfilment(body1, actor={"_id": ObjectId(), "role": "doctor"})
            
            d1 = await mock_db.ot_schedule_days.find_one({"_id": ot_day1})
            assert d1["seats_taken"] == 1

            body2 = FulfilmentBody(transcription_id=str(t_id), item_type="ot", status="deferred", ot_schedule_day_id=str(ot_day2))
            await record_fulfilment(body2, actor={"_id": ObjectId(), "role": "doctor"})

            d1_after = await mock_db.ot_schedule_days.find_one({"_id": ot_day1})
            d2_after = await mock_db.ot_schedule_days.find_one({"_id": ot_day2})
            assert d1_after["seats_taken"] == 0
            assert d2_after["seats_taken"] == 1
        asyncio.run(_run())

    def test_concurrent_ot_seat_race_exactly_one_winner(self, monkeypatch):
        async def _run():
            mock_db = setup_mock_db(monkeypatch)
            ot_day_id = ObjectId()
            await mock_db.ot_schedule_days.insert_one({
                "_id": ot_day_id,
                "camp_id": ObjectId(),
                "day_date": "2026-09-10",
                "venue": "OT 1",
                "seat_limit": 1,
                "seats_taken": 0,
            })

            trans_ids = []
            for i in range(10):
                tid = ObjectId()
                pid = await insert_seen_patient(mock_db)
                await mock_db.transcriptions.insert_one({"_id": tid, "patient_id": pid, "locked": False})
                trans_ids.append(tid)

            async def attempt_booking(t_id):
                body = FulfilmentBody(
                    transcription_id=str(t_id),
                    item_type="ot",
                    status="deferred",
                    ot_schedule_day_id=str(ot_day_id)
                )
                try:
                    await record_fulfilment(body, actor={"_id": ObjectId(), "role": "doctor"})
                    return "SUCCESS"
                except HTTPException as e:
                    return f"FAIL_{e.status_code}"

            results = await asyncio.gather(*[attempt_booking(tid) for tid in trans_ids])
            
            success_count = sum(1 for r in results if r == "SUCCESS")
            fail_409_count = sum(1 for r in results if r == "FAIL_409")

            assert success_count == 1, f"Expected exactly 1 winner, got {success_count}"
            assert fail_409_count == 9, f"Expected 9 409 failures, got {fail_409_count}"

            ot_day = await mock_db.ot_schedule_days.find_one({"_id": ot_day_id})
            assert ot_day["seats_taken"] == 1
        asyncio.run(_run())
