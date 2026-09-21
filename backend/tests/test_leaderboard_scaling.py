import os
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "snp_test")

import asyncio

from bson import ObjectId

from routes_reports import leaderboard
from test_adversarial_challenger import setup_mock_db

ADMIN = {"_id": ObjectId(), "name": "Admin", "role": "admin"}


async def _seed(mock_db, n_volunteers, n_leads, patients_each=2):
    camp_id = ObjectId()
    mock_db.camps.docs.append({"_id": camp_id, "name": "Camp", "venue": "Hall A", "is_active": True})
    leads = []
    for i in range(n_leads):
        lead_id = ObjectId()
        mock_db.users.docs.append({"_id": lead_id, "name": f"Lead {i:03d}", "role": "team_lead"})
        leads.append(lead_id)
    volunteers = []
    for i in range(n_volunteers):
        vol_id = ObjectId()
        lead_id = leads[i % len(leads)] if leads else None
        mock_db.users.docs.append({
            "_id": vol_id, "name": f"Vol {i:03d}", "role": "volunteer",
            "team_lead_id": str(lead_id) if lead_id else None,
        })
        volunteers.append((vol_id, lead_id))
        for n in range(patients_each):
            mock_db.patients.docs.append({
                "_id": ObjectId(), "camp_id": camp_id,
                "created_by": str(vol_id),
                "registrar_team_lead_id": str(lead_id) if lead_id else None,
                "committed_revision_id": ObjectId() if n == 0 else None,
            })
    return camp_id, volunteers, leads


def _query_count(mock_db, coro_factory):
    async def run():
        mock_db.query_count = 0
        board = await coro_factory()
        return mock_db.query_count, board
    return asyncio.run(run())


def test_leaderboard_db_calls_do_not_grow_with_staff_count(monkeypatch):
    small = setup_mock_db(monkeypatch)
    asyncio.run(_seed(small, n_volunteers=3, n_leads=2))
    small_calls, small_board = _query_count(small, lambda: leaderboard(actor=ADMIN))

    large = setup_mock_db(monkeypatch)
    asyncio.run(_seed(large, n_volunteers=50, n_leads=5))
    large_calls, large_board = _query_count(large, lambda: leaderboard(actor=ADMIN))

    assert len(small_board["volunteers"]) == 3
    assert len(large_board["volunteers"]) == 50
    assert small_calls == large_calls
    assert large_calls <= 8


def test_leaderboard_keeps_attribution_and_response_shape(monkeypatch):
    mock_db = setup_mock_db(monkeypatch)
    camp_id, volunteers, leads = asyncio.run(_seed(mock_db, n_volunteers=2, n_leads=1))
    lead_id = leads[0]
    mock_db.patients.docs.append({
        "_id": ObjectId(), "camp_id": camp_id, "created_by": str(lead_id),
        "registrar_team_lead_id": str(lead_id), "committed_revision_id": ObjectId(),
    })
    mock_db.patients.docs.append({
        "_id": ObjectId(), "camp_id": camp_id, "created_by": None,
        "registrar_team_lead_id": str(lead_id), "committed_revision_id": ObjectId(),
        "is_self_registered": True,
    })
    other_camp = ObjectId()
    mock_db.patients.docs.append({
        "_id": ObjectId(), "camp_id": other_camp, "created_by": str(volunteers[0][0]),
        "registrar_team_lead_id": str(lead_id), "committed_revision_id": ObjectId(),
    })

    board = asyncio.run(leaderboard(actor=ADMIN))

    assert set(board) == {"volunteers", "team_leads"}
    vol = next(v for v in board["volunteers"] if v["id"] == str(volunteers[0][0]))
    assert set(vol) == {"id", "name", "registrations", "doctor_seen", "arrivals", "points", "team_lead_id"}
    assert vol["registrations"] == 2
    assert vol["points"] == 1
    assert vol["doctor_seen"] == 1
    assert vol["arrivals"] == 1
    assert vol["team_lead_id"] == str(lead_id)

    lead = next(l for l in board["team_leads"] if l["id"] == str(lead_id))
    assert set(lead) == {
        "id", "name", "personal_registrations", "personal_points",
        "registrations", "doctor_seen", "points",
    }
    assert lead["personal_registrations"] == 1
    assert lead["personal_points"] == 1
    assert lead["registrations"] == 6
    assert lead["points"] == 3
    assert lead["doctor_seen"] == 3


def test_leaderboard_sorts_by_points_then_name(monkeypatch):
    mock_db = setup_mock_db(monkeypatch)
    camp_id, volunteers, _leads = asyncio.run(_seed(mock_db, n_volunteers=3, n_leads=1, patients_each=0))
    top = volunteers[2][0]
    mock_db.patients.docs.append({
        "_id": ObjectId(), "camp_id": camp_id, "created_by": str(top),
        "registrar_team_lead_id": None, "committed_revision_id": ObjectId(),
    })
    board = asyncio.run(leaderboard(actor=ADMIN))
    assert [v["name"] for v in board["volunteers"]] == ["Vol 002", "Vol 000", "Vol 001"]


def test_leaderboard_without_active_camp_is_empty(monkeypatch):
    mock_db = setup_mock_db(monkeypatch)
    assert asyncio.run(leaderboard(actor=ADMIN)) == {"volunteers": [], "team_leads": []}
    assert mock_db.patients.docs == []
