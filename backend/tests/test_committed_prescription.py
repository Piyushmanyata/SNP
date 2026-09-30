"""Committed prescription: every reader of what was prescribed reads the committed revision, never the draft."""
from collections import Counter
from datetime import timedelta

import pytest
from bson import ObjectId

import committed_prescription
from clinical_state import CONTENT_FIELDS
from conftest import CommandLog
from models import CorrectionBody, TranscriptionBody, UndoCompletionBody
from routes_clinical import add_correction, clinical_history, create_transcription, record_fulfilment, undo_completion
from seed import CLINICAL, FIXED_POWER, MEDICINE, MEDICINE_ALT, NOW, patient_doc, run_camp, seed_camp
from test_camp_operations_matrix import RX, _issue_body, _printed_patient, _register_printed
from test_hospital_outcomes import _complete, _csv_rows, _lines

PRESCRIPTION_COLUMNS = (
    "diagnosis", "bp", "blood_sugar", "r_sph", "r_cyl", "r_axis", "l_sph", "l_cyl", "l_axis", "add",
    "medicines_prescribed", "medicines_not_given", "fixed_power_r", "fixed_power_l",
)


def _filled(row):
    return {column: row[column] for column in PRESCRIPTION_COLUMNS if row[column] != ""}


async def _undo(patient_id, generation, op="undo"):
    return await undo_completion(UndoCompletionBody(
        patient_id=str(patient_id), expected_generation=generation, reason="Wrong patient", operation_id=op,
    ), actor=CLINICAL)


async def _correct(patient_id, generation, op="correct", **fields):
    return await add_correction(CorrectionBody(
        patient_id=str(patient_id), reason="Doctor re-checked the paper", expected_generation=generation,
        operation_id=op, full_transcription_confirmed=True, **fields,
    ), actor=CLINICAL)


@pytest.mark.parametrize("lines,column,value", [
    (["medicine", "specs_fixed", "ot"], "fixed_power_r", "'+2.00"),
    (["medicine", "specs_made", "ot"], "r_sph", "'-1.00"),
])
def test_export_blanks_the_prescription_after_an_undo_even_when_the_draft_is_then_edited(monkeypatch, lines, column, value):
    async def run(db):
        camp_id, _day, patient = await _printed_patient(db)
        done = await _complete(patient, "complete", **_lines(lines, outcome="referral"), blood_sugar="140")
        (row,) = await _csv_rows(camp_id)
        assert (row["diagnosis"], row["bp"], row["blood_sugar"], row["medicines_prescribed"]) == (
            "Cataract", "120/80", "140", MEDICINE["name"],
        )
        assert (row[column], row["ot"]) == (value, "referred")

        await _undo(patient["_id"], done["registration"]["clinical_generation"])
        (row,) = await _csv_rows(camp_id)
        assert (row["full_name"], row["reg_no"], row["seen_at"]) == (patient["full_name"], str(patient["reg_no"]), "")
        assert row["arrived_at"] != ""
        assert _filled(row) == {}

        await create_transcription(TranscriptionBody(
            patient_id=str(patient["_id"]), diagnosis_options=["Glaucoma"], bp="150/95", blood_sugar="200",
            prescribed_medicine_ids=[MEDICINE_ALT["medicine_id"]], specs_measurements=RX,
            fixed_power_r=FIXED_POWER, fixed_power_l=FIXED_POWER,
        ), actor=CLINICAL)
        (row,) = await _csv_rows(camp_id)
        assert _filled(row) == {}

    run_camp(monkeypatch, run)


def test_export_blanks_the_prescription_for_a_patient_who_was_never_committed(monkeypatch):
    async def run(db):
        camp_id, _day, patient = await _printed_patient(db)
        await create_transcription(TranscriptionBody(
            patient_id=str(patient["_id"]), diagnosis_options=["Cataract"], bp="110/70", blood_sugar="120",
            prescribed_medicine_ids=[MEDICINE["medicine_id"]], specs_measurements=RX,
            fixed_power_r=FIXED_POWER, fixed_power_l=FIXED_POWER,
        ), actor=CLINICAL)
        assert await db.transcriptions.count_documents({"patient_id": patient["_id"]}) == 1
        (row,) = await _csv_rows(camp_id)
        assert (row["full_name"], row["reg_no"]) == (patient["full_name"], str(patient["reg_no"]))
        assert _filled(row) == {}

    run_camp(monkeypatch, run)


