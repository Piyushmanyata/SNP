"""Printing through its interface: the Print window, the Print verdict with its atomic filter, and the Sheet stamp."""

from datetime import datetime, timedelta
from itertools import product

import pytest
from bson import ObjectId
from fastapi import HTTPException

import printing
import routes_camps
import routes_desk
from conftest import CommandLog, advance_clock, freeze_clock
from helpers import IST, as_utc, iso
from serializers import ser_patient
from seed import ACTOR, ADMIN, NOW, TODAY, TOMORROW, OTHER_DAY, day, patient_doc, run_camp, seed_camp

OPEN = {"printing_open": True}
CLOSED = {"printing_open": False}
STATE_KEYS = {"printing_open", "operating_day_id", "operating_day_date", "mode", "override_expires_at", "server_time"}
MESSAGES = {
    "ALREADY_SEEN": "The doctor has already seen this patient. The prescription cannot be printed again.",
    "NOT_ARRIVED": "Scan the patient in at the door before printing.",
    "PRINT_WINDOW_CLOSED": "The print window is closed.",
    "NEEDS_DOOR_SCAN": "Scan this patient's Aadhaar card at the door, or record a No-card print.",
}


def at(offset, hhmm):
    return datetime.fromisoformat(f"{day(offset)}T{hhmm}").replace(tzinfo=IST)


def code_of(exc):
    return exc.detail["code"] if exc else None


@pytest.mark.parametrize("schedule, override, now, expected", [
    ((0, 1), None, at(0, "10:00"), (True, 0, "automatic", None)),
    ((1, 2), None, at(0, "10:00"), (False, None, "automatic", None)),
    ((0, 2), ("enable", 2, at(1, "00:00")), at(0, "10:00"), (True, 2, "enable", at(1, "00:00"))),
    ((0,), ("enable", "unknown", at(1, "00:00")), at(0, "10:00"), (False, None, "enable", at(1, "00:00"))),
    ((0,), ("disable", None, at(1, "00:00")), at(0, "10:00"), (False, None, "disable", at(1, "00:00"))),
    ((0,), ("disable", None, at(0, "09:00")), at(0, "10:00"), (True, 0, "automatic", None)),
    ((0, 1), None, at(0, "23:59"), (True, 0, "automatic", None)),
    ((0, 1), None, at(1, "00:01"), (True, 1, "automatic", None)),
], ids=[
    "automatic-today", "no-today-in-the-schedule", "enable-another-day", "enable-an-unknown-day", "disable",
    "expired-override", "last-minute-of-the-ist-day", "first-minute-of-the-next-ist-day",
])
def test_resolve_table(schedule, override, now, expected):
    days = {offset: {"_id": ObjectId(), "day_date": day(offset)} for offset in schedule}
    camp = {"print_override": None}
    if override:
        mode, target, expires = override
        camp["print_override"] = {
            "mode": mode, "day_id": days[target]["_id"] if target in days else ObjectId(), "expires_at": expires,
        }
    is_open, operating, mode, expires = expected

    state = printing.resolve(camp, list(days.values()), now=now)

    assert set(state) == STATE_KEYS
    assert state["printing_open"] is is_open
    assert state["operating_day_id"] == (str(days[operating]["_id"]) if operating is not None else None)
    assert state["operating_day_date"] == (day(operating) if operating is not None else None)
    assert state["mode"] == mode
    assert state["override_expires_at"] == (iso(expires) if expires else None)
    assert state["server_time"] == iso(as_utc(now))
    assert state["printing_open"] == (state["operating_day_id"] is not None)


def test_resolve_without_a_camp_or_days_is_closed_and_automatic():
    state = printing.resolve(None, [], now=at(0, "10:00"))
    assert (state["printing_open"], state["operating_day_id"], state["mode"]) == (False, None, "automatic")


def test_a_day_is_operated_only_when_it_is_the_operating_day():
    today, other = {"_id": ObjectId(), "day_date": day(0)}, {"_id": ObjectId(), "day_date": day(1)}
    state = printing.resolve({}, [today, other], now=at(0, "10:00"))
    assert printing.operates(state, today) is True
    assert printing.operates(state, other) is False
    assert printing.operates(printing.resolve({}, [other], now=at(0, "10:00")), today) is False


