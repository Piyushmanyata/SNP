"""Hot queries keep an index. A winning COLLSCAN fails the run."""

from datetime import timedelta

from helpers import ist_day_bounds, now_utc, today_ist_str
from conftest import run_db
from benchmark_dataset import seed


def _stages(node):
    found = []
    if isinstance(node, dict):
        stage = node.get("stage")
        if stage:
            found.append(stage)
        for value in node.values():
            found.extend(_stages(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_stages(item))
    return found


def _plan(explained):
    if "queryPlanner" in explained:
        return explained["queryPlanner"]["winningPlan"]
    for stage in explained.get("stages") or []:
        cursor = stage.get("$cursor") or {}
        if "queryPlanner" in cursor:
            return cursor["queryPlanner"]["winningPlan"]
    raise AssertionError(list(explained)[:6])


async def _winning(database, command):
    explained = await database.command({"explain": command, "verbosity": "queryPlanner"})
    return _plan(explained)


def test_hot_queries_are_not_collection_scans(monkeypatch):
    async def run(db):
        seeded = await seed(db, patients=2000)
        camp_id = seeded["active_camp_id"]
        from bson import ObjectId
        camp = ObjectId(camp_id)
        patient = await db.patients.find_one({"camp_id": camp, "arrived_at": {"$ne": None}})
        person = await db.persons.find_one({"_id": patient["person_id"]})
        day_id = patient["camp_day_id"]
        start, end = ist_day_bounds(today_ist_str())
        slip = await db.deferred_slips.find_one({"item_type": "ot", "active": True})
        fulfilment = await db.fulfilments.find_one({"operation_id": {"$type": "string"}})
        revision_id = patient["committed_revision_id"]
        plans = {
            "desk person": {"find": "persons", "filter": {"aadhaar_key": person["aadhaar_key"]}, "limit": 1},
            "desk patient": {"find": "patients", "filter": {"camp_id": camp, "person_id": person["_id"]}, "limit": 1},
            "reg no": {"find": "patients", "filter": {"camp_id": camp, "reg_no": patient["reg_no"]}, "limit": 1},
            "patient qr": {"find": "patients", "filter": {"camp_id": camp, "patient_qr": patient["patient_qr"]}, "limit": 1},
            "name prefix": {"find": "patients", "filter": {
                "camp_id": camp, "full_name_normalized": {"$regex": "^synthetic"},
                "arrived_at": {"$ne": None}, "printed_at": {"$ne": None},
            }, "sort": {"reg_no": 1}, "limit": 20},
            "duplicate name": {"find": "patients", "filter": {
                "camp_id": camp, "full_name_normalized": patient["full_name_normalized"],
                "age": patient["age"], "phone_normalized": patient["phone_normalized"],
            }, "limit": 20},
            "duplicate last4": {"find": "patients", "filter": {
                "camp_id": camp, "aadhaar_last4": patient["aadhaar_last4"],
            }, "limit": 50},
            "board arrivals": {"find": "patients", "filter": {
                "camp_id": camp, "arrived_at": {"$gte": start, "$lt": end},
            }, "limit": 1},
            "kpi camp": {"find": "patients", "filter": {"camp_id": camp}, "limit": 1},
            "kpi seen": {"find": "patients", "filter": {"camp_id": camp, "queue_status": "seen"}, "limit": 1},
            "reminder targets": {"find": "patients", "filter": {"camp_day_id": day_id}, "sort": {"_id": 1}, "limit": 200},
            "canary": {"find": "reminder_ledger", "filter": {
                "message_type": "camp", "event_date": today_ist_str(),
                "status": {"$in": ["sent", "uncertain", "rejected"]},
            }, "sort": {"created_at": 1}, "limit": 1},
            "slips by day": {"find": "deferred_slips", "filter": {
                "item_type": "ot", "active": True, "collection_date": slip["collection_date"],
            }, "sort": {"_id": 1}, "limit": 200},
            "fulfilment by operation": {"find": "fulfilments", "filter": {"$and": [
                {"operation_id": fulfilment["operation_id"]},
                {"operation_id": {"$type": "string"}},
            ]}, "limit": 1},
            "revision by id": {"find": "prescription_revisions", "filter": {"_id": revision_id}, "limit": 1},
        }
        for name, command in plans.items():
            stages = _stages(await _winning(db, command))
            assert "COLLSCAN" not in stages, (name, stages)
        quiet = now_utc() - timedelta(minutes=15)
        group_plans = {
            "leaderboard": {"aggregate": "patients", "pipeline": [
                {"$match": {"camp_id": camp}},
                {"$facet": {
                    "registrations": [{"$group": {"_id": "$created_by", "count": {"$sum": 1}}}],
                    "completed": [
                        {"$match": {"committed_revision_id": {"$ne": None}, "is_self_registered": {"$ne": True}}},
                        {"$group": {"_id": "$created_by", "count": {"$sum": 1}}},
                    ],
                }},
            ], "cursor": {}},
            "board fulfilment": {"aggregate": "fulfilments", "pipeline": [
                {"$match": {"camp_id": camp, "patient_seen_at": {"$gte": start, "$lt": end}}},
                {"$group": {"_id": {"item_type": "$item_type", "status": "$status"}, "count": {"$sum": 1}}},
            ], "cursor": {}},
            "board activity": {"aggregate": "patients", "pipeline": [
                {"$match": {"camp_id": camp, "arrived_at": {"$gte": start, "$lt": end}}},
                {"$group": {"_id": "$arrived_by", "last": {"$max": "$arrived_at"},
                            "last_15m": {"$sum": {"$cond": [{"$gte": ["$arrived_at", quiet]}, 1, 0]}}}},
            ], "cursor": {}},
            "sms groups": {"aggregate": "reminder_ledger", "pipeline": [
                {"$match": {"camp_id": camp, "created_at": {"$gte": start, "$lt": end}}},
                {"$group": {"_id": {"camp_id": "$camp_id", "message_type": "$message_type", "status": "$status"}, "n": {"$sum": 1}}},
            ], "cursor": {}},
        }
        for name, command in group_plans.items():
            stages = _stages(await _winning(db, command))
            assert "COLLSCAN" not in stages, name

    run_db(run)