def test_export_shows_the_committed_revision_not_a_divergent_mirror(monkeypatch):
    async def run(db):
        camp_id, _day, patient = await _printed_patient(db)
        await _complete(patient, "complete", **_lines(["medicine", "specs_made"]), blood_sugar="140")
        await db.transcriptions.update_one({"patient_id": patient["_id"]}, {"$set": {
            "diagnosis_options": ["Glaucoma"], "bp": "1/1", "blood_sugar": "9",
            "prescribed_medicines": [MEDICINE_ALT], "specs_measurements": {"r_sph": "+9.00", "l_sph": "+9.00"},
            "fixed_power_r": FIXED_POWER, "fixed_power_l": FIXED_POWER,
        }})
        (row,) = await _csv_rows(camp_id)
        assert (row["diagnosis"], row["bp"], row["blood_sugar"], row["medicines_prescribed"]) == (
            "Cataract", "120/80", "140", MEDICINE["name"],
        )
        assert (row["r_sph"], row["l_sph"]) == ("'-1.00", "'-1.25")
        assert (row["fixed_power_r"], row["fixed_power_l"]) == ("", "")

    run_camp(monkeypatch, run)


def test_of_patient_returns_the_committed_revision_and_none_otherwise(monkeypatch):
    async def run(db):
        _camp, _day, patient = await _printed_patient(db)
        assert await committed_prescription.of_patient(db, patient) is None

        await create_transcription(TranscriptionBody(
            patient_id=str(patient["_id"]), diagnosis_options=["Glaucoma"], bp="150/95",
        ), actor=CLINICAL)
        patient = await db.patients.find_one({"_id": patient["_id"]})
        assert await committed_prescription.of_patient(db, patient) is None

        done = await _complete(patient, "complete")
        patient = await db.patients.find_one({"_id": patient["_id"]})
        revision = await committed_prescription.of_patient(db, patient)
        assert revision["_id"] == ObjectId(done["revision"]["id"])
        assert revision["diagnosis_options"] == ["Cataract"]
        async with db.client.start_session() as session:
            assert (await committed_prescription.of_patient(db, patient, session))["_id"] == revision["_id"]

        assert await committed_prescription.of_patient(db, {**patient, "committed_revision_id": ObjectId()}) is None

    run_camp(monkeypatch, run)


def test_of_patients_maps_only_committed_patients_by_patient_id(monkeypatch):
    log = CommandLog()

    async def run(db):
        _camp, day_id, first = await _printed_patient(db)
        ids = {"committed": first["_id"]}
        for name, phone in (("undone", "9876500002"), ("draft", "9876500003"), ("corrected", "9876500004")):
            ids[name] = ObjectId(await _register_printed(day_id, full_name=name, age=40, phone=phone))
        committed = await _complete({"_id": ids["committed"]}, "op-committed")
        undone = await _complete({"_id": ids["undone"]}, "op-undone")
        await _undo(ids["undone"], undone["registration"]["clinical_generation"], "op-undone-undo")
        await create_transcription(TranscriptionBody(
            patient_id=str(ids["draft"]), diagnosis_options=["Glaucoma"],
        ), actor=CLINICAL)
        corrected = await _complete({"_id": ids["corrected"]}, "op-corrected")
        correcting = await _correct(
            ids["corrected"], corrected["registration"]["clinical_generation"], diagnosis_options=["Glaucoma"], bp="140/90",
        )

        patients = await db.patients.find({"_id": {"$in": list(ids.values())}}).to_list(None)
        log.commands.clear()
        revisions = await committed_prescription.of_patients(db, patients)
        revision_reads = [name for name, collection in log.commands if collection == "prescription_revisions"]
        assert set(revisions) == {ids["committed"], ids["corrected"]}
        assert revisions[ids["committed"]]["_id"] == ObjectId(committed["revision"]["id"])
        assert revisions[ids["corrected"]]["_id"] == ObjectId(correcting["revision"]["id"])
        assert revisions[ids["corrected"]]["diagnosis_options"] == ["Glaucoma"]
        assert revision_reads == ["find"]

        log.commands.clear()
        by_id = {p["_id"]: p for p in patients}
        assert await committed_prescription.of_patients(db, []) == {}
        assert await committed_prescription.of_patients(db, [by_id[ids["undone"]], by_id[ids["draft"]]]) == {}
        assert [name for name, collection in log.commands if collection == "prescription_revisions"] == []

    run_camp(monkeypatch, run, listener=log)


def test_export_across_more_than_one_batch_reads_each_patients_own_revision(monkeypatch):
    log = CommandLog()
    total = 250

    async def run(db):
        camp_id, _days = await seed_camp(db, days=())
        patients, revisions, transcriptions = [], [], []
        for index in range(total):
            patient_id, revision_id = ObjectId(), ObjectId()
            patients.append(patient_doc(
                _id=patient_id, camp_id=camp_id, camp_day_id=ObjectId(), full_name=f"Patient {index:03d}",
                queue_status="seen", arrived_at=NOW, printed_at=NOW, seen_at=NOW,
                committed_revision_id=revision_id, clinical_generation=1,
            ))
            revisions.append({
                "_id": revision_id, "patient_id": patient_id, "camp_id": camp_id, "operation_id": f"op-{index}",
                "prescribed_lines": ["medicine"], "none_prescribed": False, "prescribed_medicines": [MEDICINE],
                "diagnosis_options": [f"Dx {index:03d}"],
            })
            transcriptions.append({
                "patient_id": patient_id, "camp_id": camp_id, "locked": True, "diagnosis_options": ["Draft"],
            })
        await db.patients.insert_many(patients)
        await db.prescription_revisions.insert_many(revisions)
        await db.transcriptions.insert_many(transcriptions)

        log.commands.clear()
        rows = await _csv_rows(camp_id)
        finds = Counter(collection for name, collection in log.commands if name == "find")
        assert len(rows) == total
        assert all(row["diagnosis"] == f"Dx {row['full_name'].split()[1]}" for row in rows)
        assert finds["prescription_revisions"] == 2
        assert finds["transcriptions"] == 2
        assert finds["fulfilments"] == 2

    run_camp(monkeypatch, run, listener=log)


