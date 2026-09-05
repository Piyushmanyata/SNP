"""SNP Camps backend regression suite.

Covers: health, auth (JWT/cookies/lockout), camps (one-active + print window),
registration (validation/idempotency/aadhaar mock), desk (print presence-once,
never_printed, PRINT_WINDOW_CLOSED), clinical (seen-only, transcription lock,
corrections, OT seats), staff management, reports/exports.
"""
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from xml.etree.ElementTree import Element, tostring

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
        assert data["user"]["name"].lower() == admin_credentials["name"].lower()
        assert isinstance(data["access_token"], str) and len(data["access_token"]) > 20
        assert "access_token" in r.cookies, f"cookies={r.cookies.get_dict()}"
        # httpOnly flag present on Set-Cookie header
        raw = r.headers.get("set-cookie", "")
        assert "httponly" in raw.lower()

    def test_login_wrong_pin(self, anon, admin_credentials):
        r = anon.post(f"{API}/auth/login",
                      json={"name": admin_credentials["name"], "pin": "0000"},
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
        name = f"TEST_lock_{TAG}"
        codes = []
        for _ in range(6):
            r = anon.post(f"{API}/auth/login", json={"name": name, "pin": "0000"},
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
        assert day["printing_open"] == True
        STATE["day_id"] = day["id"]

    def test_camp_endpoints_require_admin(self, anon):
        r = anon.post(f"{API}/camps", json={"name": "x", "venue": "y", "camp_date": TODAY_IST}, timeout=30)
        assert r.status_code in (401, 403)


# ---------------- aadhaar mock ----------------
class TestAadhaarMock:
    def test_decode_card(self, anon):
        payload = '<PrintLetterBarcodeData name="TEST Ravi Kumar" gender="M" dob="1970-05-04" uid="1234" street="12 Test Street, Chennai"/>'
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
        assert reg["arrived_at"] is None
        assert reg["patient_qr"]
        assert isinstance(reg["reg_no"], int)
        STATE["p1"] = reg

        # verify persistence via lookup; there is no patient list on the desk
        found = admin.post(f"{API}/desk/lookup", json={"value": str(reg["reg_no"])}, timeout=30)
        assert found.status_code == 200, found.text
        assert found.json()["registration"]["id"] == reg["id"]

    def test_patient_list_endpoint_is_gone(self, admin):
        assert admin.get(f"{API}/patients", timeout=30).status_code == 404

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
            "phone": "9812345688",
            "aadhaar_scanned": True, "camp_day_id": STATE["day_id"],
            "registration_request_id": str(uuid.uuid4()),
            "qr_payload": tostring(Element(
                "PrintLetterBarcodeData", name=f"TESTSELF {TAG}", gender=d["gender"],
                dob=d["dob"], uid="4321", street=d["address"],
            ), encoding="unicode"),
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
RX_MEASUREMENTS = {
    "r_sph": "-1.00", "r_cyl": "-0.50", "r_axis": "90",
    "l_sph": "-1.25", "l_cyl": "-0.25", "l_axis": "85", "add": "+2.00",
}


class TestDeskPrintWindow:
    def test_print_blocked_before_arrival(self, admin):
        r = admin.post(f"{API}/desk/print/{STATE['p1']['id']}", timeout=30)
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "NOT_ARRIVED"

    def test_mark_seen_blocked_before_arrival(self, admin):
        r = admin.post(f"{API}/desk/mark-seen/{STATE['p1']['id']}", timeout=30)
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "completion_required"

    def test_arrival_stamps_presence(self, admin):
        r = admin.post(f"{API}/desk/arrive/{STATE['p1']['id']}", timeout=30)
        assert r.status_code == 200, r.text
        reg = r.json()["registration"]
        assert reg["arrived_at"]
        assert reg["queue_status"] == "arrived"

    def test_print_blocked_when_window_closed(self, admin):
        r = admin.patch(f"{API}/camps/days/{STATE['day_id']}/print-window",
                        json={"mode": "disable"}, timeout=30)
        assert r.status_code == 200, r.text
        r = admin.post(f"{API}/desk/print/{STATE['p1']['id']}", timeout=30)
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "PRINT_WINDOW_CLOSED"

    def test_mark_seen_refused_when_never_printed(self, admin):
        r = admin.post(f"{API}/desk/mark-seen/{STATE['p1']['id']}", timeout=30)
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "completion_required"

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
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "completion_required"
        looked = admin.post(f"{API}/desk/lookup", json={"value": str(STATE["p1"]["reg_no"])}, timeout=30)
        assert looked.json()["registration"]["queue_status"] != "seen"

    def test_undo_seen_within_window(self, admin):
        r = admin.post(f"{API}/desk/undo-seen/{STATE['p1']['id']}", timeout=30)
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "completion_required"

    def test_undo_seen_on_not_seen_patient(self, admin):
        r = admin.post(f"{API}/desk/undo-seen/{STATE['p2']['id']}", timeout=30)
        assert r.status_code == 409, r.text


def _clinical(admin):
    if "clinical_http" in STATE:
        return STATE["clinical_http"]
    name = f"TEST flow clinical {TAG}"
    created = admin.post(f"{API}/staff", json={"name": name, "role": "clinical_desk_operator"}, timeout=30)
    assert created.status_code == 200, created.text
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    logged = s.post(f"{API}/auth/login", json={"name": name, "pin": "1234"}, timeout=30)
    assert logged.status_code == 200, logged.text
    changed = s.post(f"{API}/auth/change-pin", json={"current_pin": "1234", "new_pin": "5678"}, timeout=30)
    assert changed.status_code == 200, changed.text
    logged = s.post(f"{API}/auth/login", json={"name": name, "pin": "5678"}, timeout=30)
    assert logged.status_code == 200, logged.text
    s.headers.update({"Authorization": f"Bearer {logged.json()['access_token']}"})
    STATE["clinical_http"] = s
    return s


def _complete_rx(client, patient_id, operation_id, **extra):
    payload = {
        "patient_id": patient_id,
        "full_transcription_confirmed": True,
        "prescribed_lines": ["medicine", "specs_fixed", "specs_made", "ot"],
        "operation_id": operation_id,
        "diagnosis_options": ["Cataract", "Presbyopia"],
        "medication_instructions": "Moxifloxacin 1 drop QID",
        "bp": "120/80",
        "blood_sugar": "110",
        "ot_eye": "left",
        "ot_procedure": "Cataract Surgery",
        "specs_measurements": RX_MEASUREMENTS,
    }
    payload.update(extra)
    return client.post(f"{API}/clinical/transcription/complete", json=payload, timeout=30)


# ---------------- clinical ----------------
class TestClinical:
    def test_admin_cannot_transcribe(self, admin):
        r = admin.post(f"{API}/clinical/lookup", json={"value": str(STATE["p1"]["reg_no"])}, timeout=30)
        assert r.status_code == 403, r.text

    def test_lookup_not_arrived_refusal_no_phi(self, admin):
        clin = _clinical(admin)
        r = clin.post(f"{API}/clinical/lookup", json={"value": str(STATE["p2"]["reg_no"])}, timeout=30)
        assert r.status_code == 409, r.text
        detail = r.json()["detail"]
        assert detail["code"] in ("not_arrived", "never_printed")
        assert STATE["p2"]["full_name"] not in r.text

    def test_lookup_printed_before_seen(self, admin):
        clin = _clinical(admin)
        r = clin.post(f"{API}/clinical/lookup", json={"value": str(STATE["p1"]["reg_no"])}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["registration"]["queue_status"] != "seen"
        assert body["transcription"] is None

    def test_diagnosis_options(self, admin):
        r = admin.get(f"{API}/clinical/diagnosis-options", timeout=30)
        assert r.status_code == 200
        assert "Cataract" in r.json()["options"]

    def test_transcription_requires_arrival(self, admin):
        clin = _clinical(admin)
        r = clin.post(f"{API}/clinical/transcription", json={
            "patient_id": STATE["p2"]["id"], "diagnosis_options": ["Cataract"],
        }, timeout=30)
        assert r.status_code == 409, r.text

    def test_create_transcription(self, admin):
        clin = _clinical(admin)
        r = clin.post(f"{API}/clinical/transcription", json={
            "patient_id": STATE["p1"]["id"], "diagnosis_options": ["Cataract", "Presbyopia"],
            "bp": "130/85", "blood_sugar": "110", "remarks": "TEST remarks",
            "medication_instructions": "drops",
            "ot_eye": "right", "ot_procedure": "Cataract Surgery",
            "specs_measurements": RX_MEASUREMENTS,
        }, timeout=30)
        assert r.status_code == 200, r.text
        t = r.json()["transcription"]
        assert t["locked"] == False
        assert t["diagnosis_options"] == ["Cataract", "Presbyopia"]
        assert t["bp"] == "130/85"
        STATE["trans_id"] = t["id"]

        r = clin.post(f"{API}/clinical/lookup", json={"value": str(STATE["p1"]["reg_no"])}, timeout=30)
        assert r.json()["transcription"]["id"] == t["id"]
        assert r.json()["registration"]["queue_status"] != "seen"

    def test_edit_transcription_before_lock(self, admin):
        clin = _clinical(admin)
        r = clin.post(f"{API}/clinical/transcription", json={
            "patient_id": STATE["p1"]["id"], "diagnosis_options": ["Cataract"],
            "bp": "120/80", "ot_eye": "left", "ot_procedure": "Cataract Surgery",
            "medication_instructions": "Moxifloxacin 1 drop QID",
            "specs_measurements": RX_MEASUREMENTS,
        }, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["transcription"]["bp"] == "120/80"
        assert r.json()["transcription"]["locked"] == False

    def test_complete_prescription(self, admin):
        clin = _clinical(admin)
        r = _complete_rx(clin, STATE["p1"]["id"], f"op-live-{TAG}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["registration"]["queue_status"] == "seen"
        STATE["trans_id"] = body["transcription"]["id"]
        STATE["rev_id"] = body["revision"]["id"]
        STATE["gen"] = body["registration"]["clinical_generation"]

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
            "venue": "TEST Optical", "start_time": "09:00", "end_time": "17:00",
        }, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()["specs_day"]
        assert "seat_limit" not in d and "seats_taken" not in d and "seats_free" not in d
        assert d["start_time"] == "09:00" and d["end_time"] == "17:00"
        assert d["day_date"] == "2026-12-05"
        STATE["specs_day_id"] = d["id"]

        listed = admin.get(f"{API}/clinical/specs-days", timeout=30).json()["specs_days"]
        assert any(x["id"] == d["id"] and x["start_time"] == "09:00" for x in listed)

        r = admin.post(f"{API}/clinical/specs-days", json={
            "camp_id": STATE["camp_id"], "day_date": "2026-12-05",
            "venue": "TEST Optical Hall", "start_time": "10:00", "end_time": "16:00",
        }, timeout=30)
        assert r.status_code == 200, r.text
        up = r.json()["specs_day"]
        assert up["id"] == d["id"]
        assert up["venue"] == "TEST Optical Hall"
        STATE["specs_day_venue"] = "TEST Optical Hall"

    def test_medicine_fulfilment_locks_transcription(self, admin):
        clin = _clinical(admin)
        r = clin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": STATE["trans_id"], "item_type": "medicine", "status": "fulfilled",
            "paper_reviewed": True, "reviewed_revision_id": STATE["rev_id"],
            "reviewed_generation": STATE["gen"], "operation_id": f"op-med-{TAG}",
        }, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["fulfilment"]["status"] == "fulfilled"
        assert r.json()["slip"] is None

        r = clin.post(f"{API}/clinical/lookup", json={"value": str(STATE["p1"]["reg_no"])}, timeout=30)
        assert r.json()["transcription"]["locked"] == True

    def test_transcription_edit_blocked_after_lock(self, admin):
        clin = _clinical(admin)
        r = clin.post(f"{API}/clinical/transcription", json={
            "patient_id": STATE["p1"]["id"], "diagnosis_options": ["Glaucoma"],
        }, timeout=30)
        assert r.status_code == 409, r.text

    def test_invalid_fulfilment_status(self, admin):
        clin = _clinical(admin)
        r = clin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": STATE["trans_id"], "item_type": "medicine", "status": "deferred",
            "paper_reviewed": True, "reviewed_revision_id": STATE["rev_id"],
            "reviewed_generation": STATE["gen"], "operation_id": f"op-bad-{TAG}",
        }, timeout=30)
        assert r.status_code == 400, r.text

    def test_specs_deferral_requires_day_id(self, admin):
        clin = _clinical(admin)
        r = clin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": STATE["trans_id"], "item_type": "specs_made", "status": "deferred",
            "paper_reviewed": True, "reviewed_revision_id": STATE["rev_id"],
            "reviewed_generation": STATE["gen"], "operation_id": f"op-specs-miss-{TAG}",
        }, timeout=30)
        assert r.status_code == 400, r.text

        r = clin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": STATE["trans_id"], "item_type": "specs_made", "status": "deferred",
            "collection_date": "2026-12-05", "collection_venue": "TEST Optical",
            "paper_reviewed": True, "reviewed_revision_id": STATE["rev_id"],
            "reviewed_generation": STATE["gen"], "operation_id": f"op-specs-miss2-{TAG}",
        }, timeout=30)
        assert r.status_code == 400, r.text

    def test_specs_deferral_consumes_seat_and_prints_token(self, admin):
        clin = _clinical(admin)
        r = clin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": STATE["trans_id"], "item_type": "specs_made", "status": "deferred",
            "specs_collection_day_id": STATE["specs_day_id"],
            "paper_reviewed": True, "reviewed_revision_id": STATE["rev_id"],
            "reviewed_generation": STATE["gen"], "operation_id": f"op-specs-{TAG}",
        }, timeout=30)
        assert r.status_code == 200, r.text
        slip = r.json()["slip"]
        assert slip["item_type"] == "specs_made"
        assert slip["collection_date"] == "2026-12-05"
        assert slip["collection_venue"] == STATE["specs_day_venue"]
        assert slip["active"] == True
        STATE["specs_slip_id"] = slip["id"]

        days = admin.get(f"{API}/clinical/specs-days", timeout=30).json()["specs_days"]
        day = next(d for d in days if d["id"] == STATE["specs_day_id"])
        assert "seats_taken" not in day
        assert slip["collection_start_time"] == "10:00"

    def test_specs_window_can_be_updated_after_assignment(self, admin):
        r = admin.post(f"{API}/clinical/specs-days", json={
            "camp_id": STATE["camp_id"], "day_date": "2026-12-05",
            "venue": "TEST Optical Hall", "start_time": "10:00", "end_time": "16:00",
        }, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["specs_day"]["start_time"] == "10:00"

    def test_ot_deferral_consumes_seat_and_prints_slip(self, admin):
        clin = _clinical(admin)
        r = clin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": STATE["trans_id"], "item_type": "ot", "status": "deferred",
            "ot_schedule_day_id": STATE["ot_day_id"],
            "paper_reviewed": True, "reviewed_revision_id": STATE["rev_id"],
            "reviewed_generation": STATE["gen"], "operation_id": f"op-ot-{TAG}",
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

        looked = _clinical(admin).post(f"{API}/clinical/lookup", json={"value": str(STATE["p1"]["reg_no"])}, timeout=30)
        active = [s for s in looked.json()["slips"] if s.get("active")]
        assert {s["item_type"] for s in active} == {"ot", "specs_made"}

    def test_seat_limit_below_assigned(self, admin):
        r = admin.post(f"{API}/clinical/ot-days", json={
            "camp_id": STATE["camp_id"], "day_date": "2026-12-01",
            "venue": "TEST OT Hospital", "seat_limit": 0,
        }, timeout=30)
        assert r.status_code == 400, r.text

    def test_ot_day_full_rejects_further_deferral(self, admin):
        assert admin.post(f"{API}/desk/arrive/{STATE['p2']['id']}", timeout=30).status_code == 200
        assert admin.post(f"{API}/desk/print/{STATE['p2']['id']}", timeout=30).status_code == 200
        clin = _clinical(admin)
        r = _complete_rx(clin, STATE["p2"]["id"], f"op-p2-{TAG}")
        assert r.status_code == 200, r.text
        t2 = r.json()["transcription"]["id"]
        STATE["trans2_id"] = t2
        STATE["rev2_id"] = r.json()["revision"]["id"]
        STATE["gen2"] = r.json()["registration"]["clinical_generation"]
        r = clin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": t2, "item_type": "ot", "status": "deferred",
            "ot_schedule_day_id": STATE["ot_day_id"],
            "paper_reviewed": True, "reviewed_revision_id": STATE["rev2_id"],
            "reviewed_generation": STATE["gen2"], "operation_id": f"op-p2-ot-{TAG}",
        }, timeout=30)
        assert r.status_code == 409, f"expected full-day refusal, got {r.status_code}: {r.text[:200]}"

    def test_specs_window_accepts_further_deferral_without_capacity(self, admin):
        r = _clinical(admin).post(f"{API}/clinical/fulfilment", json={
            "transcription_id": STATE["trans2_id"], "item_type": "specs_made", "status": "deferred",
            "specs_collection_day_id": STATE["specs_day_id"],
            "paper_reviewed": True, "reviewed_revision_id": STATE["rev2_id"],
            "reviewed_generation": STATE["gen2"], "operation_id": f"op-p2-specs-{TAG}",
        }, timeout=30)
        assert r.status_code == 200, r.text

    def test_slip_fetch(self, admin):
        r = _clinical(admin).get(f"{API}/clinical/slip/{STATE['ot_slip_id']}", timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["slip"]["item_type"] == "ot"
        assert r.json()["registration"]["reg_no"] == STATE["p1"]["reg_no"]

    def test_correction_append_only(self, admin):
        clin = _clinical(admin)
        r = clin.post(f"{API}/clinical/correction", json={
            "transcription_id": STATE["trans_id"], "reason": "TEST typo in BP",
            "changes": {"bp": "140/90"},
            "expected_generation": STATE["gen"],
            "operation_id": f"op-corr-{TAG}",
            "full_transcription_confirmed": True,
            "prescribed_lines": ["medicine", "specs_fixed", "specs_made", "ot"],
            "diagnosis_options": ["Cataract"],
            "medication_instructions": "Moxifloxacin 1 drop QID",
            "bp": "140/90",
            "ot_eye": "left",
            "ot_procedure": "Cataract Surgery",
            "specs_measurements": RX_MEASUREMENTS,
        }, timeout=30)
        assert r.status_code == 200, r.text
        STATE["rev_id"] = r.json()["revision"]["id"]
        STATE["gen"] = r.json()["registration"]["clinical_generation"]
        r = clin.get(f"{API}/clinical/corrections/{STATE['trans_id']}", timeout=30)
        assert r.status_code == 200
        corr = r.json()["corrections"]
        assert len(corr) == 1
        assert corr[0]["reason"] == "TEST typo in BP"
        r = clin.post(f"{API}/clinical/lookup", json={"value": str(STATE["p1"]["reg_no"])}, timeout=30)
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
        r = _clinical(admin).get(f"{API}/clinical/history/{person_id}", timeout=30)
        assert r.status_code == 200, r.text
        assert isinstance(r.json()["history"], list)


# ---------------- staff ----------------
class TestStaff:
    def test_staff_requires_a_name(self, admin):
        r = admin.post(f"{API}/staff", json={
            "name": " ", "role": "volunteer",
        }, timeout=30)
        assert r.status_code == 400, r.text

    def test_create_volunteer_team_lead_clinical(self, admin):
        accounts = [
            ("volunteer", f"TEST volunteer {TAG}"),
            ("team_lead", f"TEST lead {TAG}"),
            ("clinical_desk_operator", f"TEST clinical {TAG}"),
        ]
        for role, name in accounts:
            r = admin.post(f"{API}/staff", json={"name": name, "role": role}, timeout=30)
            assert r.status_code == 200, f"{role}: {r.text}"
            assert r.json()["staff"]["role"] == role
            STATE[role] = {"name": name, "pin": "5678", "id": r.json()["staff"]["id"]}
            session = requests.Session()
            logged_in = session.post(f"{API}/auth/login", json={"name": name, "pin": "1234"}, timeout=30)
            assert logged_in.status_code == 200, logged_in.text
            changed = session.post(f"{API}/auth/change-pin", json={"current_pin": "1234", "new_pin": "5678"}, timeout=30)
            assert changed.status_code == 200, changed.text

        r = admin.post(f"{API}/staff", json={"name": accounts[0][1], "role": "volunteer"}, timeout=30)
        assert r.status_code == 409, r.text

    def test_invalid_role(self, admin):
        r = admin.post(f"{API}/staff", json={"email": f"TEST_bad_{TAG}@x.org",
                                             "password": "GoodPass@12345", "name": "x",
                                             "role": "superuser"}, timeout=30)
        assert r.status_code in (400, 422), r.text

    def test_team_lead_can_only_create_volunteers(self, anon):
        lead = STATE["team_lead"]
        r = anon.post(f"{API}/auth/login", json={"name": lead["name"], "pin": lead["pin"]},
                      timeout=30)
        assert r.status_code == 200, r.text
        tok = r.json()["access_token"]
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {tok}"})
        r = s.post(f"{API}/staff", json={"email": f"TEST_admin2_{TAG}@x.org",
                                         "password": "GoodPass@12345", "name": "x", "role": "admin"},
                   timeout=30)
        assert r.status_code == 403, r.text
        r = s.post(f"{API}/staff", json={"name": f"TEST vol2 {TAG}",
                                         "role": "volunteer"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["staff"]["team_lead_id"] == str(STATE["team_lead"]["id"])

    def test_clinical_operator_cannot_register_or_print(self, anon):
        c = STATE["clinical_desk_operator"]
        r = anon.post(f"{API}/auth/login", json={"name": c["name"], "pin": c["pin"]}, timeout=30)
        assert r.status_code == 200, r.text
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
        assert s.post(f"{API}/desk/print/{STATE['p1']['id']}", timeout=30).status_code == 403
        # but clinical lookup works
        r = s.post(f"{API}/clinical/lookup", json={"value": str(STATE["p1"]["reg_no"])}, timeout=30)
        assert r.status_code == 200, r.text

    def test_volunteer_cannot_access_clinical(self, anon):
        v = STATE["volunteer"]
        r = anon.post(f"{API}/auth/login", json={"name": v["name"], "pin": v["pin"]}, timeout=30)
        assert r.status_code == 200, r.text
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
        r = s.post(f"{API}/clinical/lookup", json={"value": str(STATE["p1"]["reg_no"])}, timeout=30)
        assert r.status_code == 403, r.text

    def test_disable_then_enable_staff(self, admin, anon):
        v = STATE["volunteer"]
        assert admin.patch(f"{API}/staff/{v['id']}/disable", timeout=30).status_code == 200
        r = anon.post(f"{API}/auth/login", json={"name": v["name"], "pin": v["pin"]}, timeout=30)
        assert r.status_code == 403, f"disabled account still logs in: {r.status_code}"
        assert admin.patch(f"{API}/staff/{v['id']}/enable", timeout=30).status_code == 200
        r = anon.post(f"{API}/auth/login", json={"name": v["name"], "pin": v["pin"]}, timeout=30)
        assert r.status_code == 200, r.text

    def test_list_staff(self, admin):
        r = admin.get(f"{API}/staff", timeout=30)
        assert r.status_code == 200
        names = [u["name"] for u in r.json()["staff"]]
        assert STATE["volunteer"]["name"] in names


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

    def test_single_export_is_one_wide_row_per_patient(self, admin):
        r = admin.get(f"{API}/exports/camp-records", timeout=60)
        assert r.status_code == 200, r.text
        assert "text/csv" in r.headers.get("content-type", "")
        header = r.text.splitlines()[0]
        assert header == (
            "reg_no,full_name,age,gender,phone,address,aadhaar_last4,"
            "manual_entry,camp_day,registered_at,arrived_at,seen_at,"
            "diagnosis,bp,blood_sugar,"
            "r_sph,r_cyl,r_axis,l_sph,l_cyl,l_axis,add,"
            "medicine,fixed_power_specs,spectacles_to_be_made,ot,"
            "ot_day,ot_venue,specs_day,specs_venue,specs_start,specs_end"
        ), header
        assert str(STATE["p1"]["reg_no"]) in r.text

    def test_clinical_audit_export_is_gone(self, admin):
        assert admin.get(f"{API}/exports/clinical-audit", timeout=60).status_code == 404

    def test_exports_require_admin(self, anon):
        c = STATE["clinical_desk_operator"]
        r = anon.post(f"{API}/auth/login", json={"name": c["name"], "pin": c["pin"]}, timeout=30)
        assert r.status_code == 200, r.text
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
        assert admin.post(f"{API}/desk/arrive/{pid}", timeout=30).status_code == 200
        pr = admin.post(f"{API}/desk/print/{pid}", timeout=30)
        assert pr.status_code == 200, pr.text
        printed_at = pr.json()["registration"]["printed_at"]
        assert printed_at
        assert admin.post(f"{API}/desk/mark-seen/{pid}", timeout=30).status_code == 200
        u = admin.post(f"{API}/desk/undo-seen/{pid}", timeout=30)
        assert u.status_code == 200, f"{u.status_code} {u.text[:300]}"
        reg = u.json()["registration"]
        assert reg["queue_status"] == "arrived"
        assert reg["printed_at"] == printed_at, "presence (printed_at) must be preserved on undo"
        assert reg.get("seen_at") in (None, "")
        # verify persisted
        g = admin.post(f"{API}/desk/lookup", json={"value": str(reg["reg_no"])}, timeout=30)
        assert g.json()["registration"]["queue_status"] == "arrived"
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

    def test_specs_rerecord_replaces_active_token_without_capacity(self, admin):
        a = admin.post(f"{API}/clinical/specs-days", json={
            "camp_id": STATE["camp_id"], "day_date": "2026-12-18",
            "venue": "TEST Specs A", "start_time": "09:00", "end_time": "17:00"}, timeout=30)
        b = admin.post(f"{API}/clinical/specs-days", json={
            "camp_id": STATE["camp_id"], "day_date": "2026-12-19",
            "venue": "TEST Specs B", "start_time": "09:00", "end_time": "17:00"}, timeout=30)
        assert a.status_code == 200 and b.status_code == 200, (a.text, b.text)
        day_a, day_b = a.json()["specs_day"]["id"], b.json()["specs_day"]["id"]

        t2 = STATE["trans2_id"]
        r = admin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": t2, "item_type": "specs_made", "status": "deferred",
            "specs_collection_day_id": day_a}, timeout=30)
        assert r.status_code == 200, r.text

        def seats(day_id):
            days = admin.get(f"{API}/clinical/specs-days", timeout=30).json()["specs_days"]
            return next(d for d in days if d["id"] == day_id).get("seats_taken", 0)

        assert seats(day_a) == 0
        r = admin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": t2, "item_type": "specs_made", "status": "deferred",
            "specs_collection_day_id": day_b}, timeout=30)
        assert r.status_code == 200, r.text
        assert seats(day_b) == 0
        assert seats(day_a) == 0, "previous Specs collection day seat leaked (not released)"

        r = admin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": t2, "item_type": "specs_fixed", "status": "fulfilled"}, timeout=30)
        assert r.status_code == 409, r.text
        assert "Spectacles to be made" in str(r.json())
        assert seats(day_b) == 0
        looked = admin.post(f"{API}/clinical/lookup", json={"value": str(STATE["p2"]["reg_no"])}, timeout=30)
        assert looked.status_code == 200, looked.text
        active_specs = [s for s in looked.json()["slips"] if s.get("active") and s["item_type"] == "specs_made"]
        assert len(active_specs) == 1

    def test_specs_choice_is_exclusive_and_collection_has_no_capacity_limit(self, admin):
        c = admin.post(f"{API}/clinical/specs-days", json={
            "camp_id": STATE["camp_id"], "day_date": "2026-12-22",
            "venue": "TEST Specs C", "start_time": "09:00", "end_time": "17:00"}, timeout=30)
        assert c.status_code == 200, c.text
        day_c = c.json()["specs_day"]["id"]
        t2 = STATE["trans2_id"]

        r = admin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": t2, "item_type": "specs_made", "status": "deferred",
            "specs_collection_day_id": day_c}, timeout=30)
        assert r.status_code == 200, r.text

        def seats():
            days = admin.get(f"{API}/clinical/specs-days", timeout=30).json()["specs_days"]
            return next(d for d in days if d["id"] == day_c).get("seats_taken", 0)

        assert seats() == 0
        r = admin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": t2, "item_type": "specs_fixed", "status": "fulfilled",
            "specs_collection_day_id": day_c}, timeout=30)
        assert r.status_code == 409, r.text
        assert seats() == 0
        r = admin.post(f"{API}/clinical/fulfilment", json={
            "transcription_id": STATE["trans_id"], "item_type": "specs_made", "status": "deferred",
            "specs_collection_day_id": day_c}, timeout=30)
        assert r.status_code == 200, r.text
        assert seats() == 0

    def test_lockout_returns_429_and_is_name_keyed(self, anon):
        name = f"TEST_lock2_{TAG}"
        codes = []
        for _ in range(7):
            codes.append(anon.post(f"{API}/auth/login",
                                   json={"name": name, "pin": "0000"},
                                   timeout=30).status_code)
        assert 500 not in codes, codes
        assert codes[:5] == [401] * 5, codes
        assert codes[5] == 429 and codes[6] == 429, codes
        other = anon.post(f"{API}/auth/login",
                          json={"name": f"TEST_other_{TAG}", "pin": "0000"}, timeout=30)
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
