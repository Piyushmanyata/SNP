from datetime import datetime, timezone

import pytest
from bson import ObjectId
from fastapi import HTTPException

import fulfilment_line
from models import MedicineOutcome
from routes_clinical import record_fulfilment
from seed import CLINICAL, MEDICINE, MEDICINE_ALT, fulfil, run_camp, seen_patient

A, B = MEDICINE["medicine_id"], MEDICINE_ALT["medicine_id"]
C_MEDICINE = {"medicine_id": "c" * 24, "name": "Atropine"}
C = C_MEDICINE["medicine_id"]
AT = datetime(2026, 9, 30, 10, 0, tzinfo=timezone.utc)
BY = "operator-1"
REVISION = {"prescribed_medicines": [MEDICINE, MEDICINE_ALT]}
MARK = {"revision_id": ObjectId(), "at": AT, "by": BY}
STATUS_STRINGS = ("fulfilled", "not_available", "partially_fulfilled", "deferred", "declined", "cancelled", "not_required")
VALID_STATUSES = {"specs_fixed": {"fulfilled"}, "specs_made": {"deferred", "cancelled"}, "ot": {"deferred", "declined"}}


def outcomes(**given):
    return [MedicineOutcome(medicine_id=mid, given=value) for mid, value in given.items()]


def issued(medicine, given):
    return {**medicine, "given": given}


def refusal(call, *args):
    with pytest.raises(HTTPException) as exc:
        call(*args)
    return exc.value.status_code, exc.value.detail["code"]


def a_line(item_type, **fields):
    return {"item_type": item_type, "status": "fulfilled", **fields}


def corrected(line, before, after):
    patch = fulfilment_line.correct(line, before, after, by=BY, at=AT)
    return patch and {**line, **patch}


def after_revision(*medicines, **fields):
    return {"_id": MARK["revision_id"], "prescribed_medicines": list(medicines), **fields}


@pytest.mark.parametrize("item_type", sorted(VALID_STATUSES))
@pytest.mark.parametrize("status", STATUS_STRINGS)
def test_check_issue_accepts_only_the_statuses_in_the_table(item_type, status):
    if status in VALID_STATUSES[item_type]:
        assert fulfilment_line.check_issue({}, item_type, status, []) == (status, None)
    else:
        assert refusal(fulfilment_line.check_issue, {}, item_type, status, []) == (400, "INVALID_FULFILMENT_ITEM_STATUS")


def test_an_unknown_item_type_is_refused():
    assert refusal(fulfilment_line.require_line, "bogus") == (400, "INVALID_FULFILMENT_ITEM_STATUS")
    assert refusal(fulfilment_line.check_issue, REVISION, "bogus", "fulfilled", []) == (400, "INVALID_FULFILMENT_ITEM_STATUS")


@pytest.mark.parametrize("given, chosen, expected", [
    ({A: True, B: True}, "not_available", "fulfilled"),
    ({A: False, B: False}, "fulfilled", "not_available"),
    ({A: True, B: False}, "fulfilled", "partially_fulfilled"),
])
def test_medicine_status_is_derived_from_outcomes_never_chosen(given, chosen, expected):
    status, _ = fulfilment_line.check_issue(REVISION, "medicine", chosen, outcomes(**given))
    assert status == expected


def test_medicine_outcomes_are_matched_to_the_revision_in_its_order_with_its_names():
    _, matched = fulfilment_line.check_issue(REVISION, "medicine", "fulfilled", outcomes(**{B: False, A: True}))
    assert matched == [
        {"medicine_id": A, "name": MEDICINE["name"], "given": True},
        {"medicine_id": B, "name": MEDICINE_ALT["name"], "given": False},
    ]


@pytest.mark.parametrize("revision, supplied", [
    (REVISION, outcomes(**{A: True})),
    (REVISION, outcomes(**{A: True, B: True, C: True})),
    (REVISION, outcomes(**{A: True}) + outcomes(**{A: True}) + outcomes(**{B: True})),
    (REVISION, []),
    ({"prescribed_medicines": []}, []),
    ({}, outcomes(**{A: True})),
])
def test_an_outcome_set_that_does_not_account_for_every_medicine_once_is_refused(revision, supplied):
    assert refusal(fulfilment_line.check_issue, revision, "medicine", "fulfilled", supplied) == (
        400, "MEDICINE_OUTCOMES_MISMATCH",
    )


def test_a_first_issue_returns_only_the_fields_that_apply():
    matched = [issued(MEDICINE, True)]
    assert fulfilment_line.issue("medicine", "fulfilled", matched, None, None) == {
        "status": "fulfilled", "medicine_outcomes": matched, "issued_power_r": None, "issued_power_l": None,
    }
    assert fulfilment_line.issue("specs_fixed", "fulfilled", None, (2.0, 2.25), None) == {
        "status": "fulfilled", "medicine_outcomes": None, "issued_power_r": 2.0, "issued_power_l": 2.25,
    }
    for item_type, status in (("specs_made", "deferred"), ("ot", "declined")):
        assert fulfilment_line.issue(item_type, status, None, None, None) == {
            "status": status, "medicine_outcomes": None, "issued_power_r": None, "issued_power_l": None,
        }


