from conftest import run_db


def test_person_camp_is_partial_unique_and_transcription_patient_is_unique():
    async def body(database):
        return await database.patients.index_information(), await database.transcriptions.index_information()

    patients, transcriptions = run_db(body)
    person_camp = patients["person_id_1_camp_id_1"]
    assert person_camp["unique"] is True
    assert person_camp["partialFilterExpression"] == {"person_id": {"$type": "objectId"}}
    assert transcriptions["patient_id_1"]["unique"] is True
