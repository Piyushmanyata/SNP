"""Genuine offline Aadhaar Secure QR decoder.

Decodes on our own server (no UIDAI API call, no per-scan cost). We parse the
identity fields only; we do NOT verify the RSA signature (matches original ADR:
"not cryptographically verified"). Only the last-4 of Aadhaar is ever surfaced.
"""
import re
import sys
import zlib
import xml.etree.ElementTree as ET
from datetime import datetime

from helpers import IST

# A Secure QR carrying a photo runs to roughly 7k digits; anything larger is not a
# card, and int(str) is quadratic, so the cap is what keeps an unauthenticated
# decode cheap.
MAX_SECURE_QR_DIGITS = 16000
MAX_DECOMPRESSED_BYTES = 256 * 1024

if hasattr(sys, "set_int_max_str_digits"):
    try:
        sys.set_int_max_str_digits(MAX_SECURE_QR_DIGITS)
    except Exception:
        pass

FIELDS = [
    "indicator", "referenceid", "name", "dob", "gender", "careof", "district",
    "landmark", "house", "location", "pincode", "postoffice", "state",
    "street", "subdistrict", "vtc",
]


DATE_FORMATS = (
    "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%y", "%d/%m/%y",
    "%d.%m.%Y", "%Y.%m.%d", "%Y/%m/%d", "%d-%b-%Y", "%d %b %Y",
    "%d-%B-%Y", "%d %B %Y",
)


def _clean_date_string(raw: str) -> str:
    cleaned = (raw or "").strip(" '\"`\t\r\n")
    if "T" in cleaned:
        return cleaned.split("T")[0]
    if " " in cleaned:
        first = cleaned.split(" ")[0]
        if any(c in first for c in "-/.") or (len(first) == 4 and first.isdigit()):
            return first
    return cleaned


def _to_iso_dob(raw: str) -> str | None:
    cleaned = _clean_date_string(raw)
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    if len(cleaned) == 4 and cleaned.isdigit():
        return f"{cleaned}-01-01"
    return None


def _calc_age(dob: str | None) -> int | None:
    if not dob:
        return None
    try:
        d = datetime.strptime(dob, "%Y-%m-%d")
        today = datetime.now(IST)
        return today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    except Exception:
        return None


def _normalize_gender(g: str | None) -> str:
    gender = (g or "").strip().upper()[:1]
    return gender if gender in ("M", "F") else "O"


def _bounded_inflate(data: bytes, wbits: int) -> bytes:
    obj = zlib.decompressobj(wbits)
    out = obj.decompress(data, MAX_DECOMPRESSED_BYTES)
    if not obj.eof:
        raise zlib.error("Secure QR payload is truncated or over the decode limit")
    return out


def _decompress(qr: str) -> bytes:
    if len(qr) > MAX_SECURE_QR_DIGITS:
        raise ValueError("Secure QR payload is too long to be a card")
    big = int(qr)
    byte_array = big.to_bytes((big.bit_length() + 7) // 8, "big")
    for b_arr in (byte_array, b"\x00" + byte_array, b"\x00\x00" + byte_array):
        for wbits in (16 + zlib.MAX_WBITS, zlib.MAX_WBITS, -zlib.MAX_WBITS):
            try:
                return _bounded_inflate(b_arr, wbits)
            except zlib.error:
                pass
    raise ValueError("Could not decompress Secure QR payload")


def _extract_delimited_segments(data: bytes, field_names: list[str]) -> dict[str, str]:
    delims = [-1]
    for i, b in enumerate(data):
        if b == 255:
            delims.append(i)
            if len(delims) >= len(field_names) + 1:
                break
    fields = {}
    for i, name in enumerate(field_names):
        if i + 1 >= len(delims):
            break
        seg = data[delims[i] + 1: delims[i + 1]]
        try:
            fields[name] = seg.decode("utf-8")
        except UnicodeDecodeError:
            fields[name] = seg.decode("ISO-8859-1", errors="replace")
    return fields


def parse_secure_qr(qr: str) -> dict:
    data = _decompress(qr)
    header, _, remainder = data.partition(b"\xff")
    if header in (b"V2", b"V3", b"V4", b"V5"):
        data = remainder
    fields = _extract_delimited_segments(data, FIELDS)
    if len(fields) != len(FIELDS) or fields["indicator"] not in ("0", "1", "2", "3"):
        raise ValueError("Incomplete or invalid Secure QR fields")

    name = fields.get("name", "").strip()
    if not name.isprintable() or not any(c.isalpha() for c in name) or any(c.isdigit() for c in name):
        raise ValueError("Invalid name field decoded")

    ref = (fields.get("referenceid", "") or "").strip()
    if not re.fullmatch(r"[0-9]{18}(?:[0-9]{3})?", ref):
        raise ValueError("Invalid Secure QR reference")
    last4 = ref[:4]
    raw_gender = fields.get("gender", "").strip().upper()
    if raw_gender not in ("M", "F", "O", "T", "MALE", "FEMALE", "OTHER", "TRANSGENDER"):
        raise ValueError("Invalid Secure QR gender")
    gender = _normalize_gender(raw_gender)
    dob_iso = _to_iso_dob(fields.get("dob", ""))
    age = _calc_age(dob_iso)
    if age is None or age < 0:
        raise ValueError("Invalid Secure QR date of birth")
    addr_keys = ["house", "street", "landmark", "location", "postoffice", "vtc", "subdistrict", "district", "state", "pincode"]
    address = ", ".join(fields.get(k, "").strip() for k in addr_keys if fields.get(k, "").strip())

    return {
        "full_name": name,
        "gender": gender,
        "dob": dob_iso,
        "age": age,
        "aadhaar_last4": last4,
        "address": address,
    }


def _parse_xml_attributes(raw_xml: str) -> dict:
    cleaned = raw_xml.strip().lstrip("\ufeff")
    try:
        root = ET.fromstring(cleaned)
        return {k.lower(): v for k, v in root.attrib.items()}
    except Exception:
        sanitized = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;)", "&amp;", cleaned)
        try:
            root = ET.fromstring(sanitized)
            return {k.lower(): v for k, v in root.attrib.items()}
        except Exception:
            matches = re.findall(r'([a-zA-Z_:][a-zA-Z0-9._:-]*)\s*=\s*["\']([^"\']*)["\']', cleaned)
            return {k.lower(): v for k, v in matches}