def test_a_reissue_over_an_uncorrected_line_lets_the_latest_win_and_keeps_removed_medicines():
    removed = {**issued(C_MEDICINE, True), "prescribed": False}
    prior = {"medicine_outcomes": [issued(MEDICINE, True), removed]}
    fields = fulfilment_line.issue("medicine", "fulfilled", [issued(MEDICINE, False)], None, prior)
    assert fields["medicine_outcomes"] == [issued(MEDICINE, False), removed]
    assert fields["status"] == "partially_fulfilled"
    assert "corrected_after_issue" not in fields


def test_a_reissue_over_a_corrected_line_cannot_change_settled_outcomes():
    prior = {"medicine_outcomes": [issued(MEDICINE, True), issued(MEDICINE_ALT, None)], "corrected_after_issue": MARK}
    supplied = [issued(MEDICINE, False), issued(MEDICINE_ALT, True)]
    fields = fulfilment_line.issue("medicine", "not_available", supplied, None, prior)
    assert fields["medicine_outcomes"] == [issued(MEDICINE, True), issued(MEDICINE_ALT, True)]
    assert fields["status"] == "fulfilled"
    assert fields["corrected_after_issue"] == MARK


def test_a_reissue_over_a_corrected_line_keeps_a_settled_not_available():
    prior = {"medicine_outcomes": [issued(MEDICINE, False)], "corrected_after_issue": MARK}
    fields = fulfilment_line.issue("medicine", "fulfilled", [issued(MEDICINE, True)], None, prior)
    assert fields["medicine_outcomes"] == [issued(MEDICINE, False)]
    assert fields["status"] == "not_available"


def test_a_reissue_over_a_corrected_fixed_power_line_keeps_the_settled_issued_power():
    prior = {"issued_power_r": 2.0, "issued_power_l": 2.0}
    kept = fulfilment_line.issue("specs_fixed", "fulfilled", None, (2.25, 2.25), {**prior, "corrected_after_issue": MARK})
    assert (kept["issued_power_r"], kept["issued_power_l"], kept["corrected_after_issue"]) == (2.0, 2.0, MARK)
    ordinary = fulfilment_line.issue("specs_fixed", "fulfilled", None, (2.25, 2.25), prior)
    assert (ordinary["issued_power_r"], ordinary["issued_power_l"]) == (2.25, 2.25)
    assert "corrected_after_issue" not in ordinary
    unset = fulfilment_line.issue(
        "specs_fixed", "fulfilled", None, (2.25, 2.25), {"issued_power_r": None, "corrected_after_issue": MARK},
    )
    assert (unset["issued_power_r"], unset["issued_power_l"]) == (2.25, 2.25)


def test_a_correction_that_adds_a_medicine_opens_it_and_marks_the_line():
    line = a_line("medicine", medicine_outcomes=[issued(MEDICINE, True)])
    patch = fulfilment_line.correct(line, {}, after_revision(MEDICINE, MEDICINE_ALT), by=BY, at=AT)
    assert patch == {
        "corrected_after_issue": MARK,
        "medicine_outcomes": [issued(MEDICINE, True), issued(MEDICINE_ALT, None)],
        "status": "partially_fulfilled",
    }
    nothing_given = a_line("medicine", medicine_outcomes=[issued(MEDICINE, False)])
    patch = fulfilment_line.correct(nothing_given, {}, after_revision(MEDICINE, MEDICINE_ALT), by=BY, at=AT)
    assert patch["status"] == "not_available"


def test_a_correction_that_removes_a_given_medicine_keeps_it_marked_prescribed_false():
    line = a_line("medicine", medicine_outcomes=[issued(MEDICINE, True), issued(MEDICINE_ALT, True)])
    patch = fulfilment_line.correct(line, {}, after_revision(MEDICINE_ALT), by=BY, at=AT)
    assert patch["medicine_outcomes"] == [issued(MEDICINE_ALT, True), {**issued(MEDICINE, True), "prescribed": False}]
    assert patch["status"] == "fulfilled"
    never_given = a_line("medicine", medicine_outcomes=[issued(MEDICINE, True), issued(MEDICINE_ALT, False)])
    patch = fulfilment_line.correct(never_given, {}, after_revision(MEDICINE), by=BY, at=AT)
    assert patch["medicine_outcomes"] == [issued(MEDICINE, True)]
    nothing_handed_over = a_line("medicine", medicine_outcomes=[issued(MEDICINE, False)])
    patch = fulfilment_line.correct(nothing_handed_over, {}, after_revision(), by=BY, at=AT)
    assert patch["medicine_outcomes"] == []
    assert patch["status"] == "not_available"


