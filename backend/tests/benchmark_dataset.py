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

from helpers import person_key

MARKER = "snp-benchmark-20000-v2"
FULL_PATIENTS = 20000
COLLECTIONS = (
    "users", "persons", "patients", "camp_days", "transcriptions", "fulfilments",
    "deferred_slips", "ot_schedule_days", "specs_collection_days", "reminder_ledger",
    "prescription_revisions", "medicines",
)
MESSAGE_TYPES = ("registration", "camp", "ot", "specs")
CARD = {
    "full_name": "Sunita Devi",
    "gender": "F",
    "dob": "1975-06-14",
    "aadhaar_last4": "1234",
}


def identifier(label: str) -> ObjectId:
    return ObjectId(hashlib.sha256(f"{MARKER}:{label}".encode()).digest()[:12])


def shape(patients: int) -> dict:
    return {
        "patients": patients,
        "persons": patients * 18000 // FULL_PATIENTS,
        "arrived": patients * 70 // 100,
        "printed": patients * 65 // 100,
        "completed": patients * 60 // 100,
        "ot_slips": patients * 2500 // FULL_PATIENTS,
        "specs_slips": patients * 1500 // FULL_PATIENTS,
        "staff": 40,
        "ledger": patients * len(MESSAGE_TYPES),
        "reserved": 160,
    }


async def _insert(database, name: str, documents: list) -> None:
    for start in range(0, len(documents), 1000):
        await database[name].insert_many(documents[start:start + 1000], ordered=False)


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


