# ADR 0062: Backups are oplog-consistent restic snapshots, copied off the VPS and drilled in a throwaway mongod

## Context

- `ops/backup.sh` dumped one database without `--oplog`, kept plain archives on the VPS disk, and reported failures only to its own log. Losing the VPS meant losing every patient record. A dump taken while desks were writing could hold a Token without its booking.
- `mongorestore` refuses `--oplogReplay` together with `--nsFrom`/`--nsTo` or `--nsInclude`. A consistent restore into a renamed side database on production is therefore impossible, and replaying the oplog on production needs `anyAction` on `anyResource`.
- Under concurrent writes, no count taken beside the dump equals the count the dump restores.

## Decision

- The `backup` image is `mongo:7` plus restic 0.19.1, verified against its published SHA-256.
- Each pass runs `restic backup --host snp --stdin-from-command -- mongodump --oplog --gzip --archive`. If `mongodump` fails, restic saves no snapshot. Each snapshot is tagged `snp` and `patients=<count before the dump>`. The fixed host keeps every snapshot in one retention group, even when Compose recreates the container under a new hostname.
- Snapshots are encrypted with `RESTIC_PASSWORD`. When `RESTIC_REMOTE_REPOSITORY` (an S3-compatible bucket, including Backblaze B2) is set, `restic copy` sends every missing snapshot off the VPS. Once a day, both repositories keep 48 hourly, 30 daily and 12 monthly snapshots and prune the rest.
- `backup.sh` writes the backup Ops status to `ops_status` (`_id: "backup"`). `snp_backup` holds only `backup` and `snpOpsStatusWriter`, which allows find, insert and update on that one collection. It loses `restore` (this amends ADR 0060). Restoring to production is an operator action done as root.
- `restore-drill.sh` starts a throwaway `mongod` on `127.0.0.1:27018` inside the backup container. It restores the newest snapshot there with `--oplogReplay` and checks three things: patients restored ≥ the `patients=` tag, every fulfilment `slip_id` resolves, and every OT day's `seats_taken` equals its deferred OT fulfilments. It then prints `DRILL OK` or the first failure. It reads only the repository, so it can drill the off-site copy too.
- `GET /api/admin/system` (admin) returns the backup Ops status, the free space on the backups volume (mounted read-only into the API), and a green/amber/red level for each:
  - **Backup:** red after 6 hours without success (or three intervals, if longer); amber after two intervals, with no fresh off-site copy, or when the last pass reported an error (a failed copy or prune).
  - **Disk:** amber under 20% free, red under 10%.
  - The worst level colours the System card. A red card sets `backups_failing` on the Camp-day board.

## Rejected alternatives

- **`mongodump | restic backup --stdin` with `pipefail`.** A dump that dies halfway still leaves a truncated snapshot as `latest`.
- **Restoring the drill into `${DB_NAME}_drill` on production.** `mongorestore` refuses the rename with `--oplogReplay`, and it would need `anyAction` and `dropDatabase` on production.
- **Patient count equal to a count stored beside the dump.** Writes during the dump make it differ. Patients are never deleted, so "at least the count before the dump" is exact without writes and safe with them.
- **`gpg` plus `rclone` plus a prune script.** That is three tools and three failure modes, where restic is one.

## Consequences

- `RESTIC_PASSWORD` is a new required secret. Losing it makes every backup unreadable.
- A deployment created before this change needs a one-time role grant (`docs/ops/backups.md`).
- The drill needs about 0.25 GB of cache and a temporary directory the size of the database inside the backup container.