def _extract_xml_address(attrs: dict) -> str:
    addr_parts = [
        attrs.get("house"),
        attrs.get("street"),
        attrs.get("landmark") or attrs.get("lm"),
        attrs.get("location") or attrs.get("loc"),
        attrs.get("postoffice") or attrs.get("po"),
        attrs.get("vtc") or attrs.get("village"),
        attrs.get("subdistrict") or attrs.get("subdist"),
        attrs.get("district") or attrs.get("dist"),
        attrs.get("state"),
        attrs.get("pincode") or attrs.get("pc"),
    ]
    return ", ".join(p.strip() for p in addr_parts if p and p.strip())


def parse_xml_qr(qr: str) -> dict:
    attrs = _parse_xml_attributes(qr)
    name = (attrs.get("name") or "").strip()
    if not name:
        raise ValueError("No name in XML QR")
    gender = _normalize_gender(attrs.get("gender"))
    uid = (attrs.get("uid") or "").strip()
    dob = attrs.get("dob") or attrs.get("yob") or ""
    dob_iso = _to_iso_dob(dob)
    address = _extract_xml_address(attrs)
    return {
        "full_name": name,
        "gender": gender,
        "dob": dob_iso,
        "age": _calc_age(dob_iso),
        "aadhaar_last4": uid[-4:] if uid else "",
        "address": address,
    }


def _try_decode_xml(raw: str) -> dict | None:
    if raw.startswith("<") or "<PrintLetterBarcodeData" in raw:
        try:
            return {"outcome": "card", "source": "secure_qr_xml", "data": parse_xml_qr(raw)}
        except Exception:
            return {"outcome": "garbage", "message": "Could not read the Aadhaar QR (XML)."}
    return None


def _try_decode_secure_qr(raw: str) -> dict | None:
    digits = re.sub(r"\s+", "", raw)
    if digits.isdigit() and len(digits) > 40:
        try:
            return {"outcome": "card", "source": "secure_qr", "data": parse_secure_qr(digits)}
        except Exception:
            return {"outcome": "garbage", "message": "Could not decode the Aadhaar Secure QR."}
    return None


def decode_aadhaar(raw: str) -> dict:
    raw = (raw or "").strip().lstrip("\ufeff")
    if not raw:
        return {"outcome": "not-aadhaar", "message": "No data captured."}
    if raw[:4].lower() == "snp:" or "/p/" in raw:
        return {"outcome": "not-aadhaar", "message": "This is a patient QR, not an Aadhaar card."}
    xml_result = _try_decode_xml(raw)
    if xml_result:
        return xml_result

    secure_result = _try_decode_secure_qr(raw)
    if secure_result:
        return secure_result

    return {"outcome": "garbage", "message": "Could not read an Aadhaar Secure QR."}
