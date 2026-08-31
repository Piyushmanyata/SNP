import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from pymongo import ASCENDING

from db import (
    PERSON_CAMP_INDEX,
    PERSON_CAMP_INDEX_NAME,
    TRANSCRIPTION_PATIENT_INDEX,
    should_drop_person_camp_index,
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
