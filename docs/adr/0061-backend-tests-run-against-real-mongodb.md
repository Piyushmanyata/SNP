# ADR 0061: Backend tests run against a real MongoDB database per test

## Context

- 374 of about 517 non-HTTP backend tests ran against `MockDB`, a hand-written imitation of MongoDB with its own `$group`, `$expr` and update semantics. A passing test proved the imitation, not MongoDB. An incorrect Camp-day board count stayed green this way.
- Unique indexes, partial filters, TTL indexes, `$expr` and transactions were never exercised in-process.
- About 115 hard-coded dates in tests would turn the suite red as the calendar passed them.
- `conftest.py` replaced `routes_registration.desk_register` globally, so no test could prove the real Manual entry rule.

## Decision

- `conftest.run_db(body, listener=None)` opens an `AsyncMongoClient` on `SNP_TEST_MONGO_URL` (default: the `rs0` replica set on `127.0.0.1:27017`), creates a `snp_t_<uuid8>` database, runs `db.init_indexes()`, runs the test body, then drops the database. Route modules read `db.get_db()`, so no module is patched.
- Query-count bounds use `conftest.CommandLog`, a `pymongo.monitoring.CommandListener` on the test client.
- `conftest.freeze_clock(monkeypatch)` fixes `now_utc` and `now_ist` in every backend module at 05-10-2026 09:00 IST; `today_ist_str` follows. In-process tests derive dates from it. `security` keeps the real clock, because PyJWT checks token expiry against the real clock.
- In-process HTTP tests share `seed.asgi_client()` and `seed.bearer()`; `conftest` sets the test `JWT_SECRET` once.
- Races are forced into a fixed order with barriers. Failure injection patches the driver's `AsyncCollection` method for one named collection.
- In-process HTTP tests use `httpx.ASGITransport`, because `TestClient` runs a second event loop that cannot share the async client.
- Shared fixtures live in `backend/tests/seed.py`. Unscanned fixtures send an explicit Manual entry reason.
- CI runs the tests against the same replica set that serves the live API, and runs daily at 06:00 IST.

## Rejected alternatives

- **Keep `MockDB`, or use `mongomock`.** Both imitate MongoDB; neither runs transactions or enforces the real index and aggregation behaviour.
- **One shared test database cleaned between tests.** A leftover document from one test can change another's result; a fresh database per test cannot.

## Consequences

- The in-process suite needs a running replica set; `docker-compose.ci.yml` publishes it.
- A query that only works in the imitation, or relies on insertion order without a sort, now fails.