@pytest.mark.parametrize("now_prescribed", [
    [{"medicine_id": B, "name": "Renamed"}, {"medicine_id": A, "name": "Also renamed"}],
    [{"medicine_id": "n" * 24, "name": MEDICINE["name"]}, {"medicine_id": "m" * 24, "name": MEDICINE_ALT["name"]}],
])
def test_a_catalogue_rename_or_reorder_does_not_reopen_a_medicine(now_prescribed):
    line = a_line("medicine", medicine_outcomes=[issued(MEDICINE, True), issued(MEDICINE_ALT, False)])
    assert fulfilment_line.correct(line, {}, after_revision(*now_prescribed), by=BY, at=AT) is None


@pytest.mark.parametrize("before, after, expected", [
    ((2.0, 2.0), (2.25, 2.25), {"corrected_after_issue": MARK}),
    ((2.25, 2.25), (2.0, 2.0), None),
    ((2.0, 2.0), (2.0, 2.0), None),
])
def test_a_fixed_power_correction_marks_only_when_the_prescription_moved_away_from_what_was_issued(
    before, after, expected,
):
    line = a_line("specs_fixed", issued_power_r=2.0, issued_power_l=2.0)
    moved = (
        {"fixed_power_r": before[0], "fixed_power_l": before[1]},
        after_revision(fixed_power_r=after[0], fixed_power_l=after[1]),
    )
    assert fulfilment_line.correct(line, *moved, by=BY, at=AT) == expected


@pytest.mark.parametrize("item_type", ["specs_made", "ot"])
def test_correct_never_touches_lines_without_goods(item_type):
    line = a_line(item_type, status="deferred")
    before = {"fixed_power_r": 1.0, "fixed_power_l": 1.0}
    after = after_revision(MEDICINE, fixed_power_r=2.0, fixed_power_l=2.0, specs_measurements={"r_sph": "-1.00"})
    assert fulfilment_line.correct(line, before, after, by=BY, at=AT) is None


def test_issue_after_correct_is_the_pr_108_seam_for_an_added_medicine():
    line = a_line("medicine", medicine_outcomes=[issued(MEDICINE, True)])
    after = after_revision(MEDICINE, MEDICINE_ALT)
    marked = corrected(line, {}, after)
    status, matched = fulfilment_line.check_issue(after, "medicine", "fulfilled", outcomes(**{A: False, B: True}))
    fields = fulfilment_line.issue("medicine", status, matched, None, marked)
    assert fields["medicine_outcomes"] == [issued(MEDICINE, True), issued(MEDICINE_ALT, True)]
    assert fields["status"] == "fulfilled"
    assert fields["corrected_after_issue"] == MARK


def test_issue_after_correct_is_the_pr_108_seam_for_a_removed_medicine_and_an_added_one():
    line = a_line("medicine", medicine_outcomes=[issued(MEDICINE, True), issued(MEDICINE_ALT, True)])
    after = after_revision(MEDICINE_ALT, C_MEDICINE)
    marked = corrected(line, {}, after)
    assert marked["medicine_outcomes"] == [
        issued(MEDICINE_ALT, True), issued(C_MEDICINE, None), {**issued(MEDICINE, True), "prescribed": False},
    ]
    status, matched = fulfilment_line.check_issue(after, "medicine", "fulfilled", outcomes(**{B: False, C: True}))
    fields = fulfilment_line.issue("medicine", status, matched, None, marked)
    assert fields["medicine_outcomes"] == [
        issued(MEDICINE_ALT, True), issued(C_MEDICINE, True), {**issued(MEDICINE, True), "prescribed": False},
    ]
    assert fields["status"] == "fulfilled"
    assert fields["corrected_after_issue"] == MARK


def test_an_unknown_item_type_is_a_400_before_the_line_prescribed_409(monkeypatch):
    async def body(database):
        seen = await seen_patient(database)
        with pytest.raises(HTTPException) as exc:
            await record_fulfilment(
                fulfil(seen["trans_id"], seen["rev_id"], item_type="bogus", status="fulfilled"),
                actor=CLINICAL, background_tasks=None,
            )
        assert (exc.value.status_code, exc.value.detail["code"]) == (400, "INVALID_FULFILMENT_ITEM_STATUS")

    run_camp(monkeypatch, body)


def test_powers_are_resolved_before_the_status_is_checked(monkeypatch):
    async def body(database):
        for fixed_power, code in ((None, "FIXED_POWER_REQUIRED"), (2.0, "INVALID_FULFILMENT_ITEM_STATUS")):
            seen = await seen_patient(database, fixed_power=fixed_power)
            with pytest.raises(HTTPException) as exc:
                await record_fulfilment(
                    fulfil(seen["trans_id"], seen["rev_id"], item_type="specs_fixed", status="deferred"),
                    actor=CLINICAL, background_tasks=None,
                )
            assert (exc.value.status_code, exc.value.detail["code"]) == (400, code)

    run_camp(monkeypatch, body)
