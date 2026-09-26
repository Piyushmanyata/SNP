"""Iteration-3 additions: genuine Aadhaar Secure QR decode + prescription template editor API."""
import gzip
import base64
import io
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import requests

from conftest import API

TAG = uuid.uuid4().hex[:6]
TODAY_IST = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
S = {}

FIELDS = ["indicator", "referenceid", "name", "dob", "gender", "careof", "district",
          "landmark", "house", "location", "pincode", "postoffice", "state",
          "street", "subdistrict", "vtc"]


def build_secure_qr(values, use_gzip=True):
    """Build a synthetic Secure-QR-v2 style big-integer payload."""
    raw = b"\xff".join(v.encode("ISO-8859-1") for v in values) + b"\xff" + b"SIGNATURE" * 8
    if use_gzip:
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as f:
            f.write(raw)
        comp = buf.getvalue()
    else:
        import zlib
        comp = zlib.compress(raw)
    return str(int.from_bytes(comp, "big"))


SAMPLE = ["2", "567820190301120000", "Ramesh Kumar", "15-08-1975", "M", "S/O Suresh",
          "Ghaziabad", "Near Temple", "12-A", "Rampur", "201001", "Rampur PO",
          "Uttar Pradesh", "MG Road", "Modinagar", "Rampur"]


