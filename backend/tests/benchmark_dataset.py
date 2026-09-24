import argparse
import asyncio
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from bson import ObjectId
from pymongo import AsyncMongoClient


MARKER = "snp-benchmark-10000-v1"
COLLECTIONS = (
    "users", "persons", "patients", "camp_days", "transcriptions", "fulfilments",
    "deferred_slips", "ot_schedule_days", "specs_collection_days", "reminder_ledger",
)


def identifier(label: str) -> ObjectId:
    return ObjectId(hashlib.sha256(f"{MARKER}:{label}".encode()).digest()[:12])


async def restore(database) -> dict:
    camp = await database.camps.find_one({"_id": identifier("camp"), "benchmark_marker": MARKER})
    if not camp:
        return {"restored": False, "reason": "dataset_not_present"}
    active = await database.camps.find_one({"is_active": True})
    if active and active["_id"] != camp["_id"]:
        return {"restored": False, "reason": "another_camp_already_active"}
    await database.camps.update_one({"_id": camp["_id"]}, {"$set": {"is_active": False}})
    previous = camp.get("benchmark_prior_active_id")
    if previous:
        await database.camps.update_one({"_id": previous}, {"$set": {"is_active": True}})
    return {"restored": True, "active_camp_id": str(previous) if previous else None}


