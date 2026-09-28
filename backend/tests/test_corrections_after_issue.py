import csv
import io

import pytest
from bson import ObjectId
from fastapi import HTTPException

from models import CorrectionBody
from routes_clinical import add_correction, record_fulfilment
from routes_reports import export_camp_records
from seed import ADMIN, CLINICAL, MEDICINE, MEDICINE_ALT, NOW, fulfil, patient_doc, run_camp

A, B = MEDICINE["medicine_id"], MEDICINE_ALT["medicine_id"]


async def _issued(database):
    camp_id, patient_id, trans_id, rev_id = ObjectId(), ObjectId(), ObjectId(), ObjectId()
    await database.camps.insert_one({"_id": camp_id, "name": "Sikar Camp", "venue": "Sikar Bhawan", "is_active": True})
    await database.patients.insert_one(patient_doc(
        _id=patient_id, camp_id=camp_id, camp_day_id=ObjectId(), full_name="Sunita Devi",
        queue_status="seen", arrived_at=NOW, printed_at=NOW, seen_at=NOW,
        committed_revision_id=rev_id, clinical_generation=1,
    ))
    content = {
        "prescribed_lines": ["medicine", "specs_fixed"], "none_prescribed": False,
        "prescribed_medicines": [MEDICINE], "fixed_power_r": 2.0, "fixed_power_l": 2.0,
        "diagnosis_options": ["Cataract"], "bp": "120/80",
    }
    await database.prescription_revisions.insert_one({
        "_id": rev_id, "patient_id": patient_id, "camp_id": camp_id, "operation_id": str(ObjectId()), **content,
    })
    await database.transcriptions.insert_one({
        "_id": trans_id, "patient_id": patient_id, "camp_id": camp_id, "locked": True, **content,
    })
    for item_type in ("medicine", "specs_fixed"):
        await record_fulfilment(fulfil(trans_id, rev_id, item_type=item_type, status="fulfilled"),
                                actor=CLINICAL, background_tasks=None)
    return {"patient_id": patient_id, "trans_id": trans_id, "camp_id": camp_id}


async def _correct(ids, **fields):
    return await add_correction(CorrectionBody(
        transcription_id=str(ids["trans_id"]), reason="Doctor re-checked the paper", expected_generation=1,
        operation_id=str(ObjectId()), full_transcription_confirmed=True, **fields,
    ), actor=CLINICAL)


async def _line(database, ids, item_type):
    return await database.fulfilments.find_one({"transcription_id": ids["trans_id"], "item_type": item_type})


def test_a_medicine_given_stays_given_and_one_the_correction_adds_opens(monkeypatch):
    async def run(database):
        ids = await _issued(database)
        result = await _correct(ids, prescribed_medicine_ids=[A, B])
        medicine = await _line(database, ids, "medicine")
        assert [(o["name"], o["given"]) for o in medicine["medicine_outcomes"]] == [
            (MEDICINE["name"], True), (MEDICINE_ALT["name"], None),
        ]
        assert medicine["status"] == "partially_fulfilled"
        mark = medicine["corrected_after_issue"]
        assert str(mark["revision_id"]) == result["revision"]["id"]
        assert mark["by"] == str(CLINICAL["_id"])
        assert mark["at"]

    run_camp(monkeypatch, run)


def test_a_medicine_removed_after_it_was_given_stays_given_and_is_marked(monkeypatch):
    async def run(database):
        ids = await _issued(database)
        await _correct(ids, prescribed_medicine_ids=[B])
        medicine = await _line(database, ids, "medicine")
        by_name = {o["name"]: o for o in medicine["medicine_outcomes"]}
        assert by_name[MEDICINE["name"]]["given"] is True
        assert by_name[MEDICINE["name"]]["prescribed"] is False
        assert by_name[MEDICINE_ALT["name"]]["given"] is None
        assert medicine["corrected_after_issue"]

    run_camp(monkeypatch, run)


def test_a_fixed_power_changed_after_issue_keeps_the_issued_power_and_is_marked_not_reopened(monkeypatch):
    async def run(database):
        ids = await _issued(database)
        await _correct(ids, fixed_power_r=2.25, fixed_power_l=2.25)
        specs = await _line(database, ids, "specs_fixed")
        assert (specs["issued_power_r"], specs["issued_power_l"], specs["status"]) == (2.0, 2.0, "fulfilled")
        assert specs["corrected_after_issue"]
        assert "corrected_after_issue" not in await _line(database, ids, "medicine")

    run_camp(monkeypatch, run)


def test_a_reissue_after_a_correction_keeps_the_settled_issued_power(monkeypatch):
    async def run(database):
        ids = await _issued(database)
        result = await _correct(ids, fixed_power_r=2.25, fixed_power_l=2.25)
        await record_fulfilment(fulfil(
            ids["trans_id"], result["revision"]["id"], item_type="specs_fixed", status="fulfilled",
            reviewed_generation=result["registration"]["clinical_generation"],
        ), actor=CLINICAL, background_tasks=None)
        specs = await _line(database, ids, "specs_fixed")
        assert (specs["issued_power_r"], specs["issued_power_l"]) == (2.0, 2.0)
        assert specs["corrected_after_issue"]

    run_camp(monkeypatch, run)


