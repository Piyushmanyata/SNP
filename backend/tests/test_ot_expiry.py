import pytest
from fastapi import HTTPException

import routes_clinical
from conftest import freeze_clock
from seed import CLINICAL, TODAY, TOMORROW, fulfil, run_camp, seed_camp, seen_patient


@pytest.mark.parametrize("already_booked", [False, True])
def test_ot_day_expires_at_ist_midnight_even_when_loaded_before_midnight(monkeypatch, already_booked):
    async def body(database):
        camp_id, _ = await seed_camp(database, days=())
        seen = await seen_patient(database, camp_id)
        day_id = (await database.ot_schedule_days.insert_one({
            "camp_id": camp_id, "day_date": TODAY,
            "venue": "Vimla Ramkrishna Bajaj Eye Hospital, Deoghar", "seat_limit": 2, "seats_taken": 0,
        })).inserted_id

        def book(operation_id):
            return routes_clinical.record_fulfilment(fulfil(
                seen["trans_id"], seen["rev_id"], item_type="ot", status="deferred",
                ot_schedule_day_id=str(day_id), operation_id=operation_id,
            ), actor=CLINICAL, background_tasks=None)

        listed = await routes_clinical.list_ot_days(actor=CLINICAL)
        assert [day["id"] for day in listed["ot_days"]] == [str(day_id)]
        if already_booked:
            await book("op-ot-1")

        freeze_clock(monkeypatch, f"{TOMORROW}T00:00")
        with pytest.raises(HTTPException) as error:
            await book("op-ot-2")
        assert error.value.status_code == 400
        assert (await routes_clinical.list_ot_days(actor=CLINICAL))["ot_days"] == []
        stored = await database.ot_schedule_days.find_one({"_id": day_id})
        assert stored["seats_taken"] == int(already_booked)

    run_camp(monkeypatch, body, ist=f"{TODAY}T23:59")