async def seed(database) -> dict:
    now = datetime.now(timezone.utc)
    local = now.astimezone(ZoneInfo("Asia/Kolkata"))
    today = local.date().isoformat()
    tomorrow = (local.date() + timedelta(days=1)).isoformat()
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    camp_id, day_id = identifier("camp"), identifier("day")
    previous = await database.camps.find_one({"is_active": True})
    if previous and previous["_id"] == camp_id:
        await restore(database)
        previous = await database.camps.find_one({"is_active": True})
    for name in COLLECTIONS:
        await database[name].delete_many({"benchmark_marker": MARKER})
    await database.camps.replace_one({"_id": camp_id}, {
        "_id": camp_id, "benchmark_marker": MARKER, "name": "SNP benchmark — 10000 synthetic registrations",
        "venue": "Synthetic benchmark venue", "camp_date": today, "is_active": False,
        "created_at": now, "benchmark_prior_active_id": previous["_id"] if previous else None,
    }, upsert=True)
    rows = {name: [] for name in COLLECTIONS}
    for index in range(20):
        rows["users"].append({
            "_id": identifier(f"volunteer:{index}"), "name": f"Benchmark volunteer {index:02d}",
            "name_normalized": f"benchmark volunteer {MARKER} {index:02d}",
            "role": "volunteer", "disabled_at": None, "created_at": now,
        })
    rows["camp_days"].append({
        "_id": day_id, "camp_id": camp_id, "day_date": today, "seat_limit": 12000,
        "seats_taken": 10000, "printing_open": True, "created_at": now,
    })
    ot_id, specs_id = identifier("ot-day"), identifier("specs-day")
    rows["ot_schedule_days"].append({
        "_id": ot_id, "camp_id": camp_id, "day_date": tomorrow,
        "venue": "Synthetic benchmark hospital", "seat_limit": 1000, "seats_taken": 500, "created_at": now,
    })
    rows["specs_collection_days"].append({
        "_id": specs_id, "camp_id": camp_id, "day_date": tomorrow,
        "venue": "Synthetic benchmark collection", "start_time": "09:00", "end_time": "17:00", "created_at": now,
    })
    for index in range(10000):
        person_id, patient_id = identifier(f"person:{index}"), identifier(f"patient:{index}")
        volunteer = str(identifier(f"volunteer:{index % 20}"))
        arrival = max(midnight, now - timedelta(minutes=30 if index % 20 < 5 else 5, seconds=index % 300))
        rows["persons"].append({
            "_id": person_id, "person_no": 700000000 + index, "aadhaar_key": f"{MARKER}:{index}",
            "full_name": f"Synthetic patient {index:05d}", "dob": "1960-01-01", "gender": "F" if index % 2 else "M",
            "aadhaar_last4": f"{index:04d}", "created_at": now,
        })
        rows["patients"].append({
            "_id": patient_id, "person_id": person_id, "camp_id": camp_id, "camp_day_id": day_id,
            "reg_no": 700000000 + index, "patient_qr": str(uuid5(NAMESPACE_URL, f"{MARKER}:{index}")),
            "registration_request_id": f"{MARKER}:{index}", "full_name": f"Synthetic patient {index:05d}",
            "full_name_normalized": f"synthetic patient {index:05d}", "age": 66,
            "phone": "9999999999", "phone_normalized": "9999999999", "address": "Synthetic benchmark address",
            "gender": "F" if index % 2 else "M", "aadhaar_last4": f"{index:04d}", "dob": "1960-01-01",
            "aadhaar_scanned": True, "manual_entry": False, "created_by": volunteer, "created_at": midnight,
            "queue_status": "seen" if index < 6000 else "registered",
            "arrived_at": arrival if index < 8000 else None, "arrived_by": volunteer if index < 8000 else None,
            "printed_at": arrival if index < 7000 else None, "seen_at": arrival if index < 6000 else None,
        })
        if index < 100:
            rows["reminder_ledger"].append({
                "_id": identifier(f"sms:{index}"), "patient_id": patient_id, "message_type": "benchmark",
                "event_date": today, "status": "failed", "created_at": now,
            })
        if index >= 5000:
            continue
        transcription_id = identifier(f"transcription:{index}")
        rows["transcriptions"].append({
            "_id": transcription_id, "patient_id": patient_id, "person_id": person_id, "camp_id": camp_id,
            "diagnosis_options": ["Cataract"], "bp": "120/80", "blood_sugar": "110", "locked": True,
            "specs_measurements": {"r_sph": "-1.00", "l_sph": "-1.25"}, "ot_eye": "R",
            "created_by": volunteer, "created_at": arrival,
        })
        items = [("medicine", "not_available" if index % 5 == 0 else "fulfilled")]
        if index % 4 == 0:
            items.append(("specs_fixed", "fulfilled"))
        elif index % 4 == 1:
            items.append(("specs_made", "deferred"))
        if index % 10 == 2:
            items.append(("ot", "deferred"))
        for item, status in items:
            collection_id = ot_id if item == "ot" else specs_id
            fields = {
                "transcription_id": transcription_id, "item_type": item, "status": status,
                "current": True, "created_by": volunteer, "created_at": arrival,
            }
            if status == "deferred":
                fields.update({
                    "collection_date": tomorrow, "collection_venue": "Synthetic benchmark venue",
                    "ot_schedule_day_id" if item == "ot" else "specs_collection_day_id": collection_id,
                })
                rows["deferred_slips"].append({
                    "_id": identifier(f"slip:{index}:{item}"), **fields, "patient_id": patient_id,
                    "active": True, "cancelled": False, "version": 1,
                    "collection_start_time": "09:00" if item == "specs_made" else None,
                    "collection_end_time": "17:00" if item == "specs_made" else None,
                })
            rows["fulfilments"].append({"_id": identifier(f"fulfilment:{index}:{item}"), **fields})
    for name, documents in rows.items():
        for document in documents:
            document["benchmark_marker"] = MARKER
        if documents:
            await database[name].insert_many(documents)
    if previous:
        await database.camps.update_one({"_id": previous["_id"]}, {"$set": {"is_active": False}})
    await database.camps.update_one({"_id": camp_id}, {"$set": {"is_active": True}})
    counts = {name: await database[name].count_documents({"benchmark_marker": MARKER}) for name in COLLECTIONS}
    return {"benchmark_marker": MARKER, "active_camp_id": str(camp_id), "counts": counts,
            "stages": {"arrived": 8000, "awaiting_print": 1000, "awaiting_seen": 1000,
                       "seen": 6000, "transcription_backlog": 1000}}


async def main(action: str) -> None:
    if os.environ.get("DB_NAME") != "snp_audit":
        raise RuntimeError("This helper may only modify the isolated snp_audit database")
    client = AsyncMongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=5000)
    try:
        database = client["snp_audit"]
        result = await (seed(database) if action == "seed" else restore(database))
        print(json.dumps(result, indent=2))
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed or restore the isolated 10000-registration audit benchmark")
    parser.add_argument("action", choices=("seed", "restore"))
    asyncio.run(main(parser.parse_args().action))
