from bson import ObjectId

from conftest import CommandLog
from routes_reports import leaderboard
from seed import ADMIN, patient_doc, run_camp, seed_camp, user_doc


async def _seed(database, n_volunteers, n_leads, patients_each=2):
    camp_id, _ = await seed_camp(database, name="Camp", venue="Hall A")
    leads = [ObjectId() for _ in range(n_leads)]
    volunteers = [(ObjectId(), leads[i % len(leads)] if leads else None) for i in range(n_volunteers)]
    await database.users.insert_many(
        [user_doc(f"Lead {i:03d}", "team_lead", _id=lead_id) for i, lead_id in enumerate(leads)]
        + [
            user_doc(f"Vol {i:03d}", _id=vol_id, team_lead_id=str(lead_id) if lead_id else None)
            for i, (vol_id, lead_id) in enumerate(volunteers)
        ]
    )
    patients = [
        patient_doc(
            camp_id=camp_id, created_by=str(vol_id),
            registrar_team_lead_id=str(lead_id) if lead_id else None,
            committed_revision_id=ObjectId() if n == 0 else None,
        )
        for vol_id, lead_id in volunteers for n in range(patients_each)
    ]
    if patients:
        await database.patients.insert_many(patients)
    return camp_id, volunteers, leads


def test_leaderboard_db_calls_do_not_grow_with_staff_count(monkeypatch):
    log = CommandLog()

    async def body(database):
        async def board_commands(n_volunteers, n_leads):
            for collection in ("camps", "camp_days", "users", "patients"):
                await database[collection].delete_many({})
            await _seed(database, n_volunteers=n_volunteers, n_leads=n_leads)
            log.commands.clear()
            board = await leaderboard(actor=ADMIN)
            return len(log.commands), board

        small_calls, small_board = await board_commands(3, 2)
        large_calls, large_board = await board_commands(50, 5)

        assert len(small_board["volunteers"]) == 3
        assert len(large_board["volunteers"]) == 50
        assert small_calls == large_calls
        assert large_calls <= 8

    run_camp(monkeypatch, body, listener=log)


def test_leaderboard_keeps_attribution_and_response_shape(monkeypatch):
    async def body(database):
        camp_id, volunteers, leads = await _seed(database, n_volunteers=2, n_leads=1)
        lead_id = leads[0]
        await database.patients.insert_many([
            patient_doc(
                camp_id=camp_id, created_by=str(lead_id),
                registrar_team_lead_id=str(lead_id), committed_revision_id=ObjectId(),
            ),
            patient_doc(
                camp_id=camp_id, created_by=None,
                registrar_team_lead_id=str(lead_id), committed_revision_id=ObjectId(),
                is_self_registered=True,
            ),
            patient_doc(
                camp_id=ObjectId(), created_by=str(volunteers[0][0]),
                registrar_team_lead_id=str(lead_id), committed_revision_id=ObjectId(),
            ),
        ])

        board = await leaderboard(actor=ADMIN)

        assert set(board) == {"volunteers", "team_leads"}
        vol = next(v for v in board["volunteers"] if v["id"] == str(volunteers[0][0]))
        assert set(vol) == {"id", "name", "registrations", "completed", "team_lead_id"}
        assert vol["registrations"] == 2
        assert vol["completed"] == 1
        assert vol["team_lead_id"] == str(lead_id)

        lead = next(row for row in board["team_leads"] if row["id"] == str(lead_id))
        assert set(lead) == {
            "id", "name", "personal_registrations", "personal_completed",
            "registrations", "completed",
        }
        assert lead["personal_registrations"] == 1
        assert lead["personal_completed"] == 1
        assert lead["registrations"] == 6
        assert lead["completed"] == 3

    run_camp(monkeypatch, body)


def test_leaderboard_sorts_by_points_then_name(monkeypatch):
    async def body(database):
        camp_id, volunteers, _leads = await _seed(database, n_volunteers=3, n_leads=1, patients_each=0)
        top = volunteers[2][0]
        await database.patients.insert_one(patient_doc(
            camp_id=camp_id, created_by=str(top), registrar_team_lead_id=None, committed_revision_id=ObjectId(),
        ))
        board = await leaderboard(actor=ADMIN)
        assert [v["name"] for v in board["volunteers"]] == ["Vol 002", "Vol 000", "Vol 001"]

    run_camp(monkeypatch, body)


def test_leaderboard_without_active_camp_is_empty(monkeypatch):
    async def body(database):
        assert await leaderboard(actor=ADMIN) == {"volunteers": [], "team_leads": []}
        assert await database.patients.count_documents({}) == 0

    run_camp(monkeypatch, body)
