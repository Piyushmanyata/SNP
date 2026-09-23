import asyncio
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from bson import ObjectId
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import routes_camps
from helpers import now_ist
from models import CampDayBody, DoorManualBody, PrintWindowBody


@pytest.mark.parametrize("operation", ["door", "day", "print"])
def test_deleted_document_after_camp_write_returns_not_found(monkeypatch, operation):
    day_date = (now_ist().date() + timedelta(days=1)).isoformat()
    camp = {"_id": ObjectId(), "name": "Camp", "venue": "Hall", "camp_date": day_date}
    day = {"_id": ObjectId(), "camp_id": camp["_id"], "day_date": day_date, "seat_limit": 10}
    db = SimpleNamespace(
        camps=SimpleNamespace(
            find_one=AsyncMock(side_effect=[camp, None if operation == "door" else camp]),
            update_one=AsyncMock(),
        ),
        camp_days=SimpleNamespace(
            find_one=AsyncMock(side_effect=[day, None]),
            update_one=AsyncMock(),
            find=Mock(return_value=SimpleNamespace(to_list=AsyncMock(return_value=[]))),
        ),
    )
    monkeypatch.setattr(routes_camps, "get_db", lambda: db)

    async def run():
        with pytest.raises(HTTPException) as error:
            if operation == "door":
                await routes_camps.set_door_manual(DoorManualBody(enabled=True), actor={})
            elif operation == "day":
                await routes_camps.upsert_camp_day(
                    CampDayBody(camp_id=str(camp["_id"]), day_date=day["day_date"], seat_limit=10), actor={},
                )
            else:
                await routes_camps.toggle_print_window(
                    str(day["_id"]), PrintWindowBody(mode="automatic"), actor={},
                )
        assert error.value.status_code == 404

    asyncio.run(run())
