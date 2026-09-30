"""A Fulfilment line: its valid statuses, what an issue makes of it, what a correction does to it. An outcome with given None is open; any other is settled (ADR 0097, 0098)."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from helpers import api_error

STATUSES: Dict[str, Tuple[str, ...]] = {
    "medicine": ("fulfilled", "not_available", "partially_fulfilled"),
    "specs_fixed": ("fulfilled",),
    "specs_made": ("deferred", "cancelled"),
    "ot": ("deferred", "declined"),
}


def _invalid() -> HTTPException:
    return api_error(400, "INVALID_FULFILMENT_ITEM_STATUS", "Invalid fulfilment item/status")


def _settled(outcome: dict) -> bool:
    return outcome.get("given") is not None


def _derive_status(outcomes: List[dict]) -> str:
    given = sum(1 for o in outcomes if o["given"])
    if given == 0:
        return "not_available"
    if given == len(outcomes):
        return "fulfilled"
    return "partially_fulfilled"


def _match_outcomes(revision: dict, outcomes) -> List[dict]:
    prescribed = {m["medicine_id"]: m["name"] for m in (revision.get("prescribed_medicines") or [])}
    supplied = {o.medicine_id: bool(o.given) for o in (outcomes or [])}
    if not prescribed or len(supplied) != len(outcomes or []) or set(supplied) != set(prescribed):
        raise api_error(400, "MEDICINE_OUTCOMES_MISMATCH", "Record given or not available for every prescribed medicine.")
    return [{"medicine_id": mid, "name": name, "given": supplied[mid]} for mid, name in prescribed.items()]


def _keep_removed(prior: List[dict], outcomes: List[dict], corrected: bool) -> List[dict]:
    prior_by_id = {o["medicine_id"]: o for o in prior}
    resolved = []
    for o in outcomes:
        p = prior_by_id.get(o["medicine_id"])
        resolved.append({**o, "given": p["given"]} if corrected and p and _settled(p) else o)
    ids = {o["medicine_id"] for o in resolved}
    return resolved + [o for o in prior if o.get("prescribed") is False and o["medicine_id"] not in ids]


def _carry_outcomes(outcomes: List[dict], prescribed: List[dict]) -> Tuple[List[dict], bool]:
    by_id = {o["medicine_id"]: o for o in outcomes}
    by_name = {o["name"]: o for o in outcomes}
    carried, matched = [], []
    for m in prescribed:
        earlier = by_id.get(m["medicine_id"]) or by_name.get(m["name"])
        if earlier:
            matched.append(earlier)
        carried.append({"medicine_id": m["medicine_id"], "name": m["name"], "given": earlier["given"] if earlier else None})
    unmatched = [o for o in outcomes if not any(o is m for m in matched)]
    carried += [{**o, "prescribed": False} for o in unmatched if o["given"]]
    return carried, len(matched) < len(prescribed) or any(o.get("prescribed") is not False for o in unmatched)


def _fixed_power_corrected(line: dict, before: dict, after: dict) -> bool:
    was = (before.get("fixed_power_r"), before.get("fixed_power_l"))
    now = (after.get("fixed_power_r"), after.get("fixed_power_l"))
    return was != now and now != (line.get("issued_power_r"), line.get("issued_power_l"))


def require_line(item_type: str) -> None:
    if item_type not in STATUSES:
        raise _invalid()


def check_issue(revision: dict, item_type: str, status: str, outcomes) -> Tuple[str, Optional[List[dict]]]:
    require_line(item_type)
    if item_type == "medicine":
        matched = _match_outcomes(revision, outcomes)
        return _derive_status(matched), matched
    if status not in STATUSES[item_type]:
        raise _invalid()
    return status, None


def issue(
    item_type: str, status: str, outcomes: Optional[List[dict]], powers: Optional[Tuple[float, float]], prior: Optional[dict],
) -> Dict[str, Any]:
    mark = (prior or {}).get("corrected_after_issue")
    fields: Dict[str, Any] = {
        "status": status,
        "medicine_outcomes": outcomes,
        "issued_power_r": powers[0] if powers else None,
        "issued_power_l": powers[1] if powers else None,
    }
    if prior and item_type == "medicine":
        fields["medicine_outcomes"] = _keep_removed(prior.get("medicine_outcomes") or [], outcomes or [], bool(mark))
        fields["status"] = _derive_status(fields["medicine_outcomes"])
    if mark:
        fields["corrected_after_issue"] = mark
        if item_type == "specs_fixed" and prior and prior.get("issued_power_r") is not None:
            fields["issued_power_r"], fields["issued_power_l"] = prior["issued_power_r"], prior["issued_power_l"]
    return fields


def correct(line: dict, before: dict, after: dict, *, by: str, at: datetime) -> Optional[Dict[str, Any]]:
    mark = {"revision_id": after["_id"], "at": at, "by": by}
    if line["item_type"] == "medicine":
        outcomes, changed = _carry_outcomes(line.get("medicine_outcomes") or [], after.get("prescribed_medicines") or [])
        if not changed:
            return None
        return {"corrected_after_issue": mark, "medicine_outcomes": outcomes, "status": _derive_status(outcomes)}
    if line["item_type"] == "specs_fixed" and _fixed_power_corrected(line, before, after):
        return {"corrected_after_issue": mark}
    return None
