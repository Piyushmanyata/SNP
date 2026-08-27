import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import io
import gzip
import zlib
from aadhaar import decode_aadhaar, parse_secure_qr, parse_xml_qr

SAMPLE = [
    "2", "567820190301120000", "Ramesh Kumar", "15-08-1975", "M", "S/O Suresh",
    "Ghaziabad", "Near Temple", "12-A", "Rampur", "201001", "Rampur PO",
    "Uttar Pradesh", "MG Road", "Modinagar", "Rampur"
]


def build_secure_qr(values, use_gzip=True):
    raw = b"\xff".join(v.encode("ISO-8859-1") for v in values) + b"\xff" + b"SIGNATURE" * 8
    if use_gzip:
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as f:
            f.write(raw)
        comp = buf.getvalue()
    else:
        comp = zlib.compress(raw)
    return str(int.from_bytes(comp, "big"))


def test_decode_empty():
    assert decode_aadhaar("") == {"outcome": "not-aadhaar", "message": "No data captured."}
    assert decode_aadhaar(None) == {"outcome": "not-aadhaar", "message": "No data captured."}


def test_decode_patient_qr():
    assert decode_aadhaar("snp:12345") == {"outcome": "not-aadhaar", "message": "This is a patient QR, not an Aadhaar card."}
    assert decode_aadhaar("https://camps.snp.org/p/abcde") == {"outcome": "not-aadhaar", "message": "This is a patient QR, not an Aadhaar card."}


def test_decode_demo_format():
    res = decode_aadhaar("AADHAAR|Priya Sharma|F|1992-04-10|9876|45 Station Rd, Howrah")
    assert res["outcome"] == "card"
    assert res["source"] == "demo"
    assert res["data"]["full_name"] == "Priya Sharma"
    assert res["data"]["gender"] == "F"
    assert res["data"]["dob"] == "1992-04-10"
    assert res["data"]["aadhaar_last4"] == "9876"
    assert res["data"]["address"] == "45 Station Rd, Howrah"


def test_decode_demo_malformed():
    res = decode_aadhaar("AADHAAR|Priya|F")
    assert res["outcome"] == "garbage"


def test_decode_xml_qr():
    xml = ('<?xml version="1.0"?><PrintLetterBarcodeData uid="123456785678" '
           'name="Amit Sharma" gender="M" yob="1980" house="9" street="Station Rd" '
           'vtc="Rampur" dist="Ghaziabad" state="Uttar Pradesh" pc="201001"/>')
    res = decode_aadhaar(xml)
    assert res["outcome"] == "card"
    assert res["source"] == "secure_qr_xml"
    assert res["data"]["full_name"] == "Amit Sharma"
    assert res["data"]["gender"] == "M"
    assert res["data"]["dob"] == "1980-01-01"
    assert res["data"]["aadhaar_last4"] == "5678"
    assert "Station Rd" in res["data"]["address"]


def test_decode_xml_malformed():
    res = decode_aadhaar("<PrintLetterBarcodeData uid='123' />")
    assert res["outcome"] == "garbage"


def test_decode_secure_qr_gzip():
    payload = build_secure_qr(SAMPLE, use_gzip=True)
    res = decode_aadhaar(payload)
    assert res["outcome"] == "card"
    assert res["source"] == "secure_qr"
    assert res["data"]["full_name"] == "Ramesh Kumar"
    assert res["data"]["gender"] == "M"
    assert res["data"]["dob"] == "1975-08-15"
    assert res["data"]["aadhaar_last4"] == "5678"
    assert "MG Road" in res["data"]["address"]


def test_decode_secure_qr_zlib():
    payload = build_secure_qr(SAMPLE, use_gzip=False)
    res = decode_aadhaar(payload)
    assert res["outcome"] == "card"
    assert res["source"] == "secure_qr"
    assert res["data"]["full_name"] == "Ramesh Kumar"


def test_decode_secure_qr_large_digits():
    import os
    vals = list(SAMPLE)
    raw = b"\xff".join(v.encode("ISO-8859-1") for v in vals) + b"\xff" + os.urandom(2500)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as f:
        f.write(raw)
    payload = str(int.from_bytes(buf.getvalue(), "big"))
    assert len(payload) > 4300
    res = decode_aadhaar(payload)
    assert res["outcome"] == "card"
    assert res["data"]["full_name"] == "Ramesh Kumar"


def test_decode_xml_case_insensitive():
    xml = ('<?xml version="1.0"?><PrintLetterBarcodeData UID="998877664321" '
           'Name="Sunita Patel" Gender="F" DOB="12/05/1988" House="Flat 402" '
           'Dist="Surat" State="Gujarat" PC="395007"/>')
    res = decode_aadhaar(xml)
    assert res["outcome"] == "card"
    assert res["source"] == "secure_qr_xml"
    assert res["data"]["full_name"] == "Sunita Patel"
    assert res["data"]["gender"] == "F"
    assert res["data"]["dob"] == "1988-05-12"
    assert res["data"]["aadhaar_last4"] == "4321"
    assert "Surat" in res["data"]["address"]


