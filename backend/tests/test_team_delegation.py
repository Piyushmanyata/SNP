import asyncio
import os
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "snp_test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("COOKIE_SECURE", "false")

from bson import ObjectId
from fastapi.testclient import TestClient

import db as db_module
import routes_auth
import routes_staff
import routes_reports
import security
import server as server_mod
from security import hash_pin
from test_adversarial_challenger import setup_mock_db


def _patch_db(monkeypatch, mock_db):
    for mod in (db_module, routes_staff, routes_auth, routes_reports, security):
        monkeypatch.setattr(mod, "get_db", lambda: mock_db)
    return mock_db


def _client(monkeypatch, mock_db):
    monkeypatch.setattr(server_mod, "init_indexes", lambda: asyncio.sleep(0))
    monkeypatch.setattr(server_mod, "seed_admin", lambda: asyncio.sleep(0))
    _patch_db(monkeypatch, mock_db)
    server_mod.app.router.on_startup.clear()
    return TestClient(server_mod.app, raise_server_exceptions=True)


def _auth(user_id, name, role):
    token = security.create_access_token(str(user_id), name, role)
    return {"Authorization": f"Bearer {token}"}


def test_staff_creation_delegation_and_pin_reset(monkeypatch):
    async def run():
        mock_db = setup_mock_db(monkeypatch)
        _patch_db(monkeypatch, mock_db)

        admin_id = ObjectId()
        await mock_db.users.insert_one({
            "_id": admin_id, "name": "admin", "name_normalized": "admin",
            "pin_hash": hash_pin("1234"), "role": "admin", "disabled_at": None,
        })

        client = _client(monkeypatch, mock_db)
        admin_headers = _auth(admin_id, "admin", "admin")

        # 1. Admin creates Team Lead
        res = client.post("/api/staff", json={"name": "Lead One", "role": "team_lead"}, headers=admin_headers)
        assert res.status_code == 200
        lead_id = res.json()["staff"]["id"]
        await mock_db.users.update_one(
            {"_id": ObjectId(lead_id)}, {"$set": {"must_change_pin": False}},
        )

        lead_headers = _auth(lead_id, "Lead One", "team_lead")

        # 2. Team Lead creates Volunteer under them
        res = client.post("/api/staff", json={"name": "Vol Alpha", "role": "volunteer"}, headers=lead_headers)
        assert res.status_code == 200
        vol_alpha = res.json()["staff"]
        assert vol_alpha["team_lead_id"] == lead_id
        assert vol_alpha["must_change_pin"] is True

        # 3. Team Lead cannot create another Team Lead or Admin
        res = client.post("/api/staff", json={"name": "Lead Two", "role": "team_lead"}, headers=lead_headers)
        assert res.status_code == 403

        # 4. Duplicate name is rejected
        res = client.post("/api/staff", json={"name": "vol alpha", "role": "volunteer"}, headers=lead_headers)
        assert res.status_code == 409

        # 5. Team Lead can reset PIN for their volunteer
        res = client.post(f"/api/staff/{vol_alpha['id']}/reset-pin", headers=lead_headers)
        assert res.status_code == 200

        # 6. Team Lead cannot reset PIN for admin or other lead
        res = client.post(f"/api/staff/{admin_id}/reset-pin", headers=lead_headers)
        assert res.status_code == 403

        # 7. Admin creates a Clinical Desk Operator and sets the Operator line
        res = client.post(
            "/api/staff",
            json={"name": "Desk Op", "role": "clinical_desk_operator", "line": "rx"},
            headers=admin_headers,
        )
        assert res.status_code == 200
        op = res.json()["staff"]
        assert op["line"] == "rx"
        res = client.patch(f"/api/staff/{op['id']}", json={"line": "ot"}, headers=admin_headers)
        assert res.status_code == 200
        assert res.json()["staff"]["line"] == "ot"

        # 8. Team Lead list is only their Volunteers
        other_lead = client.post(
            "/api/staff", json={"name": "Lead Two", "role": "team_lead"}, headers=admin_headers,
        ).json()["staff"]
        client.post(
            "/api/staff",
            json={"name": "Vol Other", "role": "volunteer", "team_lead_id": other_lead["id"]},
            headers=admin_headers,
        )
        listed = client.get("/api/staff", headers=lead_headers)
        assert listed.status_code == 200
        names = [s["name"] for s in listed.json()["staff"]]
        assert names == ["Vol Alpha"]
        assert "Lead One" not in names
        assert "Vol Other" not in names
        assert "Desk Op" not in names

    asyncio.run(run())


def test_dual_leaderboard_scoring(monkeypatch):
    async def run():
        mock_db = setup_mock_db(monkeypatch)
        _patch_db(monkeypatch, mock_db)

        camp_id = ObjectId()
        await mock_db.camps.insert_one({"_id": camp_id, "name": "Camp Alpha", "is_active": True})

        lead1_id = ObjectId()
        await mock_db.users.insert_one({
            "_id": lead1_id, "name": "Lead One", "role": "team_lead", "disabled_at": None,
        })

        lead2_id = ObjectId()
        await mock_db.users.insert_one({
            "_id": lead2_id, "name": "Lead Two", "role": "team_lead", "disabled_at": None,
        })

        vol1_id = ObjectId()
        await mock_db.users.insert_one({
            "_id": vol1_id, "name": "Vol 1", "role": "volunteer", "team_lead_id": str(lead1_id), "disabled_at": None,
        })

        vol2_id = ObjectId()
        await mock_db.users.insert_one({
            "_id": vol2_id, "name": "Vol 2", "role": "volunteer", "team_lead_id": str(lead1_id), "disabled_at": None,
        })

        vol3_id = ObjectId()
        await mock_db.users.insert_one({
            "_id": vol3_id, "name": "Vol 3", "role": "volunteer", "team_lead_id": str(lead2_id), "disabled_at": None,
        })

        rev = ObjectId()
        await mock_db.patients.insert_one({
            "camp_id": camp_id, "created_by": str(vol1_id),
            "registrar_team_lead_id": str(lead1_id), "committed_revision_id": rev,
        })
        await mock_db.patients.insert_one({
            "camp_id": camp_id, "created_by": str(vol1_id),
            "registrar_team_lead_id": str(lead1_id), "committed_revision_id": None,
        })
        await mock_db.patients.insert_one({
            "camp_id": camp_id, "created_by": str(vol2_id),
            "registrar_team_lead_id": str(lead1_id), "committed_revision_id": ObjectId(),
        })
        await mock_db.patients.insert_one({
            "camp_id": camp_id, "created_by": str(vol3_id),
            "registrar_team_lead_id": str(lead2_id), "committed_revision_id": None,
            "arrived_by": str(vol3_id),
        })

        client = _client(monkeypatch, mock_db)
        headers = _auth(lead1_id, "Lead One", "team_lead")

        res = client.get("/api/leaderboard", headers=headers)
        assert res.status_code == 200
        data = res.json()

        assert "volunteers" in data
        assert "team_leads" in data

        # Check Volunteers
        vols_by_name = {v["name"]: v for v in data["volunteers"]}
        assert vols_by_name["Vol 1"]["points"] == 1
        assert vols_by_name["Vol 1"]["registrations"] == 2
        assert vols_by_name["Vol 2"]["points"] == 1
        assert vols_by_name["Vol 3"]["points"] == 0

        leads_by_name = {l["name"]: l for l in data["team_leads"]}
        assert leads_by_name["Lead One"]["points"] == 2
        assert leads_by_name["Lead Two"]["points"] == 0

    asyncio.run(run())
