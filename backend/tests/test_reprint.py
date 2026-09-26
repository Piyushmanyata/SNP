from bson import ObjectId

from seed import CARD, asgi_client, bearer, run_camp, seed_camp, user_doc


def test_a_door_scan_of_a_printed_patient_offers_no_sheet_but_a_lookup_reprints(monkeypatch):
    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database)
        user_id = ObjectId()
        await database.users.insert_one(user_doc("Ramesh", _id=user_id))
        headers = bearer(user_id, "Ramesh", "volunteer")
        async with asgi_client() as client:
            booked = await client.post("/api/register", headers=headers, json={
                "full_name": "", "phone": "9876500001", "camp_day_id": str(day_id),
                "aadhaar_scanned": True, "qr_payload": CARD,
            })
            assert booked.status_code == 200, booked.text
            first = (await client.post("/api/desk/scan", json={"payload": CARD}, headers=headers)).json()
            assert first["prescription"]
            patient_id = first["registration"]["id"]
            assert (await client.post(f"/api/desk/print/{patient_id}", headers=headers)).status_code == 200

            again = (await client.post("/api/desk/scan", json={"payload": CARD}, headers=headers)).json()
            assert again["outcome"] == "arrived"
            assert again["registration"]["printed_at"]
            assert again["registration"]["printed_by_name"] == "Ramesh"
            assert again["prescription"] is None
            reprint = await client.get(f"/api/desk/print/{patient_id}", headers=headers)
            assert reprint.status_code == 200, reprint.text

    run_camp(monkeypatch, run)
