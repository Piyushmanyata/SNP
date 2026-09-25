# Backups

The `backup` service in `docker-compose.prod.yml` runs `ops/backup/backup.sh` every `BACKUP_INTERVAL_SECONDS` (default 86400, once a day); a failed pass is retried after an hour. Each pass:

1. Counts patients, then runs `mongodump --oplog --gzip --archive` as the `snp_backup` user and streams it into restic (`--stdin-from-command`). The oplog makes the dump one point in time even while desks are writing. If the dump fails, restic saves nothing, so the newest snapshot is always a complete one.
2. Stores the archive in the encrypted local repository `/backups/restic`, tagged `snp` and `patients=<count when the dump started>`.
3. Copies every snapshot the off-site repository lacks, if `RESTIC_REMOTE_REPOSITORY` is set.
4. Once a day, keeps 30 daily and 12 monthly snapshots in each repository and prunes the rest.
5. Writes its Ops status (`ops_status`, `_id: "backup"`): last success, last off-site copy, last error message, size and patient count.

The admin overview's System card reads that status. It is red when no backup has succeeded for 6 hours (or three intervals, if longer). It is amber when the last one is more than two intervals old, the off-site copy is missing or stale, or the last pass reported an error. A red System card also shows "Backups failing — tell the admin" on the Camp-day board.

## Set up

In `.env.production`:

- `RESTIC_PASSWORD`: `openssl rand -hex 32`. It encrypts every backup. Keep a copy off the VPS (a password manager); without it no backup can be restored.
- `RESTIC_REMOTE_REPOSITORY`: an S3-compatible bucket, `s3:https://<endpoint>/<bucket>/snp`. For Backblaze B2 the endpoint is `s3.<region>.backblazeb2.com`; restic recommends B2's S3 API over its native one.
- `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`: an access key limited to that bucket.

Then rebuild the service:

```sh
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build backup backend
```

The first pass creates both repositories.

### A deployment made before these backups

`init-users.js` only runs on an empty data volume. On a deployment created earlier, give `snp_backup` its Ops status role and take away `restore`, which it no longer needs, once, as the root user:

```sh
docker compose --env-file .env.production -f docker-compose.prod.yml exec mongo sh -c 'mongosh -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --quiet --eval "
  const admin = db.getSiblingDB(\"admin\");
  admin.createRole({role: \"snpOpsStatusWriter\", privileges: [{resource: {db: process.env.DB_NAME, collection: \"ops_status\"}, actions: [\"find\", \"insert\", \"update\"]}], roles: []});
  admin.grantRolesToUser(\"snp_backup\", [\"snpOpsStatusWriter\"]);
  admin.revokeRolesFromUser(\"snp_backup\", [\"restore\"]);"'
```

The old plain archives (`/backups/<DB_NAME>-*.archive.gz`) are no longer written or pruned. Delete them after the first drill passes.

## Check

- The System card on the admin overview is green.
- `docker compose --env-file .env.production -f docker-compose.prod.yml exec backup restic snapshots` lists the daily snapshots.
- `docker compose --env-file .env.production -f docker-compose.prod.yml logs backup` shows no `backup:` errors.

## Restore drill

Run it before every camp, and record the date and result below. It needs no access to the production database:

```sh
docker compose --env-file .env.production -f docker-compose.prod.yml exec backup restore-drill.sh
```

The drill starts a throwaway `mongod` inside the backup container, restores the newest snapshot into it with `--oplogReplay`, and checks:

- at least as many patients as the snapshot's `patients=` tag;
- every fulfilment with a `slip_id` points at an existing Deferred slip;
- every OT Schedule Day's `seats_taken` equals its deferred OT fulfilments.

It prints `DRILL OK` or `DRILL FAILED: <first failing check>`, then deletes the throwaway database. To prove the off-site copy, run the same drill against it:

```sh
docker compose --env-file .env.production -f docker-compose.prod.yml exec backup sh -c 'RESTIC_REPOSITORY="$RESTIC_REMOTE_REPOSITORY" restore-drill.sh'
```

## Restore to production

This replaces the live database. Do it only after a drill of the same snapshot passes.

1. Stop the writers and the backup loop, so no snapshot captures a half-restored database: `docker compose --env-file .env.production -f docker-compose.prod.yml stop backend reminders backup`.
2. Pick a snapshot: `docker compose --env-file .env.production -f docker-compose.prod.yml run --rm backup restic snapshots` (or use `latest`).
3. Restore it as the root user. `--oplogReplay` needs root; `snp_backup` cannot write to the database.

   ```sh
   set -a; . ./.env.production; set +a
   docker compose --env-file .env.production -f docker-compose.prod.yml run --rm -e MONGO_PASSWORD backup bash -c \
     'restic dump <snapshot> snp.archive.gz | mongorestore --uri "mongodb://snp:$MONGO_PASSWORD@mongo:27017/?authSource=admin&replicaSet=rs0" --gzip --archive --drop --oplogReplay'
   ```

4. Start again: `docker compose --env-file .env.production -f docker-compose.prod.yml up -d --wait`.

If the VPS is lost, deploy on a new one with the same `RESTIC_PASSWORD`, `RESTIC_REMOTE_REPOSITORY` and provider keys, and in step 3 add `-e RESTIC_REPOSITORY="$RESTIC_REMOTE_REPOSITORY"` to restore from the off-site copy.

## Drill log

- Date last run:
