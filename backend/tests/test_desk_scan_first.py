"""Desk scan-first registration, occupancy, print window, SNP Rx defaults."""
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from conftest import API

TAG = uuid.uuid4().hex[:8]
TODAY_IST = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
FUTURE = (datetime.now(ZoneInfo("Asia/Kolkata")) + timedelta(days=40)).strftime("%Y-%m-%d")
PAST = (datetime.now(ZoneInfo("Asia/Kolkata")) - timedelta(days=40)).strftime("%Y-%m-%d")


def _camp(admin, suffix):
    r = admin.post(f"{API}/camps", json={
        "name": f"TEST_SF_{suffix}_{TAG}",
        "venue": "Sikar Bhawan",
        "camp_date": TODAY_IST,
    }, timeout=30)
    assert r.status_code == 200, r.text
    cid = r.json()["camp"]["id"]
    assert admin.post(f"{API}/camps/{cid}/activate", timeout=30).status_code == 200
    return cid


def _day(admin, camp_id, day_date, seat_limit=0):
    r = admin.post(f"{API}/camps/days", json={
        "camp_id": camp_id, "day_date": day_date, "seat_limit": seat_limit,
    }, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["day"]


def _open_print(admin, day_id, open_=True):
    r = admin.patch(f"{API}/camps/days/{day_id}/print-window",
                    json={"printing_open": open_}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["day"]


def _reg(session, camp_day_id, **fields):
    body = {
        "full_name": fields.pop("full_name", f"TEST SF {TAG}"),
        "age": fields.pop("age", 40),
        "phone": fields.pop("phone", "9876500001"),
        "camp_day_id": camp_day_id,
        "registration_request_id": fields.pop("registration_request_id", str(uuid.uuid4())),
    }
    body.update(fields)
    return session.post(f"{API}/register", json=body, timeout=30)


def _self(anon, camp_day_id, **fields):
    body = {
        "full_name": fields.pop("full_name", f"TEST SELF {TAG}"),
        "age": fields.pop("age", 33),
        "camp_day_id": camp_day_id,
        "registration_request_id": fields.pop("registration_request_id", str(uuid.uuid4())),
    }
    body.update(fields)
    return anon.post(f"{API}/self-register", json=body, timeout=30)


class TestPrintWindowNoCalendar:
    def test_print_succeeds_on_non_today_day_when_window_open(self, admin):
        camp_id = _camp(admin, "print")
        day = _day(admin, camp_id, FUTURE, seat_limit=20)
        _open_print(admin, day["id"], True)
        r = _reg(admin, day["id"], full_name=f"TEST PrintFuture {TAG}", phone="9876500101")
        assert r.status_code == 200, r.text
        pid = r.json()["registration"]["id"]
        p = admin.post(f"{API}/desk/print/{pid}", timeout=30)
        assert p.status_code == 200, p.text
        assert p.json()["registration"]["printed_at"]

    def test_print_409_when_window_closed_even_on_today(self, admin):
        camp_id = _camp(admin, "printclosed")
        day = _day(admin, camp_id, TODAY_IST, seat_limit=20)
        _open_print(admin, day["id"], False)
        r = _reg(admin, day["id"], full_name=f"TEST PrintClosed {TAG}", phone="9876500102")
        assert r.status_code == 200, r.text
        pid = r.json()["registration"]["id"]
        p = admin.post(f"{API}/desk/print/{pid}", timeout=30)
        assert p.status_code == 409, p.text
        assert p.json()["detail"]["code"] == "PRINT_WINDOW_CLOSED"

    def test_print_409_when_window_closed_on_past_day(self, admin):
        camp_id = _camp(admin, "printpast")
        day = _day(admin, camp_id, PAST, seat_limit=20)
        _open_print(admin, day["id"], False)
        r = _reg(admin, day["id"], full_name=f"TEST PrintPast {TAG}", phone="9876500103")
        assert r.status_code == 200, r.text
        pid = r.json()["registration"]["id"]
        p = admin.post(f"{API}/desk/print/{pid}", timeout=30)
        assert p.status_code == 409, p.text
        assert p.json()["detail"]["code"] == "PRINT_WINDOW_CLOSED"


class TestDuplicateInCamp:
    def test_person_in_camp_409(self, admin):
        camp_id = _camp(admin, "dupperson")
        day = _day(admin, camp_id, TODAY_IST)
        card = dict(
            full_name=f"TEST PersonKey {TAG}", age=51, gender="M", dob="1975-01-02",
            aadhaar_last4="1357", aadhaar_scanned=True, phone="9876500201",
            address="1 Test Lane",
        )
        a = _reg(admin, day["id"], **card)
        assert a.status_code == 200, a.text
        reg_no = a.json()["registration"]["reg_no"]
        b = _reg(admin, day["id"], **{**card, "registration_request_id": str(uuid.uuid4())})
        assert b.status_code == 409, b.text
        assert b.json()["detail"]["code"] == "DUPLICATE_IN_CAMP"
        assert b.json()["detail"]["registration"]["reg_no"] == reg_no

    def test_last4_and_normalized_name_409(self, admin):
        camp_id = _camp(admin, "duplast4name")
        day = _day(admin, camp_id, TODAY_IST)
        a = _reg(admin, day["id"], full_name=f"TEST LastFour Name {TAG}", age=40,
                 phone="9876500202", aadhaar_last4="2468", manual_entry=True)
        assert a.status_code == 200, a.text
        reg_no = a.json()["registration"]["reg_no"]
        b = _reg(admin, day["id"], full_name=f"test lastfour name {TAG}", age=41,
                 phone="9876500203", aadhaar_last4="2468", manual_entry=True)
        assert b.status_code == 409, b.text
        assert b.json()["detail"]["code"] == "DUPLICATE_IN_CAMP"
        assert b.json()["detail"]["registration"]["reg_no"] == reg_no

    def test_last4_and_dob_409(self, admin):
        camp_id = _camp(admin, "duplast4dob")
        day = _day(admin, camp_id, TODAY_IST)
        a = _reg(admin, day["id"], full_name=f"TEST Dob Alpha {TAG}", age=44,
                 phone="9876500204", aadhaar_last4="3690", dob="1982-04-04", manual_entry=True)
        assert a.status_code == 200, a.text
        reg_no = a.json()["registration"]["reg_no"]
        b = _reg(admin, day["id"], full_name=f"TEST Dob Beta {TAG}", age=45,
                 phone="9876500205", aadhaar_last4="3690", dob="1982-04-04", manual_entry=True)
        assert b.status_code == 409, b.text
        assert b.json()["detail"]["code"] == "DUPLICATE_IN_CAMP"
        assert b.json()["detail"]["registration"]["reg_no"] == reg_no

    def test_name_age_phone_409(self, admin):
        camp_id = _camp(admin, "dupnap")
        day = _day(admin, camp_id, TODAY_IST)
        a = _reg(admin, day["id"], full_name=f"TEST Nap {TAG}", age=38,
                 phone="9876500206", manual_entry=True)
        assert a.status_code == 200, a.text
        reg_no = a.json()["registration"]["reg_no"]
        b = _reg(admin, day["id"], full_name=f"TEST Nap {TAG}", age=38,
                 phone="9876500206", manual_entry=True)
        assert b.status_code == 409, b.text
        assert b.json()["detail"]["code"] == "DUPLICATE_IN_CAMP"
        assert b.json()["detail"]["registration"]["reg_no"] == reg_no

    def test_override_duplicate_does_not_create_second_reg_no(self, admin):
        camp_id = _camp(admin, "dupoverride")
        day = _day(admin, camp_id, TODAY_IST)
        a = _reg(admin, day["id"], full_name=f"TEST Override {TAG}", age=29,
                 phone="9876500207", aadhaar_last4="7777", manual_entry=True)
        assert a.status_code == 200, a.text
        b = _reg(admin, day["id"], full_name=f"TEST Override {TAG}", age=29,
                 phone="9876500208", aadhaar_last4="7777", manual_entry=True,
                 override_duplicate=True)
        assert b.status_code == 409, b.text
        assert b.json()["detail"]["code"] == "DUPLICATE_IN_CAMP"
        assert b.json()["detail"]["registration"]["reg_no"] == a.json()["registration"]["reg_no"]

    def test_phone_only_does_not_hard_block(self, admin):
        camp_id = _camp(admin, "dupphone")
        day = _day(admin, camp_id, TODAY_IST)
        a = _reg(admin, day["id"], full_name=f"TEST Sibling A {TAG}", age=12,
                 phone="9876500209", manual_entry=True)
        b = _reg(admin, day["id"], full_name=f"TEST Sibling B {TAG}", age=10,
                 phone="9876500209", manual_entry=True)
        assert a.status_code == 200, a.text
        assert b.status_code == 200, b.text
        assert a.json()["registration"]["reg_no"] != b.json()["registration"]["reg_no"]

    def test_name_age_without_phone_does_not_hard_block_on_self_register(self, admin, anon):
        camp_id = _camp(admin, "dupnameage")
        day = _day(admin, camp_id, TODAY_IST)
        a = _self(anon, day["id"], full_name=f"TEST Common {TAG}", age=40, gender="M",
                  dob="1986-01-01", aadhaar_last4="1001", aadhaar_scanned=True)
        b = _self(anon, day["id"], full_name=f"TEST Common {TAG}", age=40, gender="F",
                  dob="1986-06-06", aadhaar_last4="1002", aadhaar_scanned=True)
        assert a.status_code == 200, a.text
        assert b.status_code == 200, b.text


class TestAadhaarOverwrite:
    def test_lock_updates_exactly_one_manual_in_place(self, admin, anon):
        camp_id = _camp(admin, "ow1")
        day = _day(admin, camp_id, TODAY_IST, seat_limit=5)
        typed = _reg(admin, day["id"], full_name=f"TEST Typo {TAG}", age=60,
                     gender="M", phone="9876500301", address="typed addr",
                     aadhaar_last4="8881", dob="1965-07-07", manual_entry=True)
        assert typed.status_code == 200, typed.text
        orig = typed.json()["registration"]
        lock = _reg(admin, day["id"],
                    full_name=f"TEST Card Name {TAG}", age=61, gender="F",
                    dob="1965-07-07", aadhaar_last4="8881", aadhaar_scanned=True,
                    address="card addr", phone="9876500399")
        assert lock.status_code == 200, lock.text
        body = lock.json()
        reg = body["registration"]
        assert body.get("created") is False
        assert reg["reg_no"] == orig["reg_no"]
        assert reg["id"] == orig["id"]
        assert reg["full_name"] == f"TEST Card Name {TAG}"
        assert reg["age"] == 61
        assert reg["gender"] == "F"
        assert reg["dob"] == "1965-07-07"
        assert reg["aadhaar_last4"] == "8881"
        assert reg["address"] == "card addr"
        assert reg["phone"] == "9876500301"
        assert reg["camp_day_id"] == orig["camp_day_id"]
        assert reg["aadhaar_scanned"] is True
        assert not reg.get("manual_entry")
        pub = anon.get(f"{API}/camps/active/public", timeout=30)
        assert pub.status_code == 200, pub.text
        row = next(d for d in pub.json()["days"] if d["id"] == day["id"])
        assert row["registered"] == 1

    def test_overwrite_does_not_consume_second_seat(self, admin, anon):
        camp_id = _camp(admin, "owseat")
        day = _day(admin, camp_id, TODAY_IST, seat_limit=1)
        typed = _reg(admin, day["id"], full_name=f"TEST Seat {TAG}", age=50,
                     phone="9876500302", aadhaar_last4="8882", dob="1976-02-02",
                     manual_entry=True)
        assert typed.status_code == 200, typed.text
        lock = _reg(admin, day["id"], full_name=f"TEST Seat {TAG}", age=50,
                    gender="M", dob="1976-02-02", aadhaar_last4="8882",
                    aadhaar_scanned=True, phone="9876500302")
        assert lock.status_code == 200, lock.text
        assert lock.json()["registration"]["reg_no"] == typed.json()["registration"]["reg_no"]
        extra = _reg(admin, day["id"], full_name=f"TEST Extra {TAG}", age=22,
                     phone="9876500303", manual_entry=True)
        assert extra.status_code == 409, extra.text
        assert extra.json()["detail"]["code"] == "CAMP_DAY_FULL"
        pub = anon.get(f"{API}/camps/active/public", timeout=30).json()
        row = next(d for d in pub["days"] if d["id"] == day["id"])
        assert row["registered"] == 1

    def test_lock_matching_already_scanned_409(self, admin):
        camp_id = _camp(admin, "owscan")
        day = _day(admin, camp_id, TODAY_IST)
        first = _reg(admin, day["id"], full_name=f"TEST Scanned {TAG}", age=48,
                     gender="M", dob="1978-08-08", aadhaar_last4="8883",
                     aadhaar_scanned=True, phone="9876500304", address="a")
        assert first.status_code == 200, first.text
        second = _reg(admin, day["id"], full_name=f"TEST Scanned {TAG}", age=48,
                      gender="M", dob="1978-08-08", aadhaar_last4="8883",
                      aadhaar_scanned=True, phone="9876500305", address="b")
        assert second.status_code == 409, second.text
        assert second.json()["detail"]["code"] == "DUPLICATE_IN_CAMP"
        assert second.json()["detail"]["registration"]["reg_no"] == first.json()["registration"]["reg_no"]

    def test_lock_matching_two_manuals_409_lists_them(self, admin):
        camp_id = _camp(admin, "owtwo")
        day = _day(admin, camp_id, TODAY_IST)
        a = _reg(admin, day["id"], full_name=f"TEST Twin Card {TAG}", age=99,
                 phone="9876500306", aadhaar_last4="8884", dob="1980-01-01",
                 manual_entry=True)
        b = _reg(admin, day["id"], full_name=f"TEST Twin Other {TAG}", age=36,
                 phone="9876500307", aadhaar_last4="8884", dob="1991-01-01",
                 manual_entry=True)
        assert a.status_code == 200, a.text
        assert b.status_code == 200, b.text
        lock = _reg(admin, day["id"], full_name=f"TEST Twin Card {TAG}", age=35,
                    gender="M", dob="1991-01-01", aadhaar_last4="8884",
                    aadhaar_scanned=True, phone="9876500308")
        assert lock.status_code == 409, lock.text
        detail = lock.json()["detail"]
        assert detail["code"] in ("AMBIGUOUS_MANUAL_ENTRY", "DUPLICATE_IN_CAMP")
        listed = detail.get("registrations") or []
        if not listed and detail.get("registration"):
            listed = [detail["registration"]]
        nos = {x["reg_no"] for x in listed}
        assert a.json()["registration"]["reg_no"] in nos or len(listed) >= 2
        if "registrations" in detail:
            assert {x["reg_no"] for x in detail["registrations"]} == {
                a.json()["registration"]["reg_no"],
                b.json()["registration"]["reg_no"],
            }

    def test_self_register_lock_does_not_overwrite_manual(self, admin, anon):
        camp_id = _camp(admin, "owself")
        day = _day(admin, camp_id, TODAY_IST)
        typed = _reg(admin, day["id"], full_name=f"TEST Desk Manual {TAG}", age=41,
                     phone="9876500311", aadhaar_last4="8886", dob="1985-03-03",
                     manual_entry=True)
        assert typed.status_code == 200, typed.text
        orig = typed.json()["registration"]
        lock = _self(anon, day["id"], full_name=f"TEST Card Steal {TAG}", age=41,
                     gender="M", dob="1985-03-03", aadhaar_last4="8886",
                     aadhaar_scanned=True, phone="9876500312")
        assert lock.status_code == 409, lock.text
        assert lock.json()["detail"]["code"] == "DUPLICATE_IN_CAMP"
        assert lock.json()["detail"]["registration"]["reg_no"] == orig["reg_no"]
        listed = admin.get(f"{API}/patients", timeout=30).json()["patients"]
        row = next(p for p in listed if p["id"] == orig["id"])
        assert row["full_name"] == f"TEST Desk Manual {TAG}"
        assert row["aadhaar_scanned"] is False

    def test_lock_matching_none_creates_new(self, admin):
        camp_id = _camp(admin, "ownone")
        day = _day(admin, camp_id, TODAY_IST)
        typed = _reg(admin, day["id"], full_name=f"TEST Unrelated {TAG}", age=20,
                     phone="9876500309", manual_entry=True)
        assert typed.status_code == 200, typed.text
        lock = _reg(admin, day["id"], full_name=f"TEST Fresh Card {TAG}", age=21,
                    gender="M", dob="2005-05-05", aadhaar_last4="8885",
                    aadhaar_scanned=True, phone="9876500310")
        assert lock.status_code == 200, lock.text
        assert lock.json()["created"] is True
        assert lock.json()["registration"]["reg_no"] != typed.json()["registration"]["reg_no"]


class TestCampDayCapacity:
    def test_full_day_409_desk_and_self(self, admin, anon):
        camp_id = _camp(admin, "capfull")
        day = _day(admin, camp_id, TODAY_IST, seat_limit=1)
        a = _reg(admin, day["id"], full_name=f"TEST Cap1 {TAG}", phone="9876500401",
                 manual_entry=True)
        assert a.status_code == 200, a.text
        b = _reg(admin, day["id"], full_name=f"TEST Cap2 {TAG}", phone="9876500402",
                 manual_entry=True)
        assert b.status_code == 409, b.text
        assert b.json()["detail"]["code"] == "CAMP_DAY_FULL"
        s = _self(anon, day["id"], full_name=f"TEST CapSelf {TAG}", age=30, gender="M",
                  dob="1996-03-03", aadhaar_last4="4401", aadhaar_scanned=True)
        assert s.status_code == 409, s.text
        assert s.json()["detail"]["code"] == "CAMP_DAY_FULL"

    def test_limit_zero_is_unlimited(self, admin):
        camp_id = _camp(admin, "capzero")
        day = _day(admin, camp_id, TODAY_IST, seat_limit=0)
        a = _reg(admin, day["id"], full_name=f"TEST Unlim A {TAG}", phone="9876500403",
                 manual_entry=True)
        b = _reg(admin, day["id"], full_name=f"TEST Unlim B {TAG}", phone="9876500404",
                 manual_entry=True)
        assert a.status_code == 200, a.text
        assert b.status_code == 200, b.text


class TestPublicOccupancy:
    def test_counts_remaining_and_no_phi(self, admin, anon):
        camp_id = _camp(admin, "occ")
        limited = _day(admin, camp_id, FUTURE, seat_limit=10)
        unlim = _day(admin, camp_id, PAST, seat_limit=0)
        secret_name = f"TEST SecretPhi {TAG}"
        r = _reg(admin, limited["id"], full_name=secret_name, age=77,
                 phone="9876500501", aadhaar_last4="5050", manual_entry=True)
        assert r.status_code == 200, r.text
        pub = anon.get(f"{API}/camps/active/public", timeout=30)
        assert pub.status_code == 200, pub.text
        body = pub.json()
        assert body["camp"]["id"] == camp_id
        lim_row = next(d for d in body["days"] if d["id"] == limited["id"])
        un_row = next(d for d in body["days"] if d["id"] == unlim["id"])
        assert lim_row["registered"] == 1
        assert lim_row["seat_limit"] == 10
        assert lim_row["remaining"] == 9
        assert un_row["registered"] == 0
        assert un_row["seat_limit"] == 0
        assert un_row["remaining"] == "unlimited"
        blob = pub.text.lower()
        assert secret_name.lower() not in blob
        assert "9876500501" not in blob
        assert "5050" not in blob
        assert "aadhaar_last4" not in blob
        assert "phone" not in blob or "phone" not in str(lim_row)

    def test_inactive_camps_not_listed(self, admin, anon):
        live = _camp(admin, "occlive")
        _day(admin, live, TODAY_IST, seat_limit=3)
        dead = admin.post(f"{API}/camps", json={
            "name": f"TEST_SF_dead_{TAG}", "venue": "Hidden Hall", "camp_date": TODAY_IST,
        }, timeout=30).json()["camp"]
        pub = anon.get(f"{API}/camps/active/public", timeout=30).json()
        assert pub["camp"]["id"] == live
        assert pub["camp"]["name"] != dead["name"]
        assert dead["id"] != pub["camp"]["id"]


class TestSelfRegisterLockRequired:
    def test_self_register_without_lock_400(self, admin, anon):
        camp_id = _camp(admin, "selflock")
        day = _day(admin, camp_id, TODAY_IST)
        r = _self(anon, day["id"], full_name=f"TEST NoLock {TAG}", age=30,
                  aadhaar_scanned=False, phone="9876500601")
        assert r.status_code == 400, r.text


class TestSnpDefaultTemplate:
    def test_defaults_and_restore_carry_snp_header_logos_footer(self, admin):
        camp_id = _camp(admin, "tpl")
        g = admin.get(f"{API}/templates?camp_id={camp_id}", timeout=30)
        assert g.status_code == 200, g.text
        d = g.json()["defaults"]
        title = d["header_title"]
        sub = d["header_subtitle"]
        foot = d["footer_note"]
        assert "Sikar Nagarik Parishad" in title
        assert "Sikar Zilla Welfare Trust" in title
        assert "सीकर" in title
        assert "Sikar Bhawan" in sub or "SIKAR BHAWAN" in sub.upper()
        assert "sikarkolkata@gmail.com" in sub.lower()
        assert "Rupa" in foot
        assert len(d["logos"]) >= 2
        assert all(lg.get("data_url", "").startswith("data:image/") for lg in d["logos"])

        admin.post(f"{API}/templates/draft", json={
            "camp_id": camp_id,
            "header_title": "TEST Published Keep",
            "header_subtitle": "keep sub",
            "footer_note": "keep foot",
            "blocks": [{"id": "identity", "label": "I", "type": "identity", "visible": True, "height": 0}],
            "logos": [],
        }, timeout=30)
        pub = admin.post(f"{API}/templates/publish", json={"camp_id": camp_id}, timeout=30)
        assert pub.status_code == 200, pub.text
        published_version = pub.json()["published"]["version"]
        published_title = pub.json()["published"]["header_title"]

        rest = admin.post(f"{API}/templates/restore-defaults", json={"camp_id": camp_id}, timeout=30)
        assert rest.status_code == 200, rest.text
        draft = rest.json()["draft"]
        assert "Sikar Nagarik Parishad" in draft["header_title"]
        assert "Rupa" in draft["footer_note"]
        assert len(draft["logos"]) >= 2

        after = admin.get(f"{API}/templates?camp_id={camp_id}", timeout=30).json()
        assert after["published"]["version"] == published_version
        assert after["published"]["header_title"] == published_title


def test_zz_leave_active_camp_with_today(admin):
    camp_id = _camp(admin, "leave")
    _day(admin, camp_id, TODAY_IST, seat_limit=50)