def test_load_reads_the_camp_days_once_and_sorts_them(monkeypatch):
    log = CommandLog()

    async def run(database):
        camp_id, _ids = await seed_camp(database, days=(OTHER_DAY, TODAY, TOMORROW))
        camp = await database.camps.find_one({"_id": camp_id})
        log.commands.clear()
        days, state = await printing.load(database, camp)
        assert [d["day_date"] for d in days] == [TODAY, TOMORROW, OTHER_DAY]
        assert [c for c in log.commands if c[0] == "find" and c[1] == "camp_days"] == [("find", "camp_days")]
        assert state["operating_day_id"] == str(days[0]["_id"])
        assert set(state) == STATE_KEYS

    run_camp(monkeypatch, run, listener=log)


def test_the_active_camp_carries_the_printing_state_and_each_day_says_if_it_operates(monkeypatch):
    async def run(database):
        camp_id, (today_id, _tomorrow_id) = await seed_camp(database, days=(TODAY, TOMORROW), camp_date=TODAY)
        out = await routes_camps.active_camp(actor=ADMIN)
        assert set(out) == {"camp", "days"} | STATE_KEYS
        assert out["operating_day_id"] == str(today_id) and out["printing_open"] is True
        assert [(d["day_date"], d["printing_open"]) for d in out["days"]] == [(TODAY, True), (TOMORROW, False)]
        assert (await routes_camps.list_days(str(camp_id), actor=ADMIN))["days"] == out["days"]
        assert await routes_camps.list_days(str(ObjectId()), actor=ADMIN) == {"days": []}

    run_camp(monkeypatch, run)


@pytest.mark.parametrize("fields, state, stamped, code", [
    ({"queue_status": "seen"}, OPEN, False, "ALREADY_SEEN"),
    ({"queue_status": "seen", "arrived_at": NOW, "printed_at": NOW}, CLOSED, False, "ALREADY_SEEN"),
    ({}, OPEN, False, "NOT_ARRIVED"),
    ({}, CLOSED, False, "NOT_ARRIVED"),
    ({"arrived_at": NOW, "printed_at": NOW}, CLOSED, False, None),
    ({"arrived_at": NOW, "printed_at": NOW, "identity_recheck_required": True}, CLOSED, False, None),
    ({"arrived_at": NOW, "printed_at": NOW, "identity_recheck_required": True}, OPEN, False, None),
    ({"arrived_at": NOW}, CLOSED, False, "PRINT_WINDOW_CLOSED"),
    ({"arrived_at": NOW, "identity_recheck_required": True}, CLOSED, False, "PRINT_WINDOW_CLOSED"),
    ({"arrived_at": NOW, "identity_recheck_required": True}, OPEN, False, "NEEDS_DOOR_SCAN"),
    ({"arrived_at": NOW}, OPEN, False, None),
    ({"arrived_at": NOW}, CLOSED, True, None),
    ({"arrived_at": NOW}, OPEN, True, None),
    ({"arrived_at": NOW, "identity_recheck_required": True}, CLOSED, True, "NEEDS_DOOR_SCAN"),
    ({"arrived_at": NOW, "queue_status": "seen"}, CLOSED, True, "ALREADY_SEEN"),
], ids=[
    "seen", "seen-beats-printed-and-a-closed-window", "unarrived-open", "unarrived-closed", "printed-closed",
    "printed-beats-the-recheck-closed", "printed-beats-the-recheck-open", "arrived-closed",
    "closed-beats-the-recheck", "recheck-open", "arrived-open", "fresh-stamp-skips-the-closed-window",
    "fresh-stamp-open", "fresh-stamp-never-skips-the-recheck", "fresh-stamp-never-skips-seen",
])
def test_refusal_order_table(monkeypatch, fields, state, stamped, code):
    freeze_clock(monkeypatch)
    patient = {"_id": ObjectId(), **fields}
    stamp = printing.sign_sheet(patient, OPEN) if stamped else None
    assert code_of(printing.refusal(patient, state, stamp)) == code


