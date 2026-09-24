import httpx
from bson import ObjectId

import security
import server
from security import hash_pin
from seed import patient_doc, run_camp, seed_camp, user_doc


def _http(monkeypatch, body):
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("COOKIE_SECURE", "false")

    async def with_client(database):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            return await body(database, client)

    return run_camp(monkeypatch, with_client)


def _auth(user_id, name, role):
    token = security.create_access_token(str(user_id), name, role)
    return {"Authorization": f"Bearer {token}"}


def test_staff_creation_delegation_and_pin_reset(monkeypatch):
    async def body(database, client):
        admin_id = ObjectId()
        await database.users.insert_one(user_doc("admin", "admin", _id=admin_id, pin_hash=hash_pin("1234")))
        admin_headers = _auth(admin_id, "admin", "admin")

        res = await client.post("/api/staff", json={"name": "Lead One", "role": "team_lead"}, headers=admin_headers)
        assert res.status_code == 200
        lead_id = res.json()["staff"]["id"]
        await database.users.update_one({"_id": ObjectId(lead_id)}, {"$set": {"must_change_pin": False}})

        lead_headers = _auth(lead_id, "Lead One", "team_lead")

        res = await client.post("/api/staff", json={"name": "Vol Alpha", "role": "volunteer"}, headers=lead_headers)
        assert res.status_code == 200
        vol_alpha = res.json()["staff"]
        assert vol_alpha["team_lead_id"] == lead_id
        assert vol_alpha["must_change_pin"] is True

        res = await client.post("/api/staff", json={"name": "Lead Two", "role": "team_lead"}, headers=lead_headers)
        assert res.status_code == 403

        res = await client.post("/api/staff", json={"name": "vol alpha", "role": "volunteer"}, headers=lead_headers)
        assert res.status_code == 409

        res = await client.post(f"/api/staff/{vol_alpha['id']}/reset-pin", headers=lead_headers)
        assert res.status_code == 200

        res = await client.post(f"/api/staff/{admin_id}/reset-pin", headers=lead_headers)
        assert res.status_code == 403

        res = await client.post(
            "/api/staff",
            json={"name": "Desk Op", "role": "clinical_desk_operator", "line": "rx"},
            headers=admin_headers,
        )
        assert res.status_code == 200
        op = res.json()["staff"]
        assert op["line"] == "rx"
        res = await client.patch(f"/api/staff/{op['id']}", json={"line": "ot"}, headers=admin_headers)
        assert res.status_code == 200
        assert res.json()["staff"]["line"] == "ot"

        other_lead = (await client.post(
            "/api/staff", json={"name": "Lead Two", "role": "team_lead"}, headers=admin_headers,
        )).json()["staff"]
        await client.post(
            "/api/staff",
            json={"name": "Vol Other", "role": "volunteer", "team_lead_id": other_lead["id"]},
            headers=admin_headers,
        )
        listed = await client.get("/api/staff", headers=lead_headers)
        assert listed.status_code == 200
        names = [s["name"] for s in listed.json()["staff"]]
        assert names == ["Vol Alpha"]
        assert "Lead One" not in names
        assert "Vol Other" not in names
        assert "Desk Op" not in names

    _http(monkeypatch, body)


def test_dual_leaderboard_scoring(monkeypatch):
    async def body(database, client):
        camp_id, _ = await seed_camp(database, name="Camp Alpha")
        lead1_id, lead2_id, vol1_id, vol2_id, vol3_id = (ObjectId() for _ in range(5))
        await database.users.insert_many([
            user_doc("Lead One", "team_lead", _id=lead1_id),
            user_doc("Lead Two", "team_lead", _id=lead2_id),
            user_doc("Vol 1", _id=vol1_id, team_lead_id=str(lead1_id)),
            user_doc("Vol 2", _id=vol2_id, team_lead_id=str(lead1_id)),
            user_doc("Vol 3", _id=vol3_id, team_lead_id=str(lead2_id)),
        ])
        await database.patients.insert_many([
            patient_doc(camp_id=camp_id, created_by=str(vol1_id),
                        registrar_team_lead_id=str(lead1_id), committed_revision_id=ObjectId()),
            patient_doc(camp_id=camp_id, created_by=str(vol1_id),
                        registrar_team_lead_id=str(lead1_id), committed_revision_id=None),
            patient_doc(camp_id=camp_id, created_by=str(vol2_id),
                        registrar_team_lead_id=str(lead1_id), committed_revision_id=ObjectId()),
            patient_doc(camp_id=camp_id, created_by=str(vol3_id),
                        registrar_team_lead_id=str(lead2_id), committed_revision_id=None, arrived_by=str(vol3_id)),
        ])

        res = await client.get("/api/leaderboard", headers=_auth(lead1_id, "Lead One", "team_lead"))
        assert res.status_code == 200
        data = res.json()

        assert "volunteers" in data
        assert "team_leads" in data

        vols_by_name = {v["name"]: v for v in data["volunteers"]}
        assert vols_by_name["Vol 1"]["points"] == 1
        assert vols_by_name["Vol 1"]["registrations"] == 2
        assert vols_by_name["Vol 2"]["points"] == 1
        assert vols_by_name["Vol 3"]["points"] == 0

        leads_by_name = {l["name"]: l for l in data["team_leads"]}
        assert leads_by_name["Lead One"]["points"] == 2
        assert leads_by_name["Lead Two"]["points"] == 0

    _http(monkeypatch, body)