def test_history_reports_the_committed_revision_and_null_for_a_draft(monkeypatch):
    async def run(db):
        camp_id = (await db.camps.insert_one({"name": "Eye camp"})).inserted_id
        person_id, revision_id = ObjectId(), ObjectId()
        committed = patient_doc(camp_id=camp_id, committed_revision_id=revision_id)
        draft = patient_doc(camp_id=camp_id)
        await db.patients.insert_many([committed, draft])
        await db.prescription_revisions.insert_one({
            "_id": revision_id, "patient_id": committed["_id"], "camp_id": camp_id, "diagnosis_options": ["Cataract"],
            "prescribed_lines": ["medicine"], "none_prescribed": False,
        })
        await db.transcriptions.insert_many([
            {"patient_id": committed["_id"], "camp_id": camp_id, "person_id": person_id, "created_at": NOW,
             "diagnosis_options": ["Cataract"], "locked": True},
            {"patient_id": draft["_id"], "camp_id": camp_id, "person_id": person_id,
             "created_at": NOW - timedelta(days=1), "diagnosis_options": ["Glaucoma"]},
        ])
        history = (await clinical_history(str(person_id), actor=CLINICAL))["history"]
        by_patient = {visit["transcription"]["patient_id"]: visit for visit in history}
        assert by_patient[str(committed["_id"])]["committed_revision"]["diagnosis_options"] == ["Cataract"]
        assert by_patient[str(draft["_id"])]["committed_revision"] is None
        assert by_patient[str(draft["_id"])]["transcription"]["diagnosis_options"] == ["Glaucoma"]

    run_camp(monkeypatch, run)


def test_a_correction_after_issue_leaves_the_fulfilments_patient_seen_at_unchanged(monkeypatch):
    async def run(db):
        _camp, _day, patient = await _printed_patient(db)
        done = await _complete(patient, "complete")
        generation = done["registration"]["clinical_generation"]
        await record_fulfilment(_issue_body(
            done["transcription"]["id"], done["revision"]["id"], generation, "issue",
        ), actor=CLINICAL, background_tasks=None)

        async def stamps():
            stored = await db.patients.find_one({"_id": patient["_id"]})
            line = await db.fulfilments.find_one({"item_type": "medicine"})
            return stored["seen_at"], line["patient_seen_at"]

        seen_at, line_seen_at = await stamps()
        assert seen_at is not None and line_seen_at == seen_at

        await _correct(patient["_id"], generation, bp="150/95")
        assert await stamps() == (seen_at, seen_at)

    run_camp(monkeypatch, run)


def test_mirror_equals_the_committed_revision_and_locked_tracks_the_commit(monkeypatch):
    async def run(db):
        async def assert_mirror_is_the_revision():
            stored = await db.patients.find_one({"_id": patient["_id"]})
            revision = await db.prescription_revisions.find_one({"_id": stored["committed_revision_id"]})
            transcription = await db.transcriptions.find_one({"patient_id": patient["_id"]})
            assert transcription["locked"] is True
            assert {field: transcription[field] for field in CONTENT_FIELDS} == {
                field: revision[field] for field in CONTENT_FIELDS
            }

        _camp, _day, patient = await _printed_patient(db)
        done = await _complete(
            patient, "complete", **_lines(["medicine", "specs_made", "ot"], outcome="referral"),
            blood_sugar="140", diagnosis_other="Dry eye", remarks="Review in a month", ot_notes="Refer to Sikar",
        )
        await assert_mirror_is_the_revision()

        corrected = await _correct(
            patient["_id"], done["registration"]["clinical_generation"], diagnosis_options=["Glaucoma"], bp="140/90",
        )
        await assert_mirror_is_the_revision()

        await _undo(patient["_id"], corrected["registration"]["clinical_generation"])
        transcription = await db.transcriptions.find_one({"patient_id": patient["_id"]})
        stored = await db.patients.find_one({"_id": patient["_id"]})
        assert transcription["locked"] is False
        assert stored["committed_revision_id"] is None

    run_camp(monkeypatch, run)
