from datetime import timedelta

from bson import ObjectId

from conftest import CommandLog
from routes_reports import camp_day_board
from seed import ADMIN, NOW, TODAY, day, patient_doc, run_camp, seed_camp, user_doc


def _walk_strings(obj):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append(str(k))
            out.extend(_walk_strings(v))
    elif isinstance(obj, list):
        for i in obj:
            out.extend(_walk_strings(i))
    elif obj is not None:
        out.append(str(obj))
    return out


class TestCampDayBoard:
    def test_next_schedule_is_earliest_valid_day_beyond_two_hundred_records(self, monkeypatch):
        async def body(database):
            camp_id, _ = await seed_camp(database)
            for collection in (database.ot_schedule_days, database.specs_collection_days):
                await collection.insert_many([
                    {"camp_id": camp_id, "day_date": day(i + 2), "start_time": "10:00", "end_time": "17:00"}
                    for i in range(200)
                ] + [
                    {"camp_id": camp_id, "day_date": day(1), "start_time": "10:00", "end_time": "17:00"},
                    {"camp_id": camp_id, "day_date": day(-1)},
                    {"camp_id": ObjectId(), "day_date": TODAY, "start_time": "10:00", "end_time": "17:00"},
                ])
            await database.specs_collection_days.insert_one({"camp_id": camp_id, "day_date": TODAY, "start_time": "09:00"})
            result = await camp_day_board(actor=ADMIN)
            assert result["next_ot"]["day_date"] == day(1)
            assert result["next_specs"]["day_date"] == day(1)

        run_camp(monkeypatch, body)

    def test_counts_do_not_truncate_after_twenty_thousand_arrivals(self, monkeypatch):
        async def body(database):
            camp_id, _ = await seed_camp(database)
            await database.patients.insert_many([patient_doc(camp_id=camp_id, arrived_at=NOW) for _ in range(20001)])
            result = await camp_day_board(actor=ADMIN)
            assert result["stages"]["arrived"] == 20001
            assert result["stages"]["awaiting_print"] == 20001

        run_camp(monkeypatch, body)

    def test_scoped_kpis_quiet_activity_and_no_patient_names(self, monkeypatch):
        async def body(database):
            camp_id, _ = await seed_camp(database)
            other = ObjectId()
            await database.camps.insert_one({"_id": other, "name": "Other Camp", "is_active": False})
            desk_busy, desk_quiet = ObjectId(), ObjectId()
            await database.users.insert_many([
                user_doc("Vol 1", _id=desk_busy), user_doc("Vol 2", _id=desk_quiet), user_doc("Off Duty"),
            ])
            p_seen, p_tx = ObjectId(), ObjectId()
            await database.patients.insert_many([
                patient_doc(
                    _id=p_seen, camp_id=camp_id, full_name="Sunita Devi", arrived_by=str(desk_busy),
                    arrived_at=NOW - timedelta(minutes=10), printed_at=NOW - timedelta(minutes=8),
                    seen_at=NOW - timedelta(minutes=5),
                ),
                patient_doc(
                    _id=p_tx, camp_id=camp_id, full_name="Ramesh Kumar", arrived_by=str(desk_quiet),
                    arrived_at=NOW - timedelta(minutes=40), printed_at=NOW - timedelta(minutes=35),
                    seen_at=NOW - timedelta(minutes=30),
                ),
                patient_doc(
                    camp_id=other, full_name="Other Patient", arrived_by=str(desk_busy),
                    arrived_at=NOW - timedelta(minutes=2), seen_at=NOW - timedelta(minutes=1),
                ),
            ])
            tx = ObjectId()
            await database.transcriptions.insert_one({"_id": tx, "patient_id": p_tx, "camp_id": camp_id})
            await database.fulfilments.insert_many([
                {"transcription_id": tx, "item_type": "medicine", "status": "fulfilled", "created_at": NOW - timedelta(minutes=2)},
                {"transcription_id": tx, "item_type": "ot", "status": "deferred", "created_at": NOW - timedelta(minutes=3)},
            ])
            await database.ot_schedule_days.insert_one({
                "camp_id": camp_id, "day_date": day(1), "venue": "OT Hall", "seat_limit": 10, "seats_taken": 3,
            })
            await database.specs_collection_days.insert_one({
                "camp_id": camp_id, "day_date": day(4), "venue": "Optical", "start_time": "10:00", "end_time": "17:00",
            })
            ledger = [
                {"status": "failed", "patient_id": p_seen},
                {"status": "failed", "patient_id": ObjectId()},
                {"status": "abandoned", "patient_id": p_seen},
                {"status": "rejected", "patient_id": p_tx},
                {"status": "sent", "delivery": "failed", "dlt_failure": True, "patient_id": p_tx},
                {"status": "sent", "delivery": "delivered", "patient_id": p_tx},
                {"status": "uncertain", "patient_id": p_tx},
                {"status": "paused", "patient_id": p_tx},
            ]
            await database.reminder_ledger.insert_many([
                {**row, "event_key": str(i), "created_at": NOW - timedelta(minutes=1)} for i, row in enumerate(ledger)
            ])
            await database.sms_controls.insert_many([
                {"_id": "registration", "paused": True}, {"_id": "camp", "paused": False},
            ])
            out = await camp_day_board(actor=ADMIN)
            assert out["state"] == "current"
            assert out["as_of"]
            assert out["camp"]["name"] == "Sikar Camp"
            assert out["day"]["day_date"] == TODAY
            assert out["stages"]["arrived"] == 2
            assert out["stages"]["seen"] == 2
            assert out["stages"]["transcription_backlog"] == 1
            by_name = {d["name"]: d for d in out["activity"]}
            assert set(by_name) == {"Vol 1", "Vol 2"}
            assert by_name["Vol 1"]["quiet"] is False
            assert by_name["Vol 2"]["quiet"] is True
            assert out["quiet_count"] == 1
            assert out["fulfilment"]["medicine"]["fulfilled"] == 1
            assert out["fulfilment"]["ot"]["deferred"] == 1
            assert out["next_ot"]["seats_left"] == 7
            assert out["next_ot"]["venue"] == "OT Hall"
            assert out["next_specs"]["start_time"] == "10:00"
            assert "seats_left" not in out["next_specs"]
            assert out["sms_failures"] == 4
            assert out["sms_not_sent"] == 1
            assert out["sms_paused"] == ["registration"]
            blob = " ".join(_walk_strings(out))
            assert "Sunita" not in blob
            assert "Ramesh" not in blob
            assert "Other Patient" not in blob

        run_camp(monkeypatch, body)

    def test_query_count_stays_flat_as_volunteers_grow(self, monkeypatch):
        log = CommandLog()

        async def body(database):
            camp_id, _ = await seed_camp(database)

            async def board_commands(volunteers):
                await database.users.delete_many({})
                await database.patients.delete_many({"camp_id": camp_id})
                ids = [ObjectId() for _ in range(volunteers)]
                await database.users.insert_many([user_doc(f"V{i}", _id=uid) for i, uid in enumerate(ids)])
                await database.patients.insert_many([
                    patient_doc(camp_id=camp_id, arrived_by=str(uid), arrived_at=NOW - timedelta(minutes=2)) for uid in ids
                ])
                log.commands.clear()
                await camp_day_board(actor=ADMIN)
                return len(log.commands)

            small = await board_commands(5)
            large = await board_commands(25)
            assert large <= small + 2
            assert large < 25

        run_camp(monkeypatch, body, listener=log)
