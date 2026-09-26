from datetime import timedelta

from bson import ObjectId

from seed import NOW, TODAY, TOMORROW, asgi_client, bearer, patient_doc, run_camp, seed_camp, user_doc


def test_pending_is_printed_but_not_seen_on_the_operating_day_oldest_print_first(monkeypatch):
    async def run(database):
        camp_id, (today_id, tomorrow_id) = await seed_camp(database, days=(TODAY, TOMORROW))
        user_id = ObjectId()
        await database.users.insert_one(user_doc("Ramesh", _id=user_id))
        headers = bearer(user_id, "Ramesh", "volunteer")

        def row(name, **fields):
            return patient_doc(**{"camp_id": camp_id, "camp_day_id": today_id, "full_name": name,
                                  "queue_status": "arrived", "arrived_at": NOW, "printed_at": NOW, **fields})

        await database.patients.insert_many([
            row("Waiting Longest", printed_at=NOW - timedelta(minutes=40)),
            row("Already Seen", queue_status="seen", seen_at=NOW),
            row("Not Printed", printed_at=None),
            row("Other Day", camp_day_id=tomorrow_id),
            row("Not Arrived", queue_status="registered", arrived_at=None, printed_at=None),
        ])
        async with asgi_client() as client:
            typed = {"full_name": "Kamla Bai", "age": 62, "gender": "F", "phone": "9876500011",
                     "camp_day_id": str(today_id), "manual_reason": "no_card", "at_door": True}
            reg = (await client.post("/api/register", json=typed, headers=headers)).json()["registration"]
            assert (await client.post(f"/api/desk/print/{reg['id']}", headers=headers)).status_code == 200

            kpis = (await client.get("/api/kpis", headers=headers)).json()
            listed = await client.get("/api/pending", headers=headers)
        assert kpis["pending"] == 2
        assert listed.status_code == 200, listed.text
        rows = listed.json()["patients"]
        assert [p["full_name"] for p in rows] == ["Waiting Longest", "Kamla Bai"]
        assert rows[1]["printed_by_name"] == "Ramesh"
        assert rows[1]["phone"] == "9876500011"

    run_camp(monkeypatch, run)


def test_the_clinical_desk_operator_cannot_list_pending(monkeypatch):
    async def run(database):
        await seed_camp(database)
        user_id = ObjectId()
        await database.users.insert_one(user_doc("Clin", role="clinical_desk_operator", _id=user_id))
        headers = bearer(user_id, "Clin", "clinical_desk_operator")
        async with asgi_client() as client:
            assert (await client.get("/api/pending", headers=headers)).status_code == 403
            assert (await client.get("/api/kpis", headers=headers)).status_code == 403

    run_camp(monkeypatch, run)