def test_decode_secure_qr_multiline_crlf():
    payload = build_secure_qr(SAMPLE, use_gzip=True)
    # Simulate hardware USB barcode scanner sending chunks separated by CRLF and tabs
    chunked = "\r\n".join([payload[i:i + 50] for i in range(0, len(payload), 50)]) + "\r\n\t "
    res = decode_aadhaar(chunked)
    assert res["outcome"] == "card"
    assert res["source"] == "secure_qr"
    assert res["data"]["full_name"] == "Ramesh Kumar"
    assert res["data"]["aadhaar_last4"] == "5678"


def test_decode_date_dotted_format():
    vals = list(SAMPLE)
    vals[3] = "15.08.1975"
    payload = build_secure_qr(vals, use_gzip=True)
    res = decode_aadhaar(payload)
    assert res["outcome"] == "card"
    assert res["data"]["dob"] == "1975-08-15"


def test_decode_garbage_text():
    res = decode_aadhaar("invalid random text here")
    assert res["outcome"] == "garbage"


def test_decode_garbage_long_digits():
    res = decode_aadhaar("9" * 100)
    assert res["outcome"] == "garbage"


def test_decode_xml_with_unescaped_ampersand():
    xml = ('<PrintLetterBarcodeData uid="112233445566" '
           'name="M/S Ramesh & Sons" gender="M" dob="1982-03-25" '
           'house="Shop 4 & 5" street="Main & Market Rd" dist="Kolkata" state="West Bengal" pc="700001"/>')
    res = decode_aadhaar(xml)
    assert res["outcome"] == "card"
    assert res["source"] == "secure_qr_xml"
    assert res["data"]["full_name"] == "M/S Ramesh & Sons"
    assert res["data"]["aadhaar_last4"] == "5566"
    assert "Shop 4 & 5" in res["data"]["address"]


def test_decode_xml_with_bom():
    xml = ('\ufeff<?xml version="1.0"?><PrintLetterBarcodeData uid="111122223333" '
           'name="Ananya Roy" gender="F" dob="1995-11-20" state="West Bengal" pc="700029"/>')
    res = decode_aadhaar(xml)
    assert res["outcome"] == "card"
    assert res["data"]["full_name"] == "Ananya Roy"
    assert res["data"]["aadhaar_last4"] == "3333"


def test_decode_secure_qr_utf8_payload():
    vals = list(SAMPLE)
    vals[2] = "Aarav Sharma"
    vals[12] = "Maharashtra"
    raw = b"\xff".join(v.encode("utf-8") for v in vals) + b"\xff" + b"SIG" * 10
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as f:
        f.write(raw)
    payload = str(int.from_bytes(buf.getvalue(), "big"))
    res = decode_aadhaar(payload)
    assert res["outcome"] == "card"
    assert res["data"]["full_name"] == "Aarav Sharma"


def test_decode_additional_date_formats():
    from aadhaar import _to_iso_dob
    assert _to_iso_dob("15/08/1975") == "1975-08-15"
    assert _to_iso_dob("1975/08/15") == "1975-08-15"
    assert _to_iso_dob("1975.08.15") == "1975-08-15"
    assert _to_iso_dob("15-Aug-1975") == "1975-08-15"
    assert _to_iso_dob("15 Aug 1975") == "1975-08-15"
    assert _to_iso_dob("1975") == "1975-01-01"
    assert _to_iso_dob("1985-04-12T10:30:00") == "1985-04-12"
    assert _to_iso_dob("1985-04-12 00:00:00") == "1985-04-12"
    assert _to_iso_dob("invalid") is None


def test_decode_age_calculation():
    from aadhaar import _calc_age
    assert _calc_age("1990-01-01") is not None
    assert _calc_age("1990-01-01") > 30
    assert _calc_age(None) is None
    assert _calc_age("invalid") is None

    res = decode_aadhaar("AADHAAR|Ravi Kumar|M|1990-01-01|5544|Delhi")
    assert res["outcome"] == "card"
    assert res["data"]["age"] is not None
    assert res["data"]["age"] > 30


def test_decode_xml_full_attribute_names():
    xml = ('<PrintLetterBarcodeData uid="998877665544" '
           'name="Deepak Joshi" gender="M" dob="1984-06-15" '
           'house="Flat 101" street="Ring Road" landmark="Opp Police Station" '
           'location="Sector 62" postoffice="Noida PO" vtc="Noida" '
           'subdistrict="Dadri" district="Gautam Buddha Nagar" state="Uttar Pradesh" pincode="201309"/>')
    res = decode_aadhaar(xml)
    assert res["outcome"] == "card"
    assert res["source"] == "secure_qr_xml"
    assert res["data"]["full_name"] == "Deepak Joshi"
    assert res["data"]["aadhaar_last4"] == "5544"
    assert "Opp Police Station" in res["data"]["address"]
    assert "Noida PO" in res["data"]["address"]
    assert "201309" in res["data"]["address"]


def test_decode_secure_qr_double_zero_padding():
    vals = list(SAMPLE)
    raw = b"\xff".join(v.encode("ISO-8859-1") for v in vals) + b"\xff" + b"SIG" * 10
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as f:
        f.write(raw)
    comp = buf.getvalue()
    # Prepend 2 zero bytes before integer conversion
    big_int = int.from_bytes(b"\x00\x00" + comp, "big")
    payload = str(big_int)
    res = decode_aadhaar(payload)
    assert res["outcome"] == "card"
    assert res["data"]["full_name"] == "Ramesh Kumar"