def test_errors_keep_their_codes_and_messages():
    for code, message in MESSAGES.items():
        error = printing.error(code)
        assert (error.status_code, error.detail) == (409, {"code": code, "message": message})
    for raised, code in (
        (lambda: printing.require_open(CLOSED), "PRINT_WINDOW_CLOSED"),
        (lambda: printing.require_open({}), "PRINT_WINDOW_CLOSED"),
        (lambda: printing.require_not_seen({"queue_status": "seen"}), "ALREADY_SEEN"),
    ):
        with pytest.raises(HTTPException) as exc:
            raised()
        assert (exc.value.status_code, exc.value.detail) == (409, {"code": code, "message": MESSAGES[code]})
    assert printing.require_open(OPEN) is None
    assert printing.require_not_seen({"queue_status": "arrived"}) is None


def test_the_atomic_filter_matches_the_verdict_for_every_patient_state(monkeypatch):
    missing = object()
    grid = list(product(("registered", "arrived", "seen"), (None, missing, NOW), (None, missing, NOW), (False, True)))

    async def run(database):
        camp_id, (day_id,) = await seed_camp(database)
        for queue_status, arrived_at, printed_at, recheck in grid:
            fields = {"arrived_at": arrived_at, "printed_at": printed_at}
            await database.patients.insert_one(patient_doc(
                camp_id=camp_id, camp_day_id=day_id, queue_status=queue_status, identity_recheck_required=recheck,
                **{name: value for name, value in fields.items() if value is not missing},
            ))
        rows = await database.patients.find().to_list(None)
        assert len(rows) == len(grid)
        for stored in rows:
            expected = printing.refusal(stored, OPEN) is None and not stored.get("printed_at")
            assert await database.patients.count_documents(printing.first_print_filter(stored["_id"])) == int(expected), stored
        drifted = next(
            r for r in rows
            if not r.get("arrived_at") and not r.get("printed_at") and r["queue_status"] != "seen" and not r["identity_recheck_required"]
        )
        assert await database.patients.count_documents(printing.first_print_filter(drifted["_id"])) == 0

    run_camp(monkeypatch, run)


def test_a_patient_seen_between_the_read_and_the_write_is_not_stamped(monkeypatch):
    async def run(database):
        camp_id, (day_id,) = await seed_camp(database)
        stale = patient_doc(
            _id=ObjectId(), camp_id=camp_id, camp_day_id=day_id, queue_status="arrived", arrived_at=NOW, printed_at=None,
            patient_qr="qr-stale", full_name="Stale Read",
        )
        await database.patients.insert_one({**stale, "queue_status": "seen"})
        camp = await database.camps.find_one({"_id": camp_id})
        with pytest.raises(HTTPException) as exc:
            await routes_desk._prescription_payload(database, stale, ACTOR, True, camp)
        assert (exc.value.status_code, code_of(exc.value)) == (409, "PRINT_CONFLICT")
        assert (await database.patients.find_one({"_id": stale["_id"]}))["printed_at"] is None

    run_camp(monkeypatch, run)


HELD = {"arrived_at": NOW, "identity_recheck_required": True}
NO_CARD = {"reason": "no_card", "note": None, "by": "x", "at": NOW}


