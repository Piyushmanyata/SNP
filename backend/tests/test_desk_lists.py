from datetime import timedelta

from bson import ObjectId

from seed import NOW, TODAY, TOMORROW, asgi_client, bearer, patient_doc, run_camp, seed_camp, user_doc


async def volunteer(database):
    user_id = ObjectId()
    await database.users.insert_one(user_doc("Ramesh", _id=user_id))
    return bearer(user_id, "Ramesh", "volunteer")


def test_pending_is_every_printed_patient_not_yet_seen_in_the_active_camp_oldest_print_first(monkeypatch):
    async def run(database):
        camp_id, (today_id, tomorrow_id) = await seed_camp(database, days=(TODAY, TOMORROW))
        headers = await volunteer(database)

        def row(name, **fields):
            return patient_doc(**{"camp_id": camp_id, "camp_day_id": today_id, "full_name": name,
                                  "queue_status": "arrived", "arrived_at": NOW, "printed_at": NOW, **fields})

        yesterday = NOW - timedelta(days=1)
        await database.patients.insert_many([
            row("From Yesterday", camp_day_id=tomorrow_id, arrived_at=yesterday, printed_at=yesterday),
            row("Waiting Longest", printed_at=NOW - timedelta(minutes=40)),
            row("Already Seen", queue_status="seen", seen_at=NOW),
            row("Not Printed", printed_at=None),
            row("Other Camp", camp_id=ObjectId()),
            row("Not Arrived", queue_status="registered", arrived_at=None, printed_at=None),
        ])
        async with asgi_client() as client:
            typed = {"full_name": "Kamla Bai", "age": 62, "gender": "F", "phone": "9876500011",
                     "camp_day_id": str(today_id), "manual_reason": "no_card", "at_door": True}
            reg = (await client.post("/api/register", json=typed, headers=headers)).json()["registration"]
            assert (await client.post(f"/api/desk/print/{reg['id']}", headers=headers)).status_code == 200

            kpis = (await client.get("/api/kpis", headers=headers)).json()
            listed = await client.get("/api/lists/pending", headers=headers)
        assert kpis["pending"] == 3
        assert listed.status_code == 200, listed.text
        assert listed.json()["today"] == TODAY
        assert listed.json()["total"] == 3
        rows = listed.json()["patients"]
        assert [p["full_name"] for p in rows] == ["From Yesterday", "Waiting Longest", "Kamla Bai"]
        assert rows[0]["arrived_at"].startswith(yesterday.date().isoformat())
        assert rows[2]["printed_by_name"] == "Ramesh"
        assert rows[2]["phone"] == "9876500011"

    run_camp(monkeypatch, run)


def test_a_list_shows_ten_and_counts_the_rest(monkeypatch):
    async def run(database):
        camp_id, (day_id,) = await seed_camp(database)
        await database.patients.insert_many([
            patient_doc(camp_id=camp_id, camp_day_id=day_id, full_name=f"Waiting {minutes}",
                        queue_status="arrived", arrived_at=NOW, printed_at=NOW - timedelta(minutes=minutes))
            for minutes in range(12)
        ])
        headers = await volunteer(database)
        async with asgi_client() as client:
            listed = (await client.get("/api/lists/pending", headers=headers)).json()
        assert listed["total"] == 12
        assert [p["full_name"] for p in listed["patients"]] == [f"Waiting {m}" for m in range(11, 1, -1)]

    run_camp(monkeypatch, run)


def test_registered_is_every_registration_in_the_camp_newest_first_with_its_stage(monkeypatch):
    async def run(database):
        camp_id, (day_id,) = await seed_camp(database)

        def row(name, **fields):
            return patient_doc(camp_id=camp_id, camp_day_id=day_id, full_name=name, **fields)

        await database.patients.insert_many([
            row("Booked Only", queue_status="registered", arrived_at=None, printed_at=None),
            row("At The Door", queue_status="arrived", arrived_at=NOW, printed_at=None),
            row("Holding Paper", queue_status="arrived", arrived_at=NOW, printed_at=NOW),
            row("Doctor Done", queue_status="seen", arrived_at=NOW, printed_at=NOW, seen_at=NOW),
            patient_doc(camp_id=ObjectId(), camp_day_id=ObjectId(), full_name="Other Camp", queue_status="registered"),
        ])
        headers = await volunteer(database)
        async with asgi_client() as client:
            listed = (await client.get("/api/lists/registered", headers=headers)).json()
            kpis = (await client.get("/api/kpis", headers=headers)).json()
        assert listed["total"] == kpis["registered"] == 4
        assert [(p["full_name"], p["stage"]) for p in listed["patients"]] == [
            ("Doctor Done", "seen"),
            ("Holding Paper", "pending"),
            ("At The Door", "awaiting_print"),
            ("Booked Only", "booked"),
        ]

    run_camp(monkeypatch, run)


def test_seen_is_every_doctor_seen_patient_most_recently_seen_first(monkeypatch):
    async def run(database):
        camp_id, (day_id,) = await seed_camp(database)

        def seen(name, minutes_ago):
            at = NOW - timedelta(minutes=minutes_ago)
            return patient_doc(camp_id=camp_id, camp_day_id=day_id, full_name=name,
                               queue_status="seen", arrived_at=at, printed_at=at, seen_at=at)

        await database.patients.insert_many([
            seen("Seen An Hour Ago", 60),
            seen("Seen Just Now", 1),
            seen("Seen Earlier", 30),
            patient_doc(camp_id=camp_id, camp_day_id=day_id, full_name="Still Waiting",
                        queue_status="arrived", arrived_at=NOW, printed_at=NOW),
        ])
        headers = await volunteer(database)
        async with asgi_client() as client:
            listed = (await client.get("/api/lists/seen", headers=headers)).json()
        assert listed["total"] == 3
        assert [p["full_name"] for p in listed["patients"]] == ["Seen Just Now", "Seen Earlier", "Seen An Hour Ago"]

    run_camp(monkeypatch, run)


