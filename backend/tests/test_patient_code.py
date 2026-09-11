"""The patient code is short, unguessable, and readable back from either case."""
import os
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "snp_test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("AADHAAR_HASH_PEPPER", "test-pepper")

from helpers import (  # noqa: E402
    PATIENT_CODE_ALPHABET,
    new_patient_code,
    parse_patient_identifier,
)


def test_the_code_is_eight_characters_the_qr_can_encode_in_alphanumeric_mode():
    code = new_patient_code()
    assert len(code) == 8
    assert set(code) <= set(PATIENT_CODE_ALPHABET)
    assert code == code.upper()


def test_the_alphabet_omits_the_characters_a_volunteer_would_misread():
    assert set("ILOU") & set(PATIENT_CODE_ALPHABET) == set()
    assert len(set(PATIENT_CODE_ALPHABET)) == 32


def test_codes_do_not_repeat():
    assert len({new_patient_code() for _ in range(500)}) == 500


def test_the_printed_prefix_is_stripped_whatever_its_case():
    assert parse_patient_identifier("SNP:K7M2QX9F") == "K7M2QX9F"
    assert parse_patient_identifier("snp:K7M2QX9F") == "K7M2QX9F"
    assert parse_patient_identifier("Snp:k7m2qx9f") == "K7M2QX9F"


def test_a_bare_code_a_url_and_a_registration_number_all_parse():
    assert parse_patient_identifier("  K7M2QX9F ") == "K7M2QX9F"
    assert parse_patient_identifier("https://sikarkolkata.io/p/K7M2QX9F") == "K7M2QX9F"
    assert parse_patient_identifier("1001") == "1001"


def test_an_empty_identifier_is_empty_rather_than_an_error():
    assert parse_patient_identifier("") == ""
    assert parse_patient_identifier(None) == ""