@pytest.mark.parametrize("fields, state, expected", [
    ({}, OPEN, (False, "NEEDS_DOOR_SCAN", "booked")),
    ({}, CLOSED, (False, "NEEDS_DOOR_SCAN", "booked")),
    ({"identity_recheck_required": True}, OPEN, (False, "NEEDS_DOOR_SCAN", "booked")),
    ({"no_card_print": NO_CARD}, OPEN, (True, None, "booked")),
    ({"no_card_print": NO_CARD}, CLOSED, (False, "PRINT_WINDOW_CLOSED", "booked")),
    ({"no_card_print": NO_CARD, "identity_recheck_required": True}, OPEN, (False, "NEEDS_DOOR_SCAN", "booked")),
    ({"arrived_at": NOW}, OPEN, (True, None, "arrived")),
    ({"arrived_at": NOW}, CLOSED, (False, "PRINT_WINDOW_CLOSED", "arrived")),
    (HELD, OPEN, (False, "NEEDS_DOOR_SCAN", "arrived")),
    ({**HELD, "no_card_print": NO_CARD}, OPEN, (False, "NEEDS_DOOR_SCAN", "arrived")),
    ({"arrived_at": NOW, "printed_at": NOW}, OPEN, (True, None, "printed")),
    ({"arrived_at": NOW, "printed_at": NOW}, CLOSED, (True, None, "printed")),
    ({**HELD, "printed_at": NOW}, CLOSED, (True, None, "printed")),
    ({"arrived_at": NOW, "printed_at": NOW, "queue_status": "seen"}, OPEN, (False, "ALREADY_SEEN", "seen")),
    ({"queue_status": "seen"}, OPEN, (False, "ALREADY_SEEN", "seen")),
], ids=[
    "booking", "booking-closed", "held-booking", "no-card-print", "no-card-print-closed", "no-card-print-still-held",
    "arrived", "arrived-closed", "arrived-and-held", "arrived-with-a-no-card-print-still-held", "printed",
    "printed-closed", "printed-and-held", "seen-after-print", "seen-unarrived",
])
def test_verdict_shape_and_stage_ladder(fields, state, expected):
    allowed, code, stage = expected
    assert printing.verdict({"_id": ObjectId(), **fields}, state) == {"allowed": allowed, "code": code, "stage": stage}


def test_the_verdict_never_says_not_arrived():
    for fields, state in product(({}, {"no_card_print": NO_CARD}, {"arrived_at": NOW}), (OPEN, CLOSED)):
        assert printing.verdict(fields, state)["code"] != "NOT_ARRIVED"


def test_verdict_reads_the_serialised_patient_the_same_way():
    grid = product(
        ("registered", "arrived", "seen"), (None, NOW), (None, NOW), (None, NO_CARD), (False, True), (OPEN, CLOSED),
    )
    for queue_status, arrived_at, printed_at, no_card_print, recheck, state in grid:
        stored = patient_doc(
            _id=ObjectId(), queue_status=queue_status, arrived_at=arrived_at, printed_at=printed_at,
            no_card_print=no_card_print, identity_recheck_required=recheck,
        )
        assert printing.verdict(ser_patient(stored), state) == printing.verdict(stored, state), stored


def test_a_verdict_is_attached_to_a_serialised_patient_only_when_a_state_is_given():
    stored = patient_doc(_id=ObjectId(), queue_status="arrived", arrived_at=NOW)
    assert "print" not in ser_patient(stored)
    assert ser_patient(stored, OPEN)["print"] == printing.verdict(stored, OPEN)
    assert {k: v for k, v in ser_patient(stored, OPEN).items() if k != "print"} == ser_patient(stored)


def test_sheet_stamp_round_trip_and_forgeries(monkeypatch):
    freeze_clock(monkeypatch)
    patient = {"_id": ObjectId(), "arrived_at": NOW}
    other = {"_id": ObjectId(), "arrived_at": NOW}
    stamp = printing.sign_sheet(patient, OPEN)

    assert printing.refusal(patient, CLOSED, stamp) is None
    tampered = stamp[:-1] + ("0" if stamp[-1] != "0" else "1")
    for forged in (None, "", tampered, printing.sign_sheet(other, OPEN), "not-a-stamp", "abc.def", "123.é", "١٢٣.abc", "."):
        assert code_of(printing.refusal(patient, CLOSED, forged)) == "PRINT_WINDOW_CLOSED", forged
    assert code_of(printing.refusal({**patient, "identity_recheck_required": True}, CLOSED, stamp)) == "NEEDS_DOOR_SCAN"

    advance_clock(timedelta(days=1))
    assert code_of(printing.refusal(patient, CLOSED, stamp)) == "PRINT_WINDOW_CLOSED"


def test_a_sheet_stamp_is_only_minted_while_the_window_is_open(monkeypatch):
    freeze_clock(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        printing.sign_sheet({"_id": ObjectId()}, CLOSED)
    assert code_of(exc.value) == "PRINT_WINDOW_CLOSED"
    fetched_ms, _, signature = printing.sign_sheet({"_id": ObjectId()}, OPEN).partition(".")
    assert fetched_ms.isdecimal() and len(signature) == 64
