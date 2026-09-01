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
    def test_demo_payload(self, anon):
        r = anon.post(f"{API}/aadhaar/decode",
                      json={"payload": "AADHAAR|Ramesh Kumar|M|1975-08-15|5678|MG Road"}, timeout=30)
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


class TestTemplates:
    def test_get_templates_returns_defaults(self, admin, camp):
        r = admin.get(f"{API}/templates?camp_id={camp}", timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["draft"] is None and j["published"] is None
        d = j["defaults"]
        assert len(d["blocks"]) == 7
        assert "Sikar Nagarik Parishad" in d["header_title"]
        assert "Sikar Zilla Welfare Trust" in d["header_title"]
        assert "Sikar Bhawan" in d["header_subtitle"] or "SIKAR BHAWAN" in d["header_subtitle"].upper()
        assert "Rupa" in d["footer_note"]
        assert len(d["logos"]) >= 2
        assert [b["id"] for b in d["blocks"]][0] == "identity"

    def test_requires_admin(self, camp):
        fresh = requests.Session()  # session-scoped anon may carry cookies from earlier tests
        assert fresh.get(f"{API}/templates?camp_id={camp}", timeout=30).status_code in (401, 403)
        assert fresh.post(f"{API}/templates/draft", json={"camp_id": camp}, timeout=30).status_code in (401, 403)
        assert fresh.post(f"{API}/templates/publish", json={"camp_id": camp}, timeout=30).status_code in (401, 403)
        assert fresh.get(f"{API}/templates/active?camp_id={camp}", timeout=30).status_code in (401, 403)

    def test_bad_camp_404(self, admin):
        r = admin.get(f"{API}/templates?camp_id=507f1f77bcf86cd799439011", timeout=30)
        assert r.status_code == 404, r.status_code

    def test_publish_without_draft_400(self, admin, camp):
        r = admin.post(f"{API}/templates/publish", json={"camp_id": camp}, timeout=30)
        assert r.status_code == 400, r.text
        assert "draft" in r.json()["detail"].lower()

    def test_save_draft_and_persist(self, admin, camp):
        blocks = [
            {"id": "identity", "label": "Patient Identity", "type": "identity", "visible": True, "height": 0},
            {"id": "vision", "label": "Vision R/L", "type": "lines", "visible": True, "height": 30},
            {"id": "prescription", "label": "Rx", "type": "lines", "visible": True, "height": 50},
            {"id": "advice", "label": "Advice", "type": "lines", "visible": False, "height": 200},
            {"id": "signature", "label": "Sign", "type": "signature", "visible": True, "height": 0},
        ]
        body = {"camp_id": camp, "header_title": "TEST Sankalp Netra Shivir",
                "header_subtitle": "TEST Rampur", "footer_note": "TEST footer note",
                "blocks": blocks, "logos": [{"id": "l1", "name": "sponsor.png", "data_url": PNG_DATA_URL, "order": 0}]}
        r = admin.post(f"{API}/templates/draft", json=body, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()["draft"]
        assert d["header_title"] == "TEST Sankalp Netra Shivir"
        assert len(d["blocks"]) == 5 and len(d["logos"]) == 1
        assert d["status"] == "draft"
        # GET verifies persistence
        g = admin.get(f"{API}/templates?camp_id={camp}", timeout=30).json()
        assert g["draft"]["footer_note"] == "TEST footer note"
        assert g["draft"]["blocks"][1]["label"] == "Vision R/L"
        assert g["draft"]["logos"][0]["data_url"].startswith("data:image/png;base64,")

    def test_draft_is_upserted_not_duplicated(self, admin, camp):
        r = admin.post(f"{API}/templates/draft", json={"camp_id": camp, "header_title": "TEST v2",
                                                       "header_subtitle": "s", "footer_note": "f",
                                                       "blocks": [{"id": "identity", "label": "I", "type": "identity",
                                                                   "visible": True, "height": 0}], "logos": []},
                       timeout=30)
        assert r.status_code == 200, r.text
        g = admin.get(f"{API}/templates?camp_id={camp}", timeout=30).json()
        assert g["draft"]["header_title"] == "TEST v2"
        assert len(g["draft"]["blocks"]) == 1

    def test_logo_too_large_rejected(self, admin, camp):
        big = base64.b64encode(b"\x00" * (2 * 1024 * 1024 + 10)).decode()
        r = admin.post(f"{API}/templates/draft",
                       json={"camp_id": camp, "blocks": [], "logos": [{"id": "b", "name": "big.png",
                                                                       "data_url": f"data:image/png;base64,{big}"}]},
                       timeout=60)
        assert r.status_code == 400, r.status_code
        assert "2 MB" in r.json()["detail"] or "2MB" in r.json()["detail"], r.text

    def test_logo_bad_mime_rejected(self, admin, camp):
        r = admin.post(f"{API}/templates/draft",
                       json={"camp_id": camp, "blocks": [], "logos": [{"id": "g", "name": "a.gif",
                                                                       "data_url": f"data:image/gif;base64,{PNG_1PX}"}]},
                       timeout=30)
        assert r.status_code == 400, r.status_code
        assert "Unsupported image type" in r.json()["detail"], r.text

    def test_one_page_guard(self, admin, camp):
        blocks = [{"id": "a", "label": "A", "type": "lines", "visible": True, "height": 120},
                  {"id": "b", "label": "B", "type": "lines", "visible": True, "height": 120}]
        assert admin.post(f"{API}/templates/draft", json={"camp_id": camp, "header_title": "TEST too tall",
                                                          "blocks": blocks, "logos": []},
                          timeout=30).status_code == 200
        r = admin.post(f"{API}/templates/publish", json={"camp_id": camp}, timeout=30)
        assert r.status_code == 400, r.text
        assert "exceeds one A4 page" in r.json()["detail"], r.text

    def test_hidden_blocks_excluded_from_guard(self, admin, camp):
        blocks = [{"id": "a", "label": "A", "type": "lines", "visible": True, "height": 120},
                  {"id": "b", "label": "B", "type": "lines", "visible": False, "height": 500}]
        assert admin.post(f"{API}/templates/draft", json={"camp_id": camp, "header_title": "TEST hidden ok",
                                                          "blocks": blocks, "logos": []},
                          timeout=30).status_code == 200
        r = admin.post(f"{API}/templates/publish", json={"camp_id": camp}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["published"]["version"] == 1

    def test_publish_versioning_and_active(self, admin, camp):
        admin.post(f"{API}/templates/draft", json={"camp_id": camp, "header_title": "TEST Published Title",
                                                   "header_subtitle": "TEST sub", "footer_note": "TEST foot",
                                                   "blocks": [{"id": "identity", "label": "Identity",
                                                               "type": "identity", "visible": True, "height": 0},
                                                              {"id": "rx", "label": "Rx", "type": "lines",
                                                               "visible": True, "height": 60}],
                                                   "logos": [{"id": "l1", "name": "s.png",
                                                              "data_url": PNG_DATA_URL, "order": 0}]}, timeout=30)
        r = admin.post(f"{API}/templates/publish", json={"camp_id": camp}, timeout=30)
        assert r.status_code == 200, r.text
        pub = r.json()["published"]
        assert pub["version"] == 2, pub
        assert pub["published_at"]
        act = admin.get(f"{API}/templates/active?camp_id={camp}", timeout=30)
        assert act.status_code == 200, act.text
        t = act.json()["template"]
        assert t["header_title"] == "TEST Published Title"
        assert t["version"] == 2
        assert len(t["logos"]) == 1

    def test_restore_defaults(self, admin, camp):
        r = admin.post(f"{API}/templates/restore-defaults", json={"camp_id": camp}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()["draft"]
        assert len(d["blocks"]) == 7
        assert "Sikar Nagarik Parishad" in d["header_title"]
        assert "Rupa" in d["footer_note"]
        assert len(d["logos"]) >= 2
        g = admin.get(f"{API}/templates?camp_id={camp}", timeout=30).json()
        assert len(g["draft"]["blocks"]) == 7
        assert g["published"]["version"] == 2
        assert g["published"]["header_title"] == "TEST Published Title"

    def test_no_mongo_id_leak(self, admin, camp):
        for url in [f"{API}/templates?camp_id={camp}", f"{API}/templates/active?camp_id={camp}"]:
            assert '"_id"' not in admin.get(url, timeout=30).text


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
            "aadhaar_last4": "5678", "aadhaar_verified": True,
            "registration_request_id": str(uuid.uuid4())}, timeout=30)
        assert reg.status_code in (200, 201), reg.text
        pid = reg.json()["registration"]["id"]
        pr = admin.post(f"{API}/desk/print/{pid}", timeout=30)
        assert pr.status_code == 200, pr.text
        presc = pr.json()["prescription"]
        assert presc.get("camp_id") == camp_id, presc
        # publish a custom template for the active camp so the print sheet uses it
        admin.post(f"{API}/templates/draft", json={
            "camp_id": camp_id, "header_title": "TEST Sankalp Netra Shivir",
            "header_subtitle": "TEST Rampur Community Hall", "footer_note": "TEST print footer",
            "blocks": [{"id": "identity", "label": "Patient Identity", "type": "identity",
                        "visible": True, "height": 0},
                       {"id": "vision", "label": "TEST Vision Block", "type": "lines",
                        "visible": True, "height": 40},
                       {"id": "signature", "label": "Doctor's Signature", "type": "signature",
                        "visible": True, "height": 0}],
            "logos": [{"id": "l1", "name": "s.png", "data_url": PNG_DATA_URL, "order": 0}]}, timeout=30)
        p = admin.post(f"{API}/templates/publish", json={"camp_id": camp_id}, timeout=30)
        assert p.status_code == 200, p.text
        t = admin.get(f"{API}/templates/active?camp_id={camp_id}", timeout=30).json()["template"]
        assert t["header_title"] == "TEST Sankalp Netra Shivir"
        S["print_patient_id"] = pid
        S["print_camp_id"] = camp_id
        print("PRINT_PATIENT", pid, "CAMP", camp_id, "REG", reg.json()["registration"].get("reg_no"))