# ---------------- Aadhaar decode ----------------
class TestAadhaarDecode:
    def test_legacy_xml_payload(self, anon):
        r = anon.post(f"{API}/aadhaar/decode",
                      json={"payload": '<PrintLetterBarcodeData name="Ramesh Kumar" gender="M" dob="1975-08-15" uid="5678" street="MG Road"/>'}, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["outcome"] == "card", j
        d = j["data"]
        assert d["full_name"] == "Ramesh Kumar"
        assert d["gender"] == "M"
        assert d["dob"] == "1975-08-15"
        assert d["aadhaar_last4"] == "5678"
        assert d["address"] == "MG Road"
        assert isinstance(d.get("age"), int) and d["age"] >= 50, d

    def test_genuine_secure_qr_gzip(self, anon):
        payload = build_secure_qr(SAMPLE, use_gzip=True)
        r = anon.post(f"{API}/aadhaar/decode", json={"payload": payload}, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["outcome"] == "card", j
        assert j.get("source") == "secure_qr", j
        d = j["data"]
        assert d["full_name"] == "Ramesh Kumar"
        assert d["gender"] == "M"
        assert d["dob"] == "1975-08-15"
        assert d["aadhaar_last4"] == "5678"
        for frag in ["12-A", "MG Road", "Uttar Pradesh", "201001"]:
            assert frag in d["address"], d["address"]
        assert isinstance(d.get("age"), int)

    def test_genuine_secure_qr_raw_zlib(self, anon):
        payload = build_secure_qr(SAMPLE, use_gzip=False)
        r = anon.post(f"{API}/aadhaar/decode", json={"payload": payload}, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["outcome"] == "card", j
        assert j["data"]["full_name"] == "Ramesh Kumar"

    def test_female_and_year_only_dob(self, anon):
        vals = list(SAMPLE)
        vals[2] = "Sita Devi"
        vals[3] = "1990"
        vals[4] = "F"
        r = anon.post(f"{API}/aadhaar/decode", json={"payload": build_secure_qr(vals)}, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["outcome"] == "card", j
        assert j["data"]["full_name"] == "Sita Devi"
        assert j["data"]["gender"] == "F"
        assert j["data"]["dob"] == "1990-01-01"

    def test_large_secure_qr_with_photo(self, anon):
        """Real Secure QR v2 carries an embedded JPEG photo => 1.5-3 KB compressed,
        i.e. >4300 decimal digits. Python 3.11 caps int(str) at 4300 digits, so
        aadhaar._decompress raises ValueError and genuine cards decode as garbage."""
        import os as _os
        import sys as _sys
        _sys.set_int_max_str_digits(200000)
        vals = list(SAMPLE)
        raw = b"\xff".join(v.encode("ISO-8859-1") for v in vals) + b"\xff" + _os.urandom(2000)
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as f:
            f.write(raw)
        payload = str(int.from_bytes(buf.getvalue(), "big"))
        assert len(payload) > 4300
        r = anon.post(f"{API}/aadhaar/decode", json={"payload": payload}, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["outcome"] == "card", f"payload of {len(payload)} digits rejected: {j}"
        assert j["data"]["full_name"] == "Ramesh Kumar"

    def test_old_xml_qr(self, anon):
        xml = ('<?xml version="1.0"?><PrintLetterBarcodeData uid="123456785678" '
               'name="Amit Sharma" gender="M" yob="1980" house="9" street="Station Rd" '
               'vtc="Rampur" dist="Ghaziabad" state="Uttar Pradesh" pc="201001"/>')
        r = anon.post(f"{API}/aadhaar/decode", json={"payload": xml}, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["outcome"] == "card", j
        assert j["data"]["full_name"] == "Amit Sharma"
        assert j["data"]["aadhaar_last4"] == "5678"

    def test_random_text_is_garbage(self, anon):
        r = anon.post(f"{API}/aadhaar/decode", json={"payload": "hello world this is not a qr"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["outcome"] == "garbage", r.text

    def test_long_random_digits_is_garbage(self, anon):
        r = anon.post(f"{API}/aadhaar/decode", json={"payload": "9" * 120}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["outcome"] == "garbage", r.text

    def test_patient_qr_not_aadhaar(self, anon):
        pid = str(uuid.uuid4())
        for p in [f"snp:{pid}", f"https://example.com/p/{pid}"]:
            r = anon.post(f"{API}/aadhaar/decode", json={"payload": p}, timeout=30)
            assert r.status_code == 200, r.text
            assert r.json()["outcome"] == "not-aadhaar", r.text


# ---------------- Templates ----------------
PNG_1PX = base64.b64encode(base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8AAAwAB/AF/A5o5AAAAAElFTkSuQmCC"
)).decode()
PNG_DATA_URL = f"data:image/png;base64,{PNG_1PX}"


@pytest.fixture(scope="module")
def camp(admin):
    r = admin.post(f"{API}/camps", json={"name": f"TEST_TPL Camp {TAG}", "venue": "TEST Hall",
                                         "camp_date": TODAY_IST}, timeout=30)
    assert r.status_code in (200, 201), r.text
    cid = r.json()["camp"]["id"]
    S["camp_id"] = cid
    return cid


class TestPrescriptionTemplateLockdown:
    def test_logos_are_the_only_template_surface(self, admin, camp):
        r = admin.get(f"{API}/templates/logos?camp_id={camp}", timeout=30)
        assert r.status_code == 200, r.text
        assert set(r.json().keys()) == {"logos"}
        assert len(r.json()["logos"]) == 1

    def test_reading_logos_requires_auth_and_saving_requires_admin(self, camp):
        fresh = requests.Session()  # session-scoped anon may carry cookies from earlier tests
        assert fresh.get(f"{API}/templates/logos?camp_id={camp}", timeout=30).status_code in (401, 403)
        assert fresh.put(f"{API}/templates/logos", json={"camp_id": camp, "logos": []},
                         timeout=30).status_code in (401, 403)

    def test_bad_camp_404(self, admin):
        r = admin.get(f"{API}/templates/logos?camp_id=507f1f77bcf86cd799439011", timeout=30)
        assert r.status_code == 404, r.status_code

    def test_saving_logos_persists_without_a_publish_step(self, admin, camp):
        r = admin.put(f"{API}/templates/logos", json={
            "camp_id": camp,
            "logos": [{"id": "l1", "name": "s.png", "data_url": PNG_DATA_URL, "order": 0}],
        }, timeout=30)
        assert r.status_code == 200, r.text
        again = admin.get(f"{API}/templates/logos?camp_id={camp}", timeout=30).json()
        assert [lg["name"] for lg in again["logos"]] == ["s.png"]

    def test_logo_too_large_rejected(self, admin, camp):
        big = "data:image/png;base64," + "A" * (3 * 1024 * 1024)
        r = admin.put(f"{API}/templates/logos", json={
            "camp_id": camp, "logos": [{"id": "b", "name": "b.png", "data_url": big, "order": 0}],
        }, timeout=60)
        assert r.status_code == 400, r.text

    def test_logo_bad_mime_rejected(self, admin, camp):
        r = admin.put(f"{API}/templates/logos", json={
            "camp_id": camp,
            "logos": [{"id": "g", "name": "g.gif",
                       "data_url": "data:image/gif;base64,R0lGODlhAQABAAAAACw=", "order": 0}],
        }, timeout=30)
        assert r.status_code == 400, r.text


# ---------------- print includes camp_id + template driven ----------------
class TestPrintTemplate:
    def test_print_response_has_camp_id_and_active_template(self, admin):
        ac = admin.get(f"{API}/camps/active", timeout=30)
        assert ac.status_code == 200, ac.text
        camp_id = ac.json()["camp"]["id"]
        days = [d for d in ac.json()["days"] if d["is_today"]]
        assert days, "no camp day for today on the active camp"
        day = days[0]
        if not day["printing_open"]:
            o = admin.patch(f"{API}/camps/days/{day['id']}/print-window",
                            json={"printing_open": True}, timeout=30)
            assert o.status_code == 200, o.text
        # register a patient on the active camp
        reg = admin.post(f"{API}/register", json={
            "full_name": f"TEST Print {TAG}", "gender": "M", "age": 44,
            "phone": "9876500011", "address": "TEST addr", "camp_day_id": day["id"],
            "aadhaar_last4": "5678",
            "manual_reason": "no_card",
            "registration_request_id": str(uuid.uuid4())}, timeout=30)
        assert reg.status_code in (200, 201), reg.text
        pid = reg.json()["registration"]["id"]
        blocked = admin.post(f"{API}/desk/print/{pid}", timeout=30)
        assert blocked.status_code == 409, blocked.text
        assert blocked.json()["detail"]["code"] == "NOT_ARRIVED"
        admin.post(f"{API}/desk/no-card", json={"patient_id": pid, "reason": "no_card"}, timeout=30)
        assert admin.post(f"{API}/desk/arrive/{pid}", timeout=30).status_code == 200
        pr = admin.post(f"{API}/desk/print/{pid}", timeout=30)
        assert pr.status_code == 200, pr.text
        presc = pr.json()["prescription"]
        assert presc.get("camp_id") == camp_id, presc
        admin.put(f"{API}/templates/logos", json={
            "camp_id": camp_id,
            "logos": [{"id": "l1", "name": "s.png", "data_url": PNG_DATA_URL, "order": 0}]}, timeout=30)
        t = admin.get(f"{API}/templates/logos?camp_id={camp_id}", timeout=30).json()
        assert [lg["name"] for lg in t["logos"]] == ["s.png"]
        S["print_patient_id"] = pid
        S["print_camp_id"] = camp_id
        print("PRINT_PATIENT", pid, "CAMP", camp_id, "REG", reg.json()["registration"].get("reg_no"))