async def seed(database, *, patients: int = FULL_PATIENTS) -> dict:
    spec = shape(patients)
    now = datetime.now(timezone.utc)
    local = now.astimezone(ZoneInfo("Asia/Kolkata"))
    today = local.date()
    camp_id = identifier("camp")
    previous = await database.camps.find_one({"is_active": True})
    if previous and previous["_id"] == camp_id:
        await restore(database)
        previous = await database.camps.find_one({"is_active": True})
    for name in COLLECTIONS:
        await database[name].delete_many({"benchmark_marker": MARKER})
    await database.camps.replace_one({"_id": camp_id}, {
        "_id": camp_id, "benchmark_marker": MARKER,
        "name": f"SNP benchmark — {patients} synthetic registrations",
        "venue": "Synthetic benchmark venue", "camp_date": today.isoformat(), "is_active": False,
        "created_at": now, "benchmark_prior_active_id": previous["_id"] if previous else None,
    }, upsert=True)

    medicine_id = identifier("medicine")
    rows = {name: [] for name in COLLECTIONS}
    rows["medicines"].append({
        "_id": medicine_id, "name": "Benchmark eye drop", "name_key": MARKER, "active": True,
    })
    roles = ["admin", "clinical_desk_operator"] + ["team_lead"] * 8 + ["volunteer"] * 30
    lead_ids = []
    volunteer_ids = []
    for index, role in enumerate(roles):
        user_id = identifier(f"user:{index}")
        if role == "team_lead":
            lead_ids.append(str(user_id))
        elif role == "volunteer":
            volunteer_ids.append(str(user_id))
        rows["users"].append({
            "_id": user_id, "name": f"Benchmark {role} {index:02d}",
            "name_normalized": f"benchmark {role} {MARKER} {index:02d}",
            "role": role, "disabled_at": None, "must_change_pin": False,
            "session_version": 0, "created_at": now,
            "team_lead_id": lead_ids[index % len(lead_ids)] if role == "volunteer" and lead_ids else None,
        })
    day_ids = []
    for offset in range(3):
        day_id = identifier(f"day:{offset}")
        day_ids.append(day_id)
        on_day = sum(1 for index in range(patients) if index % 3 == offset)
        rows["camp_days"].append({
            "_id": day_id, "camp_id": camp_id,
            "day_date": (today + timedelta(days=offset)).isoformat(),
            "seat_limit": 30000, "seats_taken": on_day, "booked": on_day,
            "printing_open": True, "created_at": now,
        })
    ot_ids = []
    for offset in range(6):
        ot_id = identifier(f"ot:{offset}")
        ot_ids.append(ot_id)
        rows["ot_schedule_days"].append({
            "_id": ot_id, "camp_id": camp_id,
            "day_date": (today + timedelta(days=3 + offset)).isoformat(),
            "venue": "Synthetic benchmark hospital", "seat_limit": 5000, "seats_taken": 0,
            "created_at": now,
        })
    specs_ids = []
    for offset in range(3):
        specs_id = identifier(f"specs:{offset}")
        specs_ids.append(specs_id)
        rows["specs_collection_days"].append({
            "_id": specs_id, "camp_id": camp_id,
            "day_date": (today + timedelta(days=3 + offset)).isoformat(),
            "venue": "Synthetic benchmark collection", "start_time": "10:00", "end_time": "17:00",
            "created_at": now,
        })

    reserved_from = spec["completed"] - spec["reserved"]
    fulfil_pool = []
    scan_qr = None
    for index in range(patients):
        linked = index < spec["persons"]
        person_id = identifier(f"person:{index}") if linked else None
        patient_id = identifier(f"patient:{index}")
        card = index == 0
        full_name = CARD["full_name"] if card else f"Synthetic patient {index:05d}"
        gender = CARD["gender"] if card else ("F" if index % 2 else "M")
        dob = CARD["dob"] if card else "1960-01-01"
        last4 = CARD["aadhaar_last4"] if card else f"{index % 10000:04d}"
        if linked:
            rows["persons"].append({
                "_id": person_id,
                "person_no": 800000000 + index,
                "aadhaar_key": person_key(last4, full_name, dob, gender) if card else f"{MARKER}:{index}",
                "full_name": full_name, "dob": dob, "gender": gender,
                "aadhaar_last4": last4, "created_at": now,
            })
        arrived = index < spec["arrived"]
        printed = index < spec["printed"]
        completed = index < spec["completed"]
        volunteer = volunteer_ids[index % len(volunteer_ids)]
        arrival = now - timedelta(minutes=5, seconds=index % 300)
        qr = str(uuid5(NAMESPACE_URL, f"{MARKER}:{index}"))
        if card:
            scan_qr = qr
        revision_id = identifier(f"revision:{index}") if completed else None
        lines = ["medicine"]
        if completed and index < reserved_from:
            if index < spec["specs_slips"]:
                lines.append("specs_made")
            elif index < spec["specs_slips"] + min(1000, reserved_from):
                lines.append("specs_fixed")
            if index < spec["ot_slips"]:
                lines.append("ot")
        rows["patients"].append({
            "_id": patient_id, "person_id": person_id, "camp_id": camp_id,
            "camp_day_id": day_ids[index % 3], "reg_no": 800000000 + index, "patient_qr": qr,
            "registration_request_id": f"{MARKER}:{index}", "full_name": full_name,
            "full_name_normalized": full_name.lower(), "age": 50 if card else 66,
            "phone": f"98{index % 100000000:08d}", "phone_normalized": f"98{index % 100000000:08d}",
            "address": "Synthetic benchmark address", "gender": gender, "aadhaar_last4": last4,
            "dob": dob, "aadhaar_scanned": card, "manual_entry": not linked,
            "created_by": volunteer, "registrar_team_lead_id": lead_ids[index % len(lead_ids)],
            "created_at": arrival, "queue_status": "seen" if completed else ("arrived" if arrived else "registered"),
            "arrived_at": arrival if arrived else None, "arrived_by": volunteer if arrived else None,
            "printed_at": arrival if printed else None, "seen_at": arrival if completed else None,
            "committed_revision_id": revision_id, "clinical_generation": 1 if completed else 0,
            "is_self_registered": False,
        })
        for message_type in MESSAGE_TYPES:
            rows["reminder_ledger"].append({
                "_id": identifier(f"sms:{index}:{message_type}"), "patient_id": patient_id,
                "camp_id": camp_id, "message_type": message_type, "event_date": today.isoformat(),
                "event_key": message_type, "status": "sent" if index % 5 == 0 else "queued",
                "created_at": now,
            })
        if not completed:
            continue
        rows["prescription_revisions"].append({
            "_id": revision_id, "patient_id": patient_id, "camp_id": camp_id, "kind": "complete",
            "prescribed_lines": lines, "none_prescribed": False,
            "prescribed_medicines": [{"medicine_id": str(medicine_id), "name": "Benchmark eye drop"}],
            "operation_id": f"{MARKER}:revision:{index}", "author_id": volunteer, "created_at": arrival,
        })
        transcription_id = identifier(f"transcription:{index}")
        rows["transcriptions"].append({
            "_id": transcription_id, "patient_id": patient_id, "person_id": person_id, "camp_id": camp_id,
            "diagnosis_options": ["Cataract"], "bp": "120/80", "locked": True,
            "created_by": volunteer, "created_at": arrival,
        })
        if index >= reserved_from:
            fulfil_pool.append({
                "transcription_id": str(transcription_id),
                "revision_id": str(revision_id),
                "generation": 1,
            })
            continue
        for item in lines:
            status = {"medicine": "fulfilled", "specs_fixed": "fulfilled", "specs_made": "deferred", "ot": "deferred"}[item]
            fields = {
                "transcription_id": transcription_id, "item_type": item, "status": status,
                "current": True, "created_by": volunteer, "created_at": arrival,
                "operation_id": f"{MARKER}:fulfil:{index}:{item}",
            }
            if item == "ot":
                day_ref = ot_ids[index % 6]
                fields.update({"collection_date": rows["ot_schedule_days"][index % 6]["day_date"],
                               "collection_venue": "Synthetic benchmark hospital", "ot_schedule_day_id": day_ref})
            elif item == "specs_made":
                day_ref = specs_ids[index % 3]
                fields.update({"collection_date": rows["specs_collection_days"][index % 3]["day_date"],
                               "collection_venue": "Synthetic benchmark collection",
                               "specs_collection_day_id": day_ref})
            if status == "deferred":
                rows["deferred_slips"].append({
                    "_id": identifier(f"slip:{index}:{item}"), **fields, "patient_id": patient_id,
                    "active": True, "cancelled": False, "version": 1,
                    "collection_start_time": "10:00" if item == "specs_made" else None,
                    "collection_end_time": "17:00" if item == "specs_made" else None,
                })
            rows["fulfilments"].append({
                "_id": identifier(f"fulfilment:{index}:{item}"), **fields,
                "camp_id": camp_id, "patient_seen_at": arrival,
            })

    for name, documents in rows.items():
        for document in documents:
            document["benchmark_marker"] = MARKER
        if documents:
            await _insert(database, name, documents)
    if previous:
        await database.camps.update_one({"_id": previous["_id"]}, {"$set": {"is_active": False}})
    await database.camps.update_one({"_id": camp_id}, {"$set": {"is_active": True}})
    counts = {name: await database[name].count_documents({"benchmark_marker": MARKER}) for name in COLLECTIONS}
    return {
        "benchmark_marker": MARKER, "active_camp_id": str(camp_id), "counts": counts, "shape": spec,
        "day_id": str(day_ids[0]), "admin_id": str(identifier("user:0")),
        "clinical_id": str(identifier("user:1")), "lookup_qr": scan_qr,
        "medicine_id": str(medicine_id), "fulfil": fulfil_pool,
    }


async def main(action: str) -> None:
    if os.environ.get("DB_NAME") != "snp_audit":
        raise RuntimeError("This helper may only modify the isolated snp_audit database")
    client = AsyncMongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=5000)
    try:
        database = client["snp_audit"]
        result = await (seed(database) if action == "seed" else restore(database))
        print(json.dumps({key: value for key, value in result.items() if key != "fulfil"}, indent=2, default=str))
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed or restore the isolated 20000-registration benchmark")
    parser.add_argument("action", choices=("seed", "restore"))
    asyncio.run(main(parser.parse_args().action))
