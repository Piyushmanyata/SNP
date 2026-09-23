import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from pymongo import ASCENDING

from db import (
    HOUSEHOLD_LEDGER_INDEX_NAME,
    LEGACY_LEDGER_INDEX_NAME,
    LEDGER_INDEX_NAME,
    LEDGER_PARTIAL_FILTER,
    PERSON_CAMP_INDEX,
    PERSON_CAMP_INDEX_NAME,
    SETUP_REQUEST_INDEX_NAME,
    SETUP_REQUEST_PARTIAL,
    TRANSCRIPTION_PATIENT_INDEX,
    should_drop_household_ledger_index,
    should_drop_ledger_index,
    should_drop_person_camp_index,
    should_drop_setup_request_index,
)


def test_person_camp_index_is_partial_unique():
    assert PERSON_CAMP_INDEX["keys"] == [("person_id", ASCENDING), ("camp_id", ASCENDING)]
    assert PERSON_CAMP_INDEX["unique"] is True
    assert PERSON_CAMP_INDEX["partialFilterExpression"] == {"person_id": {"$type": "objectId"}}


def test_transcription_patient_id_is_unique():
    assert TRANSCRIPTION_PATIENT_INDEX["keys"] == "patient_id"
    assert TRANSCRIPTION_PATIENT_INDEX["unique"] is True


def test_non_unique_person_camp_index_is_dropped():
    assert PERSON_CAMP_INDEX_NAME == "person_id_1_camp_id_1"
    assert should_drop_person_camp_index({
        PERSON_CAMP_INDEX_NAME: {"unique": False, "key": [("person_id", 1), ("camp_id", 1)]},
    })
    assert not should_drop_person_camp_index({
        PERSON_CAMP_INDEX_NAME: {"unique": True, "key": [("person_id", 1), ("camp_id", 1)]},
    })
    assert not should_drop_person_camp_index({})


def test_ledger_index_from_the_household_grain_is_dropped_and_rebuilt():
    assert LEGACY_LEDGER_INDEX_NAME == "patient_id_1_message_type_1_event_date_1"
    assert LEDGER_INDEX_NAME == "patient_id_1_message_type_1_event_date_1_event_key_1"
    assert LEDGER_PARTIAL_FILTER == {"patient_id": {"$exists": True}}
    # An index built before the partial filter existed conflicts on name, so it must go.
    assert should_drop_ledger_index({LEDGER_INDEX_NAME: {"unique": True}})
    assert not should_drop_ledger_index({
        LEDGER_INDEX_NAME: {"unique": True, "partialFilterExpression": LEDGER_PARTIAL_FILTER},
    })
    assert not should_drop_ledger_index({})


def test_the_household_ledger_index_is_dropped_so_a_shared_phone_can_take_two_sends():
    assert should_drop_household_ledger_index({HOUSEHOLD_LEDGER_INDEX_NAME: {"unique": True}})
    assert not should_drop_household_ledger_index({LEDGER_INDEX_NAME: {"unique": True}})
    assert not should_drop_household_ledger_index({})


def test_null_setup_request_ids_do_not_share_a_unique_index_slot():
    assert SETUP_REQUEST_INDEX_NAME == "setup_request_id_1"
    assert SETUP_REQUEST_PARTIAL == {"setup_request_id": {"$type": "string"}}
    assert should_drop_setup_request_index({SETUP_REQUEST_INDEX_NAME: {"unique": True, "sparse": True}})
    assert not should_drop_setup_request_index({
        SETUP_REQUEST_INDEX_NAME: {"unique": True, "partialFilterExpression": SETUP_REQUEST_PARTIAL},
    })
    assert not should_drop_setup_request_index({})
