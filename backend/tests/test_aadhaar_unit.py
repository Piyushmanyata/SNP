import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import io
import gzip
import zlib
import os
import pytest
from aadhaar import (
    decode_aadhaar,
    parse_xml_qr,
    _to_iso_dob,
    _calc_age,
    _clean_date_string,
    _extract_delimited_segments,
    _normalize_gender,
    _parse_xml_attributes,
    _extract_xml_address,
)

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
    assert decode_aadhaar("   \t\n  ")["outcome"] == "not-aadhaar"
    assert decode_aadhaar("﻿")["outcome"] == "not-aadhaar"


def test_decode_near_miss_payloads_are_garbage():
    assert decode_aadhaar("1234567890")["outcome"] == "garbage"
    assert decode_aadhaar("<PrintLetterBarcodeData />")["outcome"] == "garbage"


@pytest.mark.parametrize("name", [None, "   "])
def test_xml_qr_without_a_name_is_rejected(name):
    named = f' name="{name}"' if name is not None else ""
    with pytest.raises(ValueError, match="No name in XML QR"):
        parse_xml_qr(f'<PrintLetterBarcodeData uid="123412345678"{named} gender="M" yob="1990"/>')


def test_xml_qr_without_a_uid_is_rejected():
    with pytest.raises(ValueError, match="Aadhaar number"):
        parse_xml_qr('<PrintLetterBarcodeData name="Sunita" gender="F" yob="1990"/>')


def test_xml_qr_hindi_script():
    res = parse_xml_qr('<PrintLetterBarcodeData uid="555566667777" name="राजेश शर्मा" gender="M" yob="1982" dist="वाराणसी" pc="221001"/>')
    assert res["full_name"] == "राजेश शर्मा"
    assert res["gender"] == "M"
    assert res["dob"] == "1982-01-01"
    assert "वाराणसी" in res["address"]


def test_xml_qr_short_address_attribute_names():
    res = parse_xml_qr('<PrintLetterBarcodeData uid="111122223333" name="Mohan Lal" gender="Male" yob="1990" lm="Shiv Mandir" loc="Sector 2" village="Khed" subdist="Haveli" dist="Pune" pc="411001"/>')
    for part in ("Shiv Mandir", "Sector 2", "Khed", "Haveli", "Pune", "411001"):
        assert part in res["address"]


def test_xml_qr_external_entity_is_never_resolved():
    res = parse_xml_qr(
        '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        '<PrintLetterBarcodeData uid="111122224444" name="&xxe; Hacked" gender="M" dob="1980-01-01"/>'
    )
    assert res["full_name"] == "&xxe; Hacked"
    assert res["aadhaar_last4"] == "4444"


def test_extract_delimited_segments_with_fewer_delimiters_than_fields():
    data = b"ind\xffref1234\xffJohn Doe\xff1990-01-01"
    res = _extract_delimited_segments(data, ["indicator", "referenceid", "name", "dob", "gender", "careof"])
    assert res["indicator"] == "ind"
    assert res["referenceid"] == "ref1234"
    assert res["name"] == "John Doe"
    assert "gender" not in res


def test_clean_date_string_strips_quotes_times_and_notes():
    assert _clean_date_string(" '1990-05-12' ") == "1990-05-12"
    assert _clean_date_string("`15/08/1947`") == "15/08/1947"
    assert _clean_date_string("1980-01-01T15:30:00.000Z") == "1980-01-01"
    assert _clean_date_string("1980-01-01 00:00:00") == "1980-01-01"
    assert _clean_date_string("1985 (approx)") == "1985"


def test_decode_patient_qr():
    assert decode_aadhaar("snp:12345") == {"outcome": "not-aadhaar", "message": "This is a patient QR, not an Aadhaar card."}
    assert decode_aadhaar("SNP:K7M2QX9F") == {"outcome": "not-aadhaar", "message": "This is a patient QR, not an Aadhaar card."}
    assert decode_aadhaar("https://camps.snp.org/p/abcde") == {"outcome": "not-aadhaar", "message": "This is a patient QR, not an Aadhaar card."}


def test_decode_demo_format_is_rejected():
    res = decode_aadhaar("AADHAAR|Priya Sharma|F|1992-04-10|9876|45 Station Rd, Howrah")
    assert res["outcome"] == "garbage"
    assert "data" not in res


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


@pytest.mark.parametrize("version", ["V2", "V3", "V4", "V5"])
@pytest.mark.parametrize("use_gzip", [True, False])
def test_decode_versioned_secure_qr(version, use_gzip):
    values = [version, *SAMPLE]
    values[2] = "432120241021140214946"
    result = decode_aadhaar(build_secure_qr(values, use_gzip=use_gzip))
    assert result["outcome"] == "card"
    assert result["data"] == {
        "full_name": "Ramesh Kumar",
        "gender": "M",
        "dob": "1975-08-15",
        "age": _calc_age("1975-08-15"),
        "aadhaar_last4": "4321",
        "address": "12-A, MG Road, Near Temple, Rampur, Rampur PO, Rampur, Modinagar, Ghaziabad, Uttar Pradesh, 201001",
    }


@pytest.mark.parametrize("index,value", [
    (0, "9"), (1, "2"), (1, "abcd20241021140214946"),
    (2, "432120241021140214946"), (2, "Name\x00Hidden"), (2, ""),
    (3, "31-02-1980"), (3, "9999"), (3, ""),
    (4, "Unexpected"), (4, ""),
])
@pytest.mark.parametrize("version", [None, "V3"])
def test_secure_qr_invalid_identity_is_not_a_card(index, value, version):
    values = list(SAMPLE)
    values[index] = value
    if version:
        values.insert(0, version)
    result = decode_aadhaar(build_secure_qr(values))
    assert result["outcome"] == "garbage"
    assert "data" not in result


