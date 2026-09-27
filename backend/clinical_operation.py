"""Every clinical write runs here: hash, replay or refuse, claim the patient, apply, record, commit, dispatch SMS (ADR 0065)."""

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

import sms
from clinical_state import conflict, payload_hash
from db import in_transaction
from helpers import api_error, now_utc

Result = Dict[str, Any]
Apply = Callable[[dict, Any], Awaitable[Tuple[Result, List[ObjectId]]]]
Superseded = Callable[[dict, Result], Optional[str]]


@dataclass
class Operation:
    kind: str
    operation_id: Optional[str]
    patient_id: ObjectId
    payload: Dict[str, Any]
    apply: Apply
    is_superseded: Optional[Superseded] = None


async def _recorded(db: AsyncDatabase, operation: Operation, digest: str, session=None) -> Optional[dict]:
    existing = await db.clinical_operations.find_one({"operation_id": operation.operation_id}, session=session)
    if existing is None:
        return None
    if existing.get("kind") != operation.kind or existing.get("payload_hash") != digest:
        raise conflict("operation_conflict", "This operation id was used for a different request.")
    return existing


async def is_replay(db: AsyncDatabase, operation_id: Optional[str]) -> bool:
    return bool(operation_id) and await db.clinical_operations.find_one({"operation_id": operation_id}, {"_id": 1}) is not None


async def run(db: AsyncDatabase, operation: Operation, background_tasks: Any = None) -> Result:
    if not operation.operation_id:
        raise api_error(400, "OPERATION_ID_IS_REQUIRED", 'operation_id is required')
    digest = payload_hash(operation.kind, operation.payload)
    done = await _recorded(db, operation, digest)
    if done:
        if operation.is_superseded:
            patient = await db.patients.find_one({"_id": operation.patient_id}) or {}
            message = operation.is_superseded(patient, done["result"])
            if message:
                raise conflict("OPERATION_SUPERSEDED", message)
        return done["result"]

    async def write(session):
        patient = await db.patients.find_one_and_update(
            {"_id": operation.patient_id}, {"$inc": {"clinical_seq": 1}}, return_document=True, session=session,
        )
        if not patient:
            raise api_error(404, "REGISTRATION_NOT_FOUND", 'Registration not found')
        replay = await _recorded(db, operation, digest, session)
        if replay:
            return replay["result"], []
        result, intent_ids = await operation.apply(patient, session)
        await db.clinical_operations.insert_one({
            "operation_id": operation.operation_id, "kind": operation.kind, "payload_hash": digest,
            "patient_id": patient["_id"], "result": result, "created_at": now_utc(),
        }, session=session)
        return result, intent_ids

    try:
        result, intent_ids = await in_transaction(write)
    except DuplicateKeyError:
        done = await _recorded(db, operation, digest)
        if not done:
            raise
        return done["result"]
    await sms.dispatch(background_tasks, db, intent_ids, now_utc())
    return result
