import asyncio
from datetime import timedelta

import pytest
from bson import ObjectId
from fastapi import HTTPException

from test_camp_lifecycle import RX, _fulfil, _mock, _seen_patient_with_transcription
import routes_clinical
from helpers import now_ist



@pytest.mark.parametrize("already_booked", [False, True])
def test_ot_day_expires_at_ist_midnight_even_when_loaded_before_midnight(monkeypatch, already_booked):
    async def run():
        database = _mock(monkeypatch)
        camp_id, _, trans_id = await _seen_patient_with_transcription(database, RX)
        await database.camps.insert_one({"_id": camp_id, "is_active": True})
        before_midnight = now_ist().replace(hour=23, minute=59, second=0, microsecond=0)
        day_id = ObjectId()
        await database.ot_schedule_days.insert_one({
            "_id": day_id, "camp_id": camp_id, "day_date": before_midnight.date().isoformat(),
            "venue": routes_clinical.HOSPITAL_VENUE, "seat_limit": 2, "seats_taken": 0,
        })
        actor = {"_id": ObjectId(), "role": "clinical_desk_operator"}
        body = _fulfil(trans_id, database.last_rev_id, item_type="ot", status="deferred",
                       ot_schedule_day_id=str(day_id), operation_id="op-ot-1")
        monkeypatch.setattr(routes_clinical, "now_ist", lambda: before_midnight)
        listed = await routes_clinical.list_ot_days(actor=actor)
        assert [day["id"] for day in listed["ot_days"]] == [str(day_id)]
        if already_booked:
            await routes_clinical.record_fulfilment(body, actor=actor)

        monkeypatch.setattr(routes_clinical, "now_ist", lambda: before_midnight + timedelta(minutes=1))
        with pytest.raises(HTTPException) as error:
            await routes_clinical.record_fulfilment(_fulfil(
                trans_id, database.last_rev_id, item_type="ot", status="deferred",
                ot_schedule_day_id=str(day_id), operation_id="op-ot-2",
            ), actor=actor)
        assert error.value.status_code == 400
        assert (await routes_clinical.list_ot_days(actor=actor))["ot_days"] == []
        stored = await database.ot_schedule_days.find_one({"_id": day_id})
        assert stored["seats_taken"] == int(already_booked)
    asyncio.run(run())