@pytest.mark.parametrize("values", [SAMPLE[:3], SAMPLE[:-1], ["V99", *SAMPLE]])
def test_secure_qr_incomplete_or_unsupported_layout_is_not_a_card(values):
    result = decode_aadhaar(build_secure_qr(values))
    assert result["outcome"] == "garbage"
    assert "data" not in result


@pytest.mark.parametrize("version", [None, "V5"])
def test_secure_qr_unicode_name_year_of_birth_and_binary_tail(version):
    values = list(SAMPLE)
    values[1] = "000120241021140214946"
    values[2] = "অনন্যা রায়"
    values[3] = "1980"
    values[4] = "T"
    if version:
        values.insert(0, version)
        values.append("XXXXXX9876")
    raw = b"\xff".join(value.encode("utf-8") for value in values) + b"\xff"
    raw += bytes(range(256)) * 8
    payload = str(int.from_bytes(gzip.compress(raw), "big"))
    result = decode_aadhaar("\r\n".join(payload[i:i + 70] for i in range(0, len(payload), 70)))
    assert result["outcome"] == "card"
    assert result["data"]["full_name"] == "অনন্যা রায়"
    assert result["data"]["aadhaar_last4"] == "0001"
    assert result["data"]["dob"] == "1980-01-01"
    assert result["data"]["gender"] == "O"


def test_versioned_secure_qr_raw_deflate():
    raw = b"\xff".join(value.encode() for value in ["V3", *SAMPLE]) + b"\xff" + b"SIG" * 100
    compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    compressed = compressor.compress(raw) + compressor.flush()
    result = decode_aadhaar(str(int.from_bytes(compressed, "big")))
    assert result["outcome"] == "card"
    assert result["data"]["full_name"] == "Ramesh Kumar"
    assert result["data"]["aadhaar_last4"] == "5678"


def test_versioned_secure_qr_decode_endpoint(anon):
    from conftest import API

    response = anon.post(f"{API}/aadhaar/decode", json={"payload": build_secure_qr(["V3", *SAMPLE])})
    assert response.status_code == 200
    result = response.json()
    assert result["outcome"] == "card"
    assert result["data"]["full_name"] == "Ramesh Kumar"
    assert result["data"]["dob"] == "1975-08-15"
    assert result["data"]["age"] == _calc_age("1975-08-15")
    assert result["data"]["gender"] == "M"
    assert result["data"]["aadhaar_last4"] == "5678"
    rejected = anon.post(f"{API}/aadhaar/decode", json={"payload": build_secure_qr(["V99", *SAMPLE])})
    assert rejected.status_code == 200
    assert rejected.json()["outcome"] == "garbage"
    assert "data" not in rejected.json()


def test_decode_secure_qr_large_digits():
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
    assert _to_iso_dob("15/08/1975") == "1975-08-15"
    assert _to_iso_dob("1975/08/15") == "1975-08-15"
    assert _to_iso_dob("1975.08.15") == "1975-08-15"
    assert _to_iso_dob("15-Aug-1975") == "1975-08-15"
    assert _to_iso_dob("15 Aug 1975") == "1975-08-15"
    assert _to_iso_dob("1975") == "1975-01-01"
    assert _to_iso_dob("1985-04-12T10:30:00") == "1985-04-12"
    assert _to_iso_dob("1985-04-12 00:00:00") == "1985-04-12"
    assert _to_iso_dob("15 August 1985") == "1985-08-15"
    assert _to_iso_dob("01-Jan-2000") == "2000-01-01"
    assert _to_iso_dob(" '1990-05-12' ") == "1990-05-12"
    assert _to_iso_dob("invalid") is None
    assert _to_iso_dob("") is None
    assert _to_iso_dob(None) is None


def test_decode_age_calculation():
    assert _calc_age("1990-01-01") is not None
    assert _calc_age("1990-01-01") > 30
    assert _calc_age(None) is None
    assert _calc_age("invalid") is None

    res = decode_aadhaar('<PrintLetterBarcodeData name="Ravi Kumar" gender="M" dob="1990-01-01" uid="5544" street="Delhi"/>')
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


def test_normalize_gender_helper():
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


def test_parse_xml_attributes_helper():
    xml = '<PrintLetterBarcodeData uid="1234" name="Test User" gender="F" />'
    attrs = _parse_xml_attributes(xml)
    assert attrs["uid"] == "1234"
    assert attrs["name"] == "Test User"
    assert attrs["gender"] == "F"


def test_extract_xml_address_helper():
    attrs = {
        "house": "42",
        "street": "Main St",
        "district": "City",
        "state": "State",
        "pincode": "123456",
    }
    addr = _extract_xml_address(attrs)
    assert addr == "42, Main St, City, State, 123456"


@pytest.mark.parametrize("xml", [
    '<anything name="Not Aadhaar" gender="F" dob="1975-06-14" uid="123456781234"/>',
    '<PrintLetterBarcodeData name="Sunita Devi" gender="F" dob="1975-06-14" uid="12345678',
    '<PrintLetterBarcodeData name="Sunita Devi" gender="F" dob="2099-06-14" uid="123456781234"/>',
    '<PrintLetterBarcodeData name="Sunita Devi" gender="F" dob="1975-06-14" uid="12345"/>',
    '<PrintLetterBarcodeData name="Sunita Devi" gender="F" dob="1850-06-14" uid="123456781234"/>',
    '<PrintLetterBarcodeData name="Sunita Devi" gender="F" uid="123456781234"/>',
])
def test_decode_xml_rejects_forged_or_impossible_cards(xml):
    res = decode_aadhaar(xml)
    assert res["outcome"] == "garbage"
    assert "data" not in res
