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

if hasattr(sys, "set_int_max_str_digits"):
    try:
        sys.set_int_max_str_digits(200000)
    except Exception:
        pass

# Secure QR v2 delimiter-separated text fields (delimiter = byte 0xFF)
FIELDS = [
    "indicator", "referenceid", "name", "dob", "gender", "careof", "district",
    "landmark", "house", "location", "pincode", "postoffice", "state",
    "street", "subdistrict", "vtc",
]


def _to_iso_dob(raw: str):
    raw = (raw or "").strip()
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%y", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # year-only fallback
    if len(raw) == 4 and raw.isdigit():
        return f"{raw}-01-01"
    return None


def _decompress(qr: str) -> bytes:
    big = int(qr)
    byte_array = big.to_bytes((big.bit_length() + 7) // 8, "big")
    try:
        return zlib.decompress(byte_array, 16 + zlib.MAX_WBITS)  # gzip header
    except zlib.error:
        pass
    try:
        return zlib.decompress(byte_array)  # raw zlib fallback
    except zlib.error:
        return zlib.decompress(byte_array, -zlib.MAX_WBITS)  # raw deflate fallback


def parse_secure_qr(qr: str) -> dict:
    """Parse a Secure QR v2 big-integer payload. Raises on malformed input."""
    data = _decompress(qr)
    delim = [-1]
    for i, b in enumerate(data):
        if b == 255:
            delim.append(i)
            if len(delim) >= len(FIELDS) + 1:  # enough to bound every text field
                break
    fields = {}
    for i in range(len(FIELDS)):
        if i + 1 >= len(delim):
            break
        seg = data[delim[i] + 1: delim[i + 1]]
        fields[FIELDS[i]] = seg.decode("ISO-8859-1")

    name = fields.get("name", "").strip()
    if not name:
        raise ValueError("No name field decoded")
    ref = fields.get("referenceid", "")
    last4 = ref[:4] if len(ref) >= 4 else ""
    gender = (fields.get("gender", "") or "").strip().upper()[:1]
    if gender not in ("M", "F"):
        gender = "O"
    addr_keys = ["house", "street", "landmark", "location", "vtc", "subdistrict", "district", "state", "pincode"]
    address = ", ".join(fields.get(k, "").strip() for k in addr_keys if fields.get(k, "").strip())
    return {
        "full_name": name,
        "gender": gender,
        "dob": _to_iso_dob(fields.get("dob", "")),
        "aadhaar_last4": last4.zfill(4) if last4 else "",
        "address": address,
    }


def parse_xml_qr(qr: str) -> dict:
    """Parse the older (pre-2018) XML PrintLetterBarcodeData QR."""
    root = ET.fromstring(qr.strip())
    attrs = {k.lower(): v for k, v in root.attrib.items()}
    name = (attrs.get("name") or "").strip()
    if not name:
        raise ValueError("No name in XML QR")
    gender = (attrs.get("gender") or "").strip().upper()[:1]
    if gender not in ("M", "F"):
        gender = "O"
    uid = attrs.get("uid", "")
    dob = attrs.get("dob") or attrs.get("yob") or ""
    addr_keys = ["house", "street", "lm", "loc", "vtc", "subdist", "dist", "state", "pc"]
    address = ", ".join((attrs.get(k) or "").strip() for k in addr_keys if (attrs.get(k) or "").strip())
    return {
        "full_name": name,
        "gender": gender,
        "dob": _to_iso_dob(dob),
        "aadhaar_last4": uid[-4:] if uid else "",
        "address": address,
    }


def decode_aadhaar(raw: str) -> dict:
    """Return {outcome, data|message}. outcome in card|garbage|not-aadhaar."""
    raw = (raw or "").strip()
    if not raw:
        return {"outcome": "not-aadhaar", "message": "No data captured."}
    if raw.startswith("snp:") or "/p/" in raw:
        return {"outcome": "not-aadhaar", "message": "This is a patient QR, not an Aadhaar card."}

    # Demo/simulated card (kept for testing without a real card)
    if raw.upper().startswith("AADHAAR|"):
        parts = raw.split("|")
        if len(parts) < 6:
            return {"outcome": "garbage", "message": "Aadhaar QR data is incomplete."}
        gender = (parts[2] or "").upper()[:1]
        gender = gender if gender in ("M", "F", "O") else "O"
        return {"outcome": "card", "source": "demo", "data": {
            "full_name": parts[1].strip(), "gender": gender, "dob": parts[3].strip(),
            "aadhaar_last4": parts[4].strip()[-4:].zfill(4), "address": "|".join(parts[5:]).strip(),
        }}

    # Old XML QR
    if raw.startswith("<"):
        try:
            return {"outcome": "card", "source": "secure_qr_xml", "data": parse_xml_qr(raw)}
        except Exception:
            return {"outcome": "garbage", "message": "Could not read the Aadhaar QR (XML)."}

    # Secure QR v2 big-integer payload
    digits = re.sub(r"\s+", "", raw)
    if digits.isdigit() and len(digits) > 40:
        try:
            return {"outcome": "card", "source": "secure_qr", "data": parse_secure_qr(digits)}
        except Exception:
            return {"outcome": "garbage", "message": "Could not decode the Aadhaar Secure QR."}

    return {"outcome": "garbage", "message": "Could not read an Aadhaar Secure QR."}
