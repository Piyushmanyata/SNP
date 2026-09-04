from helpers import iso, STATUS_LABELS, GENDER_LABELS


def ser_patient(p: dict) -> dict:
    return {
        "id": str(p["_id"]),
        "person_id": str(p["person_id"]) if p.get("person_id") else None,
        "camp_id": str(p["camp_id"]),
        "camp_day_id": str(p["camp_day_id"]),
        "reg_no": p["reg_no"],
        "full_name": p["full_name"],
        "latin_display_name": p.get("latin_display_name"),
        "gender": p.get("gender"),
        "gender_label": GENDER_LABELS.get(p.get("gender"), p.get("gender") or "-"),
        "age": p.get("age"),
        "address": p.get("address"),
        "phone": p.get("phone"),
        "aadhaar_last4": p.get("aadhaar_last4"),
        "dob": p.get("dob"),
        "aadhaar_scanned": p.get("aadhaar_scanned", False),
        "manual_entry": bool(p.get("manual_entry") or p.get("manual_exception")),
        "queue_status": p.get("queue_status", "registered"),
        "status_label": STATUS_LABELS.get(p.get("queue_status", "registered"), "Registered"),
        "patient_qr": p.get("patient_qr"),
        "arrived_at": iso(p.get("arrived_at")),
        "camp_day_changed_from": p.get("camp_day_changed_from"),
        "printed_at": iso(p.get("printed_at")),
        "seen_at": iso(p.get("seen_at")),
        "seen_by": str(p["seen_by"]) if p.get("seen_by") else None,
        "created_by": str(p["created_by"]) if p.get("created_by") else None,
        "created_roster_id": p.get("created_roster_id"),
        "arrived_roster_id": p.get("arrived_roster_id"),
        "seen_roster_id": p.get("seen_roster_id"),
        "is_self_registered": p.get("is_self_registered", False),
        "manual_exception": p.get("manual_exception"),
        "created_at": iso(p.get("created_at")),
    }


def ser_person(p: dict) -> dict:
    return {
        "id": str(p["_id"]),
        "person_no": p.get("person_no"),
        "name_verbatim": p.get("name_verbatim"),
        "latin_display_name": p.get("latin_display_name"),
        "dob": p.get("dob"),
        "gender": p.get("gender"),
        "aadhaar_last4": p.get("last4"),
        "locked": p.get("locked", False),
    }