def test_a_correction_that_leaves_the_issued_lines_alone_marks_nothing(monkeypatch):
    async def run(database):
        ids = await _issued(database)
        await _correct(ids, bp="135/85")
        for item_type in ("medicine", "specs_fixed"):
            assert "corrected_after_issue" not in await _line(database, ids, item_type)

    run_camp(monkeypatch, run)


def test_a_reopened_line_needs_a_fresh_paper_review(monkeypatch):
    async def run(database):
        ids = await _issued(database)
        old_revision = (await database.patients.find_one({"_id": ids["patient_id"]}))["committed_revision_id"]
        result = await _correct(ids, prescribed_medicine_ids=[A, B])
        outcomes = [{"medicine_id": A, "given": True}, {"medicine_id": B, "given": True}]
        with pytest.raises(HTTPException) as exc:
            await record_fulfilment(fulfil(ids["trans_id"], old_revision, item_type="medicine", status="fulfilled",
                                           medicine_outcomes=outcomes), actor=CLINICAL, background_tasks=None)
        assert exc.value.detail["code"] == "STALE_REVIEW"
        await record_fulfilment(fulfil(
            ids["trans_id"], result["revision"]["id"], item_type="medicine", status="fulfilled",
            medicine_outcomes=outcomes, reviewed_generation=result["registration"]["clinical_generation"],
        ), actor=CLINICAL, background_tasks=None)
        medicine = await _line(database, ids, "medicine")
        assert [o["given"] for o in medicine["medicine_outcomes"]] == [True, True]
        assert medicine["status"] == "fulfilled"
        assert medicine["corrected_after_issue"]

    run_camp(monkeypatch, run)


def test_the_export_shows_the_mark_the_open_medicine_and_the_fixed_power_trio(monkeypatch):
    async def run(database):
        ids = await _issued(database)
        await _correct(ids, prescribed_medicine_ids=[B], fixed_power_r=2.25, fixed_power_l=2.25)
        response = await export_camp_records(camp_id=str(ids["camp_id"]), actor=ADMIN)
        text = "".join([chunk async for chunk in response.body_iterator])
        (row,) = list(csv.DictReader(io.StringIO(text)))
        assert row["medicines_prescribed"] == MEDICINE_ALT["name"]
        assert row["medicines_not_given"] == MEDICINE_ALT["name"]
        assert (row["fixed_power_r"], row["issued_power_r"]) == ("'+2.25", "'+2.00")
        assert row["corrected_after_issue"] == "medicine;fixed_power_specs"

    run_camp(monkeypatch, run)


def test_a_reissue_keeps_a_medicine_the_correction_removed_after_it_was_given(monkeypatch):
    async def run(database):
        ids = await _issued(database)
        result = await _correct(ids, prescribed_medicine_ids=[B])
        await record_fulfilment(fulfil(
            ids["trans_id"], result["revision"]["id"], item_type="medicine", status="fulfilled",
            medicine_outcomes=[{"medicine_id": B, "given": True}],
            reviewed_generation=result["registration"]["clinical_generation"],
        ), actor=CLINICAL, background_tasks=None)
        medicine = await _line(database, ids, "medicine")
        assert [(o["name"], o["given"], o.get("prescribed", True)) for o in medicine["medicine_outcomes"]] == [
            (MEDICINE_ALT["name"], True, True), (MEDICINE["name"], True, False),
        ]
        assert medicine["status"] == "fulfilled"

    run_camp(monkeypatch, run)


def test_a_line_where_nothing_was_handed_over_never_reads_fulfilled(monkeypatch):
    async def run(database):
        ids = await _issued(database)
        await database.fulfilments.update_one(
            {"transcription_id": ids["trans_id"], "item_type": "medicine"},
            {"$set": {"medicine_outcomes": [{**MEDICINE, "given": False}], "status": "not_available"}},
        )
        await _correct(ids, prescribed_lines=["specs_fixed"], prescribed_medicine_ids=[])
        medicine = await _line(database, ids, "medicine")
        assert medicine["medicine_outcomes"] == []
        assert medicine["status"] == "not_available"

    run_camp(monkeypatch, run)


def test_a_catalogue_rename_does_not_reopen_a_medicine_already_given(monkeypatch):
    async def run(database):
        ids = await _issued(database)
        await database.medicines.update_one({"name": MEDICINE["name"]}, {"$set": {"name": "Moxifloxacin 0.5%"}})
        await _correct(ids, fixed_power_r=2.25, fixed_power_l=2.25)
        medicine = await _line(database, ids, "medicine")
        assert [o["given"] for o in medicine["medicine_outcomes"] if o.get("prescribed") is not False] == [True]
        assert "corrected_after_issue" not in medicine

    run_camp(monkeypatch, run)

