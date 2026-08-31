"""SNP Camps backend regression suite.

Covers: health, auth (JWT/cookies/lockout), camps (one-active + print window),
registration (validation/idempotency/aadhaar mock), desk (print presence-once,
never_printed, PRINT_WINDOW_CLOSED), clinical (seen-only, transcription lock,
corrections, OT seats), staff management, reports/exports.
"""
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import requests

from conftest import API

TODAY_IST = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
TAG = uuid.uuid4().hex[:6]
STATE = {}


# ---------------- health ----------------
class TestHealth:
    def test_liveness(self, anon):
        r = anon.get(f"{API}/health", timeout=30)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_readiness(self, anon):
        r = anon.get(f"{API}/health/ready", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ready"] == True
        assert body["db"] == "reachable"


# ---------------- auth ----------------
class TestAuth:
    def test_login_success_sets_cookie(self, admin_credentials):
        r = requests.post(f"{API}/auth/login", json=admin_credentials, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["user"]["role"] == "admin"
        assert data["user"]["email"] == admin_credentials["email"]
        assert isinstance(data["access_token"], str) and len(data["access_token"]) > 20
        assert "access_token" in r.cookies, f"cookies={r.cookies.get_dict()}"
        # httpOnly flag present on Set-Cookie header
        raw = r.headers.get("set-cookie", "")
        assert "httponly" in raw.lower()

    def test_login_wrong_password(self, anon, admin_credentials):
        r = anon.post(f"{API}/auth/login",
                      json={"email": admin_credentials["email"], "password": "WrongPass@12345"},
                      timeout=30)
        assert r.status_code == 401, r.text

    def test_me_requires_auth(self, anon):
        r = requests.get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 401

    def test_me_with_bearer(self, admin):
        r = admin.get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "admin"

    def test_brute_force_lockout(self, anon):
        email = f"TEST_lock_{TAG}@snpcamps.org"
        codes = []
        for _ in range(6):
            r = anon.post(f"{API}/auth/login", json={"email": email, "password": "Nope@123456789"},
                          timeout=30)
            codes.append(r.status_code)
        assert codes[-1] == 429, f"expected lockout 429 after 5 fails, got {codes}"


# ---------------- camps ----------------
class TestCamps:
    def test_create_and_activate_camp(self, admin):
        r = admin.post(f"{API}/camps", json={"name": f"TEST_Camp_{TAG}", "venue": "TEST Venue",
                                             "camp_date": TODAY_IST}, timeout=30)
        assert r.status_code == 200, r.text
        camp = r.json()["camp"]
        assert camp["is_active"] == False
        STATE["camp_id"] = camp["id"]

        r = admin.post(f"{API}/camps/{camp['id']}/activate", timeout=30)
        assert r.status_code == 200, r.text
        r = admin.get(f"{API}/camps/active", timeout=30)
        assert r.json()["camp"]["id"] == camp["id"]

    def test_only_one_active_camp(self, admin):
        r = admin.post(f"{API}/camps", json={"name": f"TEST_Camp2_{TAG}", "venue": "V2",
                                             "camp_date": TODAY_IST}, timeout=30)
        second = r.json()["camp"]["id"]
        assert admin.post(f"{API}/camps/{second}/activate", timeout=30).status_code == 200
        camps = admin.get(f"{API}/camps", timeout=30).json()["camps"]
        active = [c for c in camps if c["is_active"]]
        assert len(active) == 1 and active[0]["id"] == second
        # re-activate the primary camp for the remaining flow
        assert admin.post(f"{API}/camps/{STATE['camp_id']}/activate", timeout=30).status_code == 200
        STATE["camp2_id"] = second

    def test_create_day_today_and_print_window(self, admin):
        r = admin.post(f"{API}/camps/days", json={"camp_id": STATE["camp_id"],
                                                  "day_date": TODAY_IST, "seat_limit": 50}, timeout=30)
        assert r.status_code == 200, r.text
        day = r.json()["day"]
        assert day["day_date"] == TODAY_IST
        assert day["is_today"] == True
        assert day["printing_open"] == False
        STATE["day_id"] = day["id"]

    def test_camp_endpoints_require_admin(self, anon):
        r = anon.post(f"{API}/camps", json={"name": "x", "venue": "y", "camp_date": TODAY_IST}, timeout=30)
        assert r.status_code in (401, 403)


# ---------------- aadhaar mock ----------------
class TestAadhaarMock:
    def test_decode_card(self, anon):
        payload = f"AADHAAR|TEST Ravi Kumar|M|1970-05-04|1234|12 Test Street, Chennai"
        r = anon.post(f"{API}/aadhaar/decode", json={"payload": payload}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["outcome"] == "card"
        d = body["data"]
        assert d["full_name"] == "TEST Ravi Kumar"
        assert d["gender"] == "M"
        assert d["aadhaar_last4"] == "1234"
        assert d["age"] and d["age"] > 50
        STATE["aadhaar"] = d

    def test_decode_garbage(self, anon):
        r = anon.post(f"{API}/aadhaar/decode", json={"payload": "hello world"}, timeout=30)
        assert r.json()["outcome"] == "garbage"

    def test_decode_patient_qr(self, anon):
        r = anon.post(f"{API}/aadhaar/decode", json={"payload": "snp:abc-123"}, timeout=30)
        assert r.json()["outcome"] == "not-aadhaar"

    def test_decode_empty(self, anon):
        r = anon.post(f"{API}/aadhaar/decode", json={"payload": ""}, timeout=30)
        assert r.json()["outcome"] == "not-aadhaar"


# ---------------- registration ----------------
class TestRegistration:
    def test_reject_dummy_phone(self, admin):
        r = admin.post(f"{API}/register", json={
            "full_name": f"TEST Dummy {TAG}", "age": 40, "phone": "9999999999",
            "camp_day_id": STATE["day_id"], "registration_request_id": str(uuid.uuid4()),
        }, timeout=30)
        assert r.status_code == 400, r.text

    def test_reject_empty_name(self, admin):
        r = admin.post(f"{API}/register", json={
            "full_name": "   ", "age": 40, "phone": "9876543210",
            "camp_day_id": STATE["day_id"],
        }, timeout=30)
        assert r.status_code in (400, 422), r.text

    def test_create_registration(self, admin):
        rid = str(uuid.uuid4())
        STATE["req_id"] = rid
        r = admin.post(f"{API}/register", json={
            "full_name": f"TESTPATIENT Alpha {TAG}", "age": 55, "gender": "M",
            "phone": "9876543210", "camp_day_id": STATE["day_id"],
            "registration_request_id": rid,
        }, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["created"] == True
        reg = body["registration"]
        assert "_id" not in reg and isinstance(reg["id"], str)
        assert reg["queue_status"] == "registered"
        assert reg["printed_at"] is None
        assert reg["patient_qr"]
        assert isinstance(reg["reg_no"], int)
        STATE["p1"] = reg

        # verify persistence via list
        pts = admin.get(f"{API}/patients", timeout=30).json()["patients"]
        assert any(p["id"] == reg["id"] for p in pts)

    def test_idempotent_registration(self, admin):
        r = admin.post(f"{API}/register", json={
            "full_name": f"TESTPATIENT Alpha {TAG}", "age": 55, "gender": "M",
            "phone": "9876543210", "camp_day_id": STATE["day_id"],
            "registration_request_id": STATE["req_id"],
        }, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["created"] == False
        assert body["registration"]["reg_no"] == STATE["p1"]["reg_no"]

    def test_name_search_prefix(self, admin):
        r = admin.get(f"{API}/patients/search", params={"q": "TESTPATIENT"}, timeout=30)
        assert r.status_code == 200, r.text
        results = r.json()["results"]
        assert any(x["id"] == STATE["p1"]["id"] for x in results)

    def test_duplicate_check(self, admin):
        r = admin.post(f"{API}/register/duplicate-check",
                       json={"full_name": f"TESTPATIENT Alpha {TAG}", "age": 55}, timeout=30)
        assert r.status_code == 200, r.text
        assert len(r.json()["likely_duplicates"]) >= 1

    def test_second_registration_for_clinical_flow(self, admin):
        r = admin.post(f"{API}/register", json={
            "full_name": f"TESTPATIENT Beta {TAG}", "age": 62, "gender": "F",
            "phone": "9812345670", "camp_day_id": STATE["day_id"],
            "registration_request_id": str(uuid.uuid4()),
        }, timeout=30)
        assert r.status_code == 200, r.text
        STATE["p2"] = r.json()["registration"]

    def test_self_register_requires_aadhaar(self, anon):
        r = anon.post(f"{API}/self-register", json={
            "full_name": "TEST Self NoScan", "age": 30, "camp_day_id": STATE["day_id"],
        }, timeout=30)
        assert r.status_code == 400, r.text

    def test_self_register_with_aadhaar_returns_receipt(self, anon):
        d = STATE["aadhaar"]
        r = anon.post(f"{API}/self-register", json={
            "full_name": f"TESTSELF {TAG}", "gender": d["gender"], "dob": d["dob"],
            "age": d["age"], "address": d["address"], "aadhaar_last4": "4321",
            "aadhaar_scanned": True, "camp_day_id": STATE["day_id"],
            "registration_request_id": str(uuid.uuid4()),
        }, timeout=30)
        assert r.status_code == 200, r.text
        receipt = r.json()["receipt"]
        assert isinstance(receipt["reg_no"], int)
        assert receipt["patient_qr"]
        assert receipt["day_date"] == TODAY_IST
        STATE["p_self"] = r.json()["registration"]

    def test_register_requires_auth(self, anon):
        r = anon.post(f"{API}/register", json={"full_name": "TEST x", "age": 20,
                                               "camp_day_id": STATE["day_id"]}, timeout=30)
        assert r.status_code in (401, 403)


# ---------------- desk: print window / presence ----------------
class TestDeskPrintWindow:
    def test_print_blocked_when_window_closed(self, admin):
        r = admin.post(f"{API}/desk/print/{STATE['p1']['id']}", timeout=30)
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "PRINT_WINDOW_CLOSED"

    def test_mark_seen_refused_when_never_printed(self, admin):
        r = admin.post(f"{API}/desk/mark-seen/{STATE['p1']['id']}", timeout=30)
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "never_printed"

    def test_open_print_window(self, admin):
        r = admin.patch(f"{API}/camps/days/{STATE['day_id']}/print-window",
                        json={"printing_open": True}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["day"]["printing_open"] == True

    def test_print_records_presence_once(self, admin):
        r = admin.post(f"{API}/desk/print/{STATE['p1']['id']}", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        first_printed = body["registration"]["printed_at"]
        assert first_printed
        pres = body["prescription"]
        assert pres["reg_no"] == STATE["p1"]["reg_no"]
        assert pres["patient_qr"] == STATE["p1"]["patient_qr"]
        assert pres["date"] == TODAY_IST

        # idempotent: printed_at unchanged on reprint
        r2 = admin.post(f"{API}/desk/print/{STATE['p1']['id']}", timeout=30)
        assert r2.status_code == 200
        assert r2.json()["registration"]["printed_at"] == first_printed

    def test_lookup_by_reg_no_and_qr(self, admin):
        r = admin.post(f"{API}/desk/lookup", json={"value": str(STATE["p1"]["reg_no"])}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["registration"]["id"] == STATE["p1"]["id"]

        r = admin.post(f"{API}/desk/lookup", json={"value": f"snp:{STATE['p1']['patient_qr']}"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["registration"]["id"] == STATE["p1"]["id"]

    def test_lookup_unknown_404(self, admin):
        r = admin.post(f"{API}/desk/lookup", json={"value": "99999999"}, timeout=30)
        assert r.status_code == 404

    def test_mark_seen_and_idempotency(self, admin):
        r = admin.post(f"{API}/desk/mark-seen/{STATE['p1']['id']}", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["changed"] == True
        assert body["registration"]["queue_status"] == "seen"
        assert body["registration"]["seen_at"]

        r2 = admin.post(f"{API}/desk/mark-seen/{STATE['p1']['id']}", timeout=30)
        assert r2.status_code == 200
        assert r2.json()["changed"] == False

    def test_undo_seen_within_window(self, admin):
        r = admin.post(f"{API}/desk/undo-seen/{STATE['p1']['id']}", timeout=30)
        assert r.status_code == 200, f"undo-seen failed: {r.status_code} {r.text[:300]}"
        assert r.json()["registration"]["queue_status"] == "registered"
        # re-mark seen for downstream clinical tests
        r = admin.post(f"{API}/desk/mark-seen/{STATE['p1']['id']}", timeout=30)
        assert r.status_code == 200, r.text

    def test_undo_seen_on_not_seen_patient(self, admin):
        r = admin.post(f"{API}/desk/undo-seen/{STATE['p2']['id']}", timeout=30)
        assert r.status_code == 409, r.text


# ---------------- clinical ----------------
class TestClinical:
    def test_lookup_not_seen_refusal_no_phi(self, admin):
        r = admin.post(f"{API}/clinical/lookup", json={"value": str(STATE["p2"]["reg_no"])}, timeout=30)
        assert r.status_code == 409, r.text
        detail = r.json()["detail"]
        assert detail["code"] == "not_seen"
        assert STATE["p2"]["full_name"] not in r.text

    def test_lookup_seen_ok(self, admin):
        r = admin.post(f"{API}/clinical/lookup", json={"value": str(STATE["p1"]["reg_no"])}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["registration"]["queue_status"] == "seen"
        assert body["transcription"] is None

    def test_diagnosis_options(self, admin):
        r = admin.get(f"{API}/clinical/diagnosis-options", timeout=30)
        assert r.status_code == 200
        assert "Cataract" in r.json()["options"]

    def test_transcription_requires_seen(self, admin):
        r = admin.post(f"{API}/clinical/transcription", json={
            "patient_id": STATE["p2"]["id"], "diagnosis_options": ["Cataract"],
        }, timeout=30)
        assert r.status_code == 409, r.text

    def test_create_transcription(self, admin):
        r = admin.post(f"{API}/clinical/transcription", json={
            "patient_id": STATE["p1"]["id"], "diagnosis_options": ["Cataract", "Presbyopia"],
            "bp": "130/85", "blood_sugar": "110", "remarks": "TEST remarks",
            "ot_eye": "right", "ot_procedure": "Cataract Surgery",
        }, timeout=30)
        assert r.status_code == 200, r.text
        t = r.json()["transcription"]
        assert t["locked"] == False
        assert t["diagnosis_options"] == ["Cataract", "Presbyopia"]
        assert t["bp"] == "130/85"
        STATE["trans_id"] = t["id"]

        # verify persisted via lookup
        r = admin.post(f"{API}/clinical/lookup", json={"value": str(STATE["p1"]["reg_no"])}, timeout=30)
        assert r.json()["transcription"]["id"] == t["id"]

    def test_edit_transcription_before_lock(self, admin):
        r = admin.post(f"{API}/clinical/transcription", json={
            "patient_id": STATE["p1"]["id"], "diagnosis_options": ["Cataract"],
            "bp": "120/80", "ot_eye": "left", "ot_procedure": "Cataract Surgery",
        }, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["transcription"]["bp"] == "120/80"
        assert r.json()["transcription"]["locked"] == False

    def test_create_ot_day(self, admin):
        r = admin.post(f"{API}/clinical/ot-days", json={
            "camp_id": STATE["camp_id"], "day_date": "2026-12-01",
            "venue": "TEST OT Hospital", "seat_limit": 1,
        }, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()["ot_day"]
        assert d["seat_limit"] == 1 and d["seats_taken"] == 0 and d["seats_free"] == 1
        STATE["ot_day_id"] = d["id"]

    def test_create_list_upsert_specs_collection_days(self, admin):
        r = admin.post(f"{API}/clinical/specs-days", json={
            "camp_id": STATE["camp_id"], "day_date": "2026-12-05",
            "venue": "TEST Optical", "seat_limit": 1,
        }, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()["specs_day"]
        assert d["seat_limit"] == 1 and d["seats_taken"] == 0 and d["seats_free"] == 1
        assert d["day_date"] == "2026-12-05"
        STATE["specs_day_id"] = d["id"]

        listed = admin.get(f"{API}/clinical/specs-days", timeout=30).json()["specs_days"]
        assert any(x["id"] == d["id"] and x["seats_free"] == 1 for x in listed)

        r = admin.post(f"{API}/clinical/specs-days", json={
            "camp_id": STATE["camp_id"], "day_date": "2026-12-05",
            "venue": "TEST Optical Hall", "seat_limit": 1,
        }, timeout=30)
        assert r.status_code == 200, r.text
        up = r.json()["specs_day"]
        assert up["id"] == d["id"]
        assert up["venue"] == "TEST Optical Hall"
        STATE["specs_day_venue"] = "TEST Optical Hall"

    def test_medicine_fulfilment_locks_transcription(self, admin):
        r = admin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": STATE["trans_id"], "item_type": "medicine", "status": "fulfilled",
        }, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["fulfilment"]["status"] == "fulfilled"
        assert r.json()["slip"] is None

        r = admin.post(f"{API}/clinical/lookup", json={"value": str(STATE["p1"]["reg_no"])}, timeout=30)
        assert r.json()["transcription"]["locked"] == True

    def test_transcription_edit_blocked_after_lock(self, admin):
        r = admin.post(f"{API}/clinical/transcription", json={
            "patient_id": STATE["p1"]["id"], "diagnosis_options": ["Glaucoma"],
        }, timeout=30)
        assert r.status_code == 409, r.text

    def test_invalid_fulfilment_status(self, admin):
        r = admin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": STATE["trans_id"], "item_type": "medicine", "status": "deferred",
        }, timeout=30)
        assert r.status_code == 400, r.text

    def test_specs_deferral_requires_day_id(self, admin):
        r = admin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": STATE["trans_id"], "item_type": "specs", "status": "deferred",
        }, timeout=30)
        assert r.status_code == 400, r.text

        r = admin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": STATE["trans_id"], "item_type": "specs", "status": "deferred",
            "collection_date": "2026-12-05", "collection_venue": "TEST Optical",
        }, timeout=30)
        assert r.status_code == 400, r.text

    def test_specs_deferral_consumes_seat_and_prints_token(self, admin):
        r = admin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": STATE["trans_id"], "item_type": "specs", "status": "deferred",
            "specs_collection_day_id": STATE["specs_day_id"],
        }, timeout=30)
        assert r.status_code == 200, r.text
        slip = r.json()["slip"]
        assert slip["item_type"] == "specs"
        assert slip["collection_date"] == "2026-12-05"
        assert slip["collection_venue"] == STATE["specs_day_venue"]
        assert slip["active"] == True
        STATE["specs_slip_id"] = slip["id"]

        days = admin.get(f"{API}/clinical/specs-days", timeout=30).json()["specs_days"]
        day = next(d for d in days if d["id"] == STATE["specs_day_id"])
        assert day["seats_taken"] == 1
        assert day["seats_free"] == 0

    def test_specs_seat_limit_below_assigned(self, admin):
        r = admin.post(f"{API}/clinical/specs-days", json={
            "camp_id": STATE["camp_id"], "day_date": "2026-12-05",
            "venue": "TEST Optical Hall", "seat_limit": 0,
        }, timeout=30)
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "SEAT_LIMIT_BELOW_ASSIGNED"

    def test_ot_deferral_consumes_seat_and_prints_slip(self, admin):
        r = admin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": STATE["trans_id"], "item_type": "ot", "status": "deferred",
            "ot_schedule_day_id": STATE["ot_day_id"],
        }, timeout=30)
        assert r.status_code == 200, r.text
        slip = r.json()["slip"]
        assert slip["item_type"] == "ot"
        assert slip["collection_date"] == "2026-12-01"
        STATE["ot_slip_id"] = slip["id"]

        days = admin.get(f"{API}/clinical/ot-days", timeout=30).json()["ot_days"]
        day = next(d for d in days if d["id"] == STATE["ot_day_id"])
        assert day["seats_taken"] == 1
        assert day["seats_free"] == 0

        looked = admin.post(f"{API}/clinical/lookup", json={"value": str(STATE["p1"]["reg_no"])}, timeout=30)
        active = [s for s in looked.json()["slips"] if s.get("active")]
        assert {s["item_type"] for s in active} == {"ot", "specs"}

    def test_seat_limit_below_assigned(self, admin):
        r = admin.post(f"{API}/clinical/ot-days", json={
            "camp_id": STATE["camp_id"], "day_date": "2026-12-01",
            "venue": "TEST OT Hospital", "seat_limit": 0,
        }, timeout=30)
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "SEAT_LIMIT_BELOW_ASSIGNED"

    def test_ot_day_full_rejects_further_deferral(self, admin):
        # print + mark seen p2 then transcribe and try to defer to the full OT day
        assert admin.post(f"{API}/desk/print/{STATE['p2']['id']}", timeout=30).status_code == 200
        assert admin.post(f"{API}/desk/mark-seen/{STATE['p2']['id']}", timeout=30).status_code == 200
        r = admin.post(f"{API}/clinical/transcription", json={
            "patient_id": STATE["p2"]["id"], "diagnosis_options": ["Cataract"],
        }, timeout=30)
        assert r.status_code == 200, r.text
        t2 = r.json()["transcription"]["id"]
        STATE["trans2_id"] = t2
        r = admin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": t2, "item_type": "ot", "status": "deferred",
            "ot_schedule_day_id": STATE["ot_day_id"],
        }, timeout=30)
        assert r.status_code == 409, f"expected full-day refusal, got {r.status_code}: {r.text[:200]}"

    def test_specs_day_full_rejects_further_deferral(self, admin):
        r = admin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": STATE["trans2_id"], "item_type": "specs", "status": "deferred",
            "specs_collection_day_id": STATE["specs_day_id"],
        }, timeout=30)
        assert r.status_code == 409, f"expected full-day refusal, got {r.status_code}: {r.text[:200]}"

    def test_slip_fetch(self, admin):
        r = admin.get(f"{API}/clinical/slip/{STATE['ot_slip_id']}", timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["slip"]["item_type"] == "ot"
        assert r.json()["registration"]["reg_no"] == STATE["p1"]["reg_no"]

    def test_correction_append_only(self, admin):
        r = admin.post(f"{API}/clinical/correction", json={
            "transcription_id": STATE["trans_id"], "reason": "TEST typo in BP",
            "changes": {"bp": "140/90"},
        }, timeout=30)
        assert r.status_code == 200, r.text
        r = admin.get(f"{API}/clinical/corrections/{STATE['trans_id']}", timeout=30)
        assert r.status_code == 200
        corr = r.json()["corrections"]
        assert len(corr) == 1
        assert corr[0]["reason"] == "TEST typo in BP"
        # change applied
        r = admin.post(f"{API}/clinical/lookup", json={"value": str(STATE["p1"]["reg_no"])}, timeout=30)
        assert r.json()["transcription"]["bp"] == "140/90"

    def test_undo_seen_blocked_after_transcription(self, admin):
        r = admin.post(f"{API}/desk/undo-seen/{STATE['p1']['id']}", timeout=30)
        assert r.status_code == 409, f"expected block, got {r.status_code}: {r.text[:200]}"

    def test_history_by_person(self, admin):
        # p_self has a person_id (aadhaar scanned)
        r = admin.post(f"{API}/desk/lookup", json={"value": str(STATE["p_self"]["reg_no"])}, timeout=30)
        assert r.status_code == 200
        person_id = r.json()["registration"].get("person_id")
        if not person_id:
            pytest.skip("no person_id on self-registered patient")
        r = admin.get(f"{API}/clinical/history/{person_id}", timeout=30)
        assert r.status_code == 200, r.text
        assert isinstance(r.json()["history"], list)


# ---------------- staff ----------------
class TestStaff:
    def test_password_policy(self, admin):
        r = admin.post(f"{API}/staff", json={
            "email": f"TEST_weak_{TAG}@snpcamps.org", "password": "short1A!",
            "name": "TEST Weak", "role": "volunteer",
        }, timeout=30)
        assert r.status_code == 400, r.text

    def test_create_volunteer_team_lead_clinical(self, admin):
        accounts = [
            ("volunteer", f"TEST_vol_{TAG}@snpcamps.org", "VolunteerPass@1"),
            ("team_lead", f"TEST_lead_{TAG}@snpcamps.org", "TeamLeadPass@1"),
            ("clinical_desk_operator", f"TEST_clin_{TAG}@snpcamps.org", "ClinicalPass@1"),
        ]
        for role, email, pwd in accounts:
            r = admin.post(f"{API}/staff", json={"email": email, "password": pwd,
                                                 "name": f"TEST {role}", "role": role}, timeout=30)
            assert r.status_code == 200, f"{role}: {r.text}"
            assert r.json()["staff"]["role"] == role
            STATE[role] = {"email": email, "password": pwd, "id": r.json()["staff"]["id"]}

        # duplicate email
        r = admin.post(f"{API}/staff", json={"email": accounts[0][1], "password": accounts[0][2],
                                             "name": "dup", "role": "volunteer"}, timeout=30)
        assert r.status_code == 409, r.text

    def test_invalid_role(self, admin):
        r = admin.post(f"{API}/staff", json={"email": f"TEST_bad_{TAG}@x.org",
                                             "password": "GoodPass@12345", "name": "x",
                                             "role": "superuser"}, timeout=30)
        assert r.status_code in (400, 422), r.text

    def test_team_lead_can_only_create_volunteers(self, anon):
        lead = STATE["team_lead"]
        r = anon.post(f"{API}/auth/login", json={"email": lead["email"], "password": lead["password"]},
                      timeout=30)
        assert r.status_code == 200, r.text
        tok = r.json()["access_token"]
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {tok}"})
        r = s.post(f"{API}/staff", json={"email": f"TEST_admin2_{TAG}@x.org",
                                         "password": "GoodPass@12345", "name": "x", "role": "admin"},
                   timeout=30)
        assert r.status_code == 403, r.text
        r = s.post(f"{API}/staff", json={"email": f"TEST_vol2_{TAG}@x.org",
                                         "password": "GoodPass@12345", "name": "TEST vol2",
                                         "role": "volunteer"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["staff"]["team_lead_id"] == str(STATE["team_lead"]["id"])

    def test_clinical_operator_cannot_register_or_print(self, anon):
        c = STATE["clinical_desk_operator"]
        r = anon.post(f"{API}/auth/login", json={"email": c["email"], "password": c["password"]}, timeout=30)
        assert r.status_code == 200, r.text
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
        assert s.post(f"{API}/desk/print/{STATE['p1']['id']}", timeout=30).status_code == 403
        # but clinical lookup works
        r = s.post(f"{API}/clinical/lookup", json={"value": str(STATE["p1"]["reg_no"])}, timeout=30)
        assert r.status_code == 200, r.text

    def test_volunteer_cannot_access_clinical(self, anon):
        v = STATE["volunteer"]
        r = anon.post(f"{API}/auth/login", json={"email": v["email"], "password": v["password"]}, timeout=30)
        assert r.status_code == 200, r.text
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
        r = s.post(f"{API}/clinical/lookup", json={"value": str(STATE["p1"]["reg_no"])}, timeout=30)
        assert r.status_code == 403, r.text

    def test_disable_then_enable_staff(self, admin, anon):
        v = STATE["volunteer"]
        assert admin.patch(f"{API}/staff/{v['id']}/disable", timeout=30).status_code == 200
        r = anon.post(f"{API}/auth/login", json={"email": v["email"], "password": v["password"]}, timeout=30)
        assert r.status_code == 403, f"disabled account still logs in: {r.status_code}"
        assert admin.patch(f"{API}/staff/{v['id']}/enable", timeout=30).status_code == 200
        r = anon.post(f"{API}/auth/login", json={"email": v["email"], "password": v["password"]}, timeout=30)
        assert r.status_code == 200, r.text

    def test_list_staff(self, admin):
        r = admin.get(f"{API}/staff", timeout=30)
        assert r.status_code == 200
        emails = [u["email"] for u in r.json()["staff"]]
        assert STATE["volunteer"]["email"].lower() in emails


# ---------------- reports ----------------
class TestReports:
    def test_kpis(self, admin):
        r = admin.get(f"{API}/kpis", timeout=30)
        assert r.status_code == 200, r.text
        k = r.json()
        assert k["active_camp"]["id"] == STATE["camp_id"]
        assert k["registered"] >= 3
        assert k["seen"] >= 2
        assert k["pending"] == k["registered"] - k["seen"]

    def test_leaderboard(self, admin):
        r = admin.get(f"{API}/leaderboard", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body["volunteers"], list)
        assert isinstance(body["team_leads"], list)

    def test_export_camp_records(self, admin):
        r = admin.get(f"{API}/exports/camp-records", timeout=60)
        assert r.status_code == 200, r.text
        assert "text/csv" in r.headers.get("content-type", "")
        assert "reg_no,full_name" in r.text
        assert str(STATE["p1"]["reg_no"]) in r.text

    def test_export_clinical_audit(self, admin):
        r = admin.get(f"{API}/exports/clinical-audit", timeout=60)
        assert r.status_code == 200, r.text
        assert "event,transcription_id" in r.text
        assert "transcription" in r.text

    def test_exports_require_admin(self, anon):
        c = STATE["clinical_desk_operator"]
        r = anon.post(f"{API}/auth/login", json={"email": c["email"], "password": c["password"]}, timeout=30)
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
        assert s.get(f"{API}/exports/camp-records", timeout=30).status_code == 403


# ---------------- iteration-2 fix regressions ----------------
class TestFixRegressions:
    """Targeted checks for the iteration-1 defects that were fixed."""

    # public unauthenticated active-camp endpoint used by /self-register
    def test_public_active_camp_no_auth(self, anon):
        r = anon.get(f"{API}/camps/active/public", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["camp"]["id"] == STATE["camp_id"]
        assert body["camp"]["venue"] == "TEST Venue"
        # today's camp day must be exposed for the public form
        blob = str(body)
        assert STATE["day_id"] in blob, body
        assert TODAY_IST in blob, body
        # no PHI leakage
        assert "patients" not in body
        assert "_id" not in blob

    # desk registration requires a valid 10-digit household phone
    def test_register_missing_phone_rejected(self, admin):
        r = admin.post(f"{API}/register", json={
            "full_name": f"TEST NoPhone {TAG}", "age": 33,
            "camp_day_id": STATE["day_id"], "registration_request_id": str(uuid.uuid4()),
        }, timeout=30)
        assert r.status_code == 400, r.text
        assert "10-digit" in r.text.lower() or "phone" in r.text.lower(), r.text

    def test_register_short_phone_rejected(self, admin):
        r = admin.post(f"{API}/register", json={
            "full_name": f"TEST ShortPhone {TAG}", "age": 33, "phone": "98765",
            "camp_day_id": STATE["day_id"], "registration_request_id": str(uuid.uuid4()),
        }, timeout=30)
        assert r.status_code == 400, r.text

    # undo-seen keeps printed_at (presence recorded once)
    def test_undo_seen_keeps_printed_at(self, admin):
        rid = str(uuid.uuid4())
        r = admin.post(f"{API}/register", json={
            "full_name": f"TESTUNDO Gamma {TAG}", "age": 44, "gender": "M",
            "phone": "9876500011", "camp_day_id": STATE["day_id"],
            "registration_request_id": rid,
        }, timeout=30)
        assert r.status_code == 200, r.text
        pid = r.json()["registration"]["id"]
        pr = admin.post(f"{API}/desk/print/{pid}", timeout=30)
        assert pr.status_code == 200, pr.text
        printed_at = pr.json()["registration"]["printed_at"]
        assert printed_at
        assert admin.post(f"{API}/desk/mark-seen/{pid}", timeout=30).status_code == 200
        u = admin.post(f"{API}/desk/undo-seen/{pid}", timeout=30)
        assert u.status_code == 200, f"{u.status_code} {u.text[:300]}"
        reg = u.json()["registration"]
        assert reg["queue_status"] == "registered"
        assert reg["printed_at"] == printed_at, "presence (printed_at) must be preserved on undo"
        assert reg.get("seen_at") in (None, "")
        # verify persisted
        g = admin.post(f"{API}/desk/lookup", json={"value": str(reg["reg_no"])}, timeout=30)
        assert g.json()["registration"]["queue_status"] == "registered"
        assert g.json()["registration"]["printed_at"] == printed_at
        STATE["p_undo"] = reg

    # OT seat must be released when an OT deferral is re-recorded on another day
    def test_ot_seat_released_on_rerecord(self, admin):
        # two OT days with free seats
        a = admin.post(f"{API}/clinical/ot-days", json={
            "camp_id": STATE["camp_id"], "day_date": "2026-12-18",
            "venue": "TEST OT A", "seat_limit": 3}, timeout=30)
        b = admin.post(f"{API}/clinical/ot-days", json={
            "camp_id": STATE["camp_id"], "day_date": "2026-12-19",
            "venue": "TEST OT B", "seat_limit": 3}, timeout=30)
        assert a.status_code == 200 and b.status_code == 200, (a.text, b.text)
        day_a, day_b = a.json()["ot_day"]["id"], b.json()["ot_day"]["id"]

        t2 = STATE["trans2_id"]
        r = admin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": t2, "item_type": "ot", "status": "deferred",
            "ot_schedule_day_id": day_a}, timeout=30)
        assert r.status_code == 200, r.text

        def seats(day_id):
            days = admin.get(f"{API}/clinical/ot-days", timeout=30).json()["ot_days"]
            return next(d for d in days if d["id"] == day_id)["seats_taken"]

        assert seats(day_a) == 1
        # re-record on day B -> day A seat must be released
        r = admin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": t2, "item_type": "ot", "status": "deferred",
            "ot_schedule_day_id": day_b}, timeout=30)
        assert r.status_code == 200, r.text
        assert seats(day_b) == 1, "new day should hold the seat"
        assert seats(day_a) == 0, "previous OT day seat leaked (not released)"

    def test_specs_seat_released_on_rerecord_and_fulfilment(self, admin):
        a = admin.post(f"{API}/clinical/specs-days", json={
            "camp_id": STATE["camp_id"], "day_date": "2026-12-18",
            "venue": "TEST Specs A", "seat_limit": 3}, timeout=30)
        b = admin.post(f"{API}/clinical/specs-days", json={
            "camp_id": STATE["camp_id"], "day_date": "2026-12-19",
            "venue": "TEST Specs B", "seat_limit": 3}, timeout=30)
        assert a.status_code == 200 and b.status_code == 200, (a.text, b.text)
        day_a, day_b = a.json()["specs_day"]["id"], b.json()["specs_day"]["id"]

        t2 = STATE["trans2_id"]
        r = admin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": t2, "item_type": "specs", "status": "deferred",
            "specs_collection_day_id": day_a}, timeout=30)
        assert r.status_code == 200, r.text

        def seats(day_id):
            days = admin.get(f"{API}/clinical/specs-days", timeout=30).json()["specs_days"]
            return next(d for d in days if d["id"] == day_id)["seats_taken"]

        assert seats(day_a) == 1
        r = admin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": t2, "item_type": "specs", "status": "deferred",
            "specs_collection_day_id": day_b}, timeout=30)
        assert r.status_code == 200, r.text
        assert seats(day_b) == 1, "new day should hold the seat"
        assert seats(day_a) == 0, "previous Specs collection day seat leaked (not released)"

        r = admin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": t2, "item_type": "specs", "status": "fulfilled"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["slip"] is None
        assert seats(day_b) == 0, "fulfilled must release the Specs collection day seat"
        looked = admin.post(f"{API}/clinical/lookup", json={"value": str(STATE["p2"]["reg_no"])}, timeout=30)
        assert looked.status_code == 200, looked.text
        active_specs = [s for s in looked.json()["slips"] if s.get("active") and s["item_type"] == "specs"]
        assert active_specs == [], "fulfilled must cancel the Specs Token"

    def test_specs_fulfil_then_redefer_consumes_and_full_day_409(self, admin):
        c = admin.post(f"{API}/clinical/specs-days", json={
            "camp_id": STATE["camp_id"], "day_date": "2026-12-22",
            "venue": "TEST Specs C", "seat_limit": 1}, timeout=30)
        assert c.status_code == 200, c.text
        day_c = c.json()["specs_day"]["id"]
        t2 = STATE["trans2_id"]

        r = admin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": t2, "item_type": "specs", "status": "deferred",
            "specs_collection_day_id": day_c}, timeout=30)
        assert r.status_code == 200, r.text

        r = admin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": t2, "item_type": "specs", "status": "fulfilled",
            "specs_collection_day_id": day_c}, timeout=30)
        assert r.status_code == 200, r.text

        def seats():
            days = admin.get(f"{API}/clinical/specs-days", timeout=30).json()["specs_days"]
            return next(d for d in days if d["id"] == day_c)["seats_taken"]

        assert seats() == 0
        r = admin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": t2, "item_type": "specs", "status": "deferred",
            "specs_collection_day_id": day_c}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["slip"]["active"] is True
        assert seats() == 1, "re-defer after fulfil must consume a seat"
        r = admin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": STATE["trans_id"], "item_type": "specs", "status": "deferred",
            "specs_collection_day_id": day_c}, timeout=30)
        assert r.status_code == 409, f"expected full-day refusal, got {r.status_code}: {r.text[:200]}"
        assert seats() == 1

    # lockout is keyed on email and returns 429 (proxy-safe)
    def test_lockout_returns_429_and_is_email_keyed(self, anon):
        email = f"TEST_lock2_{TAG}@snpcamps.org"
        codes = []
        for _ in range(7):
            codes.append(anon.post(f"{API}/auth/login",
                                   json={"email": email, "password": "Nope@123456789"},
                                   timeout=30).status_code)
        assert 500 not in codes, codes
        assert codes[:5] == [401] * 5, codes
        assert codes[5] == 429 and codes[6] == 429, codes
        # a different email is unaffected
        other = anon.post(f"{API}/auth/login",
                          json={"email": f"TEST_other_{TAG}@snpcamps.org",
                                "password": "Nope@123456789"}, timeout=30)
        assert other.status_code == 401, other.status_code

    def test_locked_admin_not_affected(self, admin_credentials, anon):
        r = anon.post(f"{API}/auth/login", json=admin_credentials, timeout=30)
        assert r.status_code == 200, r.text


# ---------------- cleanup ----------------
def test_zz_state_left_usable(admin):
    """Leave the test camp active + print window open for UI testing."""
    r = admin.get(f"{API}/camps/active", timeout=30)
    assert r.status_code == 200
    assert r.json()["camp"]["id"] == STATE["camp_id"]
    print("ACTIVE_CAMP", STATE["camp_id"], "DAY", STATE["day_id"],
          "P1_REG", STATE["p1"]["reg_no"], "P2_REG", STATE["p2"]["reg_no"])
