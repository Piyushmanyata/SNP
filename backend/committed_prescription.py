"""Committed prescription: what was prescribed is the patient's committed revision, never the transcription draft (ADR 0100)."""

from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase


async def of_patient(db: AsyncDatabase, patient: dict, session: Any = None) -> Optional[dict]:
    revision_id = patient.get("committed_revision_id")
    if not revision_id:
        return None
    return await db.prescription_revisions.find_one({"_id": revision_id}, session=session)


async def of_patients(db: AsyncDatabase, patients: List[dict]) -> Dict[ObjectId, dict]:
    ids = list({p["committed_revision_id"] for p in patients if p.get("committed_revision_id")})
    if not ids:
        return {}
    by_id = {r["_id"]: r for r in await db.prescription_revisions.find({"_id": {"$in": ids}}).to_list(len(ids))}
    return {p["_id"]: by_id[p["committed_revision_id"]] for p in patients if p.get("committed_revision_id") in by_id}
