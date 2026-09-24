# ADR 0060: MongoDB runs as a one-node replica set, services get their own users, and PyMongo Async replaces Motor

## Context

- A standalone `mongod` cannot take a point-in-time backup while the camp is writing: `mongodump --oplog` needs a replica set. Without it, a backup taken mid-request can hold a Token without its booking.
- Multi-document transactions also need a replica set. Clinical writes that touch a seat, a slip, a fulfilment and an operation record today rely on hand-written compensation.
- Every service used the MongoDB root account. A compromised API or backup container therefore had root control of the database.
- Motor, the async driver, reached end of life on 14 May 2026 and receives only critical fixes until 14 May 2027. PyMongo 4.x ships its own asyncio client, which avoids Motor's thread pool.

## Decision

- MongoDB runs as the single-node replica set `rs0` in every environment. The Compose healthcheck initiates the set once and reports healthy only when the node is PRIMARY. Production adds a key file, created on first start in the `mongo_config` volume, and authentication.
- `ops/mongo/init-users.js` runs on an empty data directory and creates `snp_app` (`readWrite` on `DB_NAME`) for the API and `snp_backup` (`backup` and `restore` on `admin`) for the backup service. The root user is for the operator only; no service receives its password.
- The backend uses `pymongo==4.18.1` `AsyncMongoClient`. `db.get_client()` exposes the client for sessions. `aggregate()` is awaited before its cursor, through `db.aggregate_list`.
- Uvicorn keeps **one** worker. The self-registration and extract rate limiters live in process memory, and bcrypt already runs in a thread.
- Every request gets a 12-character `request_id`, returned as `X-Request-ID` and logged in one JSON line with the route template, status and duration; requests over one second log a warning. An unhandled error returns `500 {"code": "INTERNAL", "request_id": …}` and logs the exception type and stack only, never its message, the body, names, phone numbers or Aadhaar data.
- Compose health uses `/api/health/ready`, which fails when MongoDB is unreachable. `/api/health` stays as liveness.
- The start-up migrations for data created before the current schema are deleted; `init_indexes` is a flat list of index definitions.

## Rejected alternatives

- **Filesystem snapshots for consistent backups.** The Hostinger KVM cannot schedule per-volume snapshots, and a snapshot is only consistent if the journal and data share one volume.
- **Staying on Motor.** It is end of life and wraps PyMongo in a thread pool that the native async client no longer needs.
- **More uvicorn workers.** They would split the in-memory rate limiters and let one client multiply its limit.

## Consequences

- Moving an existing deployment needs a fresh data volume (the init script runs only on an empty directory) and two new secrets, `MONGO_APP_PASSWORD` and `MONGO_BACKUP_PASSWORD`.
- Tests and CI reach the replica set on `127.0.0.1:27017` with `directConnection=true`, through `docker-compose.ci.yml`.
- `listDatabases` from the API account lists only `DB_NAME`; asking for every database is refused.
