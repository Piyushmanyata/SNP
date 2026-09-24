"""Roster API is unregistered; new records attribute authenticated user ids only."""
import inspect

from bson import ObjectId

from db import init_indexes
from models import ScanBody
from routes_clinical import record_fulfilment
from routes_desk import print_prescription, scan
from routes_reports import leaderboard
from security import hash_pin
from seed import CARD, bearer, fulfil, http, patient_doc, register, run_camp, seed_camp, seen_patient, user_doc

VOLUNTEER = {"_id": ObjectId(), "role": "volunteer", "name": "Desk 1"}
TEAM_LEAD = {"_id": ObjectId(), "role": "team_lead", "name": "Lead"}
ADMIN = {"_id": ObjectId(), "role": "admin", "name": "admin"}
CLINICAL = {"_id": ObjectId(), "role": "clinical_desk_operator", "name": "Rx 1"}
SCANNED = {
    "full_name": "Sunita Devi", "gender": "F", "dob": "1975-06-14", "aadhaar_last4": "1234",
    "aadhaar_scanned": True, "qr_payload": CARD,
}


async def _user(database, actor):
    await database.users.insert_one(user_doc(actor["name"], actor["role"], _id=actor["_id"], pin_hash=hash_pin("2468")))


class TestRosterUnregistered:
    def test_roster_routes_are_not_registered(self, monkeypatch):
        async def body(database, client):
            await _user(database, ADMIN)
            headers = bearer(ADMIN["_id"], ADMIN["name"], ADMIN["role"])
            listed = await client.get("/api/roster", headers=headers)
            created = await client.post(
                "/api/roster",
                json={"camp_id": str(ObjectId()), "names": ["Ramesh"]},
                headers=headers,
            )
            disabled = await client.patch(f"/api/roster/{ObjectId()}/disable", headers=headers)
            enabled = await client.patch(f"/api/roster/{ObjectId()}/enable", headers=headers)
            assert listed.status_code == 404
            assert created.status_code == 404
            assert disabled.status_code == 404
            assert enabled.status_code == 404

        http(monkeypatch, body)

    def test_init_indexes_does_not_create_roster_index(self):
        assert "roster.create_index" not in inspect.getsource(init_indexes)


class TestOnDeskVolunteerHeader:
    def test_volunteer_without_roster_header_is_not_refused(self, monkeypatch):
        async def body(database, client):
            await seed_camp(database)
            await _user(database, VOLUNTEER)
            r = await client.post("/api/desk/scan", json={"payload": CARD}, headers=bearer(VOLUNTEER["_id"], VOLUNTEER["name"], VOLUNTEER["role"]))
            assert r.status_code != 428
            assert r.status_code == 200

        http(monkeypatch, body)

    def test_team_lead_without_header_is_not_refused(self, monkeypatch):
        async def body(database, client):
            await seed_camp(database)
            await _user(database, TEAM_LEAD)
            r = await client.post("/api/desk/scan", json={"payload": CARD}, headers=bearer(TEAM_LEAD["_id"], TEAM_LEAD["name"], TEAM_LEAD["role"]))
            assert r.status_code != 428
            assert r.status_code == 200
            assert r.json()["outcome"] == "no_match"

        http(monkeypatch, body)


class TestAuthenticatedAttribution:
    def test_desk_register_writes_created_by_not_roster_id(self, monkeypatch):
        async def body(database):
            _camp_id, (day_id,) = await seed_camp(database)
            registration = await register(day_id, actor=VOLUNTEER)
            stored = await database.patients.find_one({"_id": ObjectId(registration["id"])})
            assert stored["created_by"] == str(VOLUNTEER["_id"])
            assert "created_roster_id" not in stored
            assert "created_roster_id" not in registration

        run_camp(monkeypatch, body)

    def test_scan_writes_arrived_by_not_roster_id(self, monkeypatch):
        async def body(database):
            _camp_id, (day_id,) = await seed_camp(database)
            await register(day_id, actor=VOLUNTEER, **SCANNED)
            out = await scan(ScanBody(payload=CARD), actor=VOLUNTEER)
            assert out["outcome"] == "arrived"
            stored = await database.patients.find_one({"_id": ObjectId(out["registration"]["id"])})
            assert stored["arrived_by"] == str(VOLUNTEER["_id"])
            assert "arrived_roster_id" not in stored
            assert "arrived_roster_id" not in out["registration"]

        run_camp(monkeypatch, body)

    def test_print_and_seen_attribute_authenticated_user_not_roster(self, monkeypatch):
        async def body(database):
            _camp_id, (day_id,) = await seed_camp(database)
            registration = await register(day_id, actor=VOLUNTEER, **SCANNED)
            await scan(ScanBody(payload=CARD), actor=VOLUNTEER)
            printed = await print_prescription(registration["id"], actor=VOLUNTEER)
            stored = await database.patients.find_one({"_id": ObjectId(registration["id"])})
            assert stored["checked_in_by"] == str(VOLUNTEER["_id"])
            assert stored.get("seen_by") is None
            assert "printed_roster_id" not in stored
            assert "created_roster_id" not in printed["registration"]

        run_camp(monkeypatch, body)

    def test_clinical_fulfilment_attributes_created_by_not_roster_id(self, monkeypatch):
        async def body(database):
            seen = await seen_patient(database)
            result = await record_fulfilment(
                fulfil(seen["trans_id"], seen["rev_id"], item_type="medicine", status="fulfilled"),
                actor=CLINICAL, background_tasks=None,
            )
            stored = await database.fulfilments.find_one({"_id": ObjectId(result["fulfilment"]["id"])})
            assert stored["created_by"] == str(CLINICAL["_id"])
            assert stored.get("roster_id") is None

        run_camp(monkeypatch, body)

    def test_leaderboard_counts_authenticated_ids_and_ignores_legacy_roster_fields(self, monkeypatch):
        async def body(database):
            camp_id, (day_id,) = await seed_camp(database)
            anita_id, ramesh_id, ghost_id = ObjectId(), ObjectId(), ObjectId()
            await database.users.insert_many([user_doc("Anita", _id=anita_id), user_doc("Ramesh", _id=ramesh_id)])
            anita_user = {"_id": anita_id, "role": "volunteer"}
            ramesh_user = {"_id": ramesh_id, "role": "volunteer"}

            await register(day_id, actor=anita_user)
            await register(day_id, actor=ramesh_user, phone="9876500002", **SCANNED)
            await scan(ScanBody(payload=CARD), actor=ramesh_user)
            await database.patients.insert_one(patient_doc(
                camp_id=camp_id, created_roster_id=str(anita_id), arrived_roster_id=str(ramesh_id),
                created_by=str(ghost_id),
            ))
            board = await leaderboard(actor=ADMIN)
            by_name = {row["name"]: row for row in board["volunteers"]}
            assert by_name["Anita"]["registrations"] == 1
            assert by_name["Anita"]["completed"] == 0
            assert by_name["Ramesh"]["registrations"] == 1
            assert by_name["Ramesh"]["completed"] == 0

        run_camp(monkeypatch, body)