def test_a_list_searches_by_registration_number_household_phone_or_any_word_of_the_name(monkeypatch):
    async def run(database):
        camp_id, (day_id,) = await seed_camp(database)

        def row(reg_no, name, phone, **fields):
            return patient_doc(**{
                "camp_id": camp_id, "camp_day_id": day_id, "reg_no": reg_no, "full_name": name,
                "full_name_normalized": name.lower(), "phone": phone, "phone_normalized": phone,
                "queue_status": "registered", **fields,
            })

        await database.patients.insert_many([
            row(412, "Ram Kumar", "9876543210"),
            row(4120, "Kumari Devi", "9876543210", queue_status="seen", seen_at=NOW),
            row(413, "Shyam Akumar", "9123456780"),
            row(414, "Geeta Bai", "9000000001"),
            patient_doc(camp_id=ObjectId(), camp_day_id=ObjectId(), reg_no=415, full_name="Ram Kumar",
                        full_name_normalized="ram kumar", phone_normalized="9876543210"),
        ])
        headers = await volunteer(database)

        async with asgi_client() as client:
            async def search(q, stage="registered"):
                r = await client.get(f"/api/lists/{stage}", params={"q": q}, headers=headers)
                assert r.status_code == 200, r.text
                return r.json()["total"], [p["reg_no"] for p in r.json()["patients"]]

            assert await search("412") == (1, [412])
            assert await search(" 0412 ") == (1, [412])
            assert await search("+91 98765-43210") == (2, [4120, 412])
            assert await search("09876543210") == (2, [4120, 412])
            assert await search("kum") == (2, [4120, 412])
            assert await search("DEVI") == (1, [4120])
            assert await search("ram ku") == (1, [412])
            assert await search("kum", stage="seen") == (1, [4120])
            assert await search("12345678901") == (0, [])
            assert await search("5432") == (0, [])
            assert await search(".*") == (0, [])
            assert await search("   ") == (4, [4120, 414, 413, 412])

    run_camp(monkeypatch, run)


def test_a_crowded_search_counts_up_to_a_limit_and_says_so(monkeypatch):
    import routes_reports
    monkeypatch.setattr(routes_reports, "SEARCH_COUNT_LIMIT", 3)

    async def run(database):
        camp_id, (day_id,) = await seed_camp(database)
        await database.patients.insert_many([
            patient_doc(camp_id=camp_id, camp_day_id=day_id, reg_no=500 + n, full_name=f"Kumar {n}",
                        full_name_normalized=f"kumar {n}", queue_status="registered")
            for n in range(5)
        ] + [patient_doc(camp_id=camp_id, camp_day_id=day_id, reg_no=600, full_name="Geeta Bai",
                         full_name_normalized="geeta bai", queue_status="registered")])
        headers = await volunteer(database)
        async with asgi_client() as client:
            async def listed(q):
                return (await client.get("/api/lists/registered", params={"q": q}, headers=headers)).json()

            crowded, single, everyone = await listed("kum"), await listed("geeta"), await listed("")
        assert (crowded["total"], crowded["total_is_floor"]) == (3, True)
        assert [p["reg_no"] for p in crowded["patients"]] == [504, 503, 502, 501, 500]
        assert (single["total"], single["total_is_floor"]) == (1, False)
        assert (everyone["total"], everyone["total_is_floor"]) == (6, False)

    run_camp(monkeypatch, run)


def test_find_one_patient_reads_a_typed_line_the_same_way(monkeypatch):
    async def run(database):
        camp_id, (day_id,) = await seed_camp(database)
        await database.patients.insert_many([
            patient_doc(camp_id=camp_id, camp_day_id=day_id, full_name=name, full_name_normalized=name.lower(),
                        phone_normalized="9876543210", queue_status="registered")
            for name in ("Ram Kumar", "Kumari Devi", "Shyam Akumar")
        ])
        headers = await volunteer(database)
        async with asgi_client() as client:
            async def find(q):
                r = await client.get("/api/patients/search", params={"q": q}, headers=headers)
                assert r.status_code == 200, r.text
                return sorted(p["full_name"] for p in r.json()["results"])

            assert await find("kumar") == ["Kumari Devi", "Ram Kumar"]
            assert await find("+91 98765 43210") == ["Kumari Devi", "Ram Kumar", "Shyam Akumar"]
            assert await find(".*") == []

    run_camp(monkeypatch, run)


def test_the_clinical_desk_operator_cannot_open_the_desk_lists_or_counts(monkeypatch):
    async def run(database):
        await seed_camp(database)
        user_id = ObjectId()
        await database.users.insert_one(user_doc("Clin", role="clinical_desk_operator", _id=user_id))
        headers = bearer(user_id, "Clin", "clinical_desk_operator")
        async with asgi_client() as client:
            for stage in ("registered", "seen", "pending"):
                assert (await client.get(f"/api/lists/{stage}", headers=headers)).status_code == 403
            assert (await client.get("/api/kpis", headers=headers)).status_code == 403

    run_camp(monkeypatch, run)
