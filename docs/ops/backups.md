# Backups

Production compose runs two services against the `backups` volume.

- `backup` dumps MongoDB every `BACKUP_INTERVAL_SECONDS` (default 3600) into `/backups/${DB_NAME}-<UTC timestamp>.archive.gz` and deletes dumps older than `BACKUP_KEEP_DAYS` (default 14) days.
- `backup-sync` copies those dumps off the box with `rclone copy` to `BACKUP_REMOTE`. It never uses `sync`, so pruning on the box does not delete off-box copies. Files younger than 60 seconds are skipped so a dump still being written is not copied.

During camp, keep the interval at 3600 so a failure loses at most an hour. To change it, set `BACKUP_INTERVAL_SECONDS` in `.env` and recreate the services.

`BACKUP_REMOTE` is required. Compose refuses to start when it is unset. Copy `backup.env.example` to `backup.env` (gitignored) and fill the five `RCLONE_CONFIG_OFFBOX_*` keys for the S3-compatible bucket. The remote name those variables define is `offbox`; a typical value is `BACKUP_REMOTE=offbox:snp-backups`.

## Restore drill

Run this once before camp. Record the date at the bottom of this file.

List dumps:

```sh
docker compose -f docker-compose.prod.yml exec backup ls -1 /backups
```

Restore one dump into a side database (replace `<file>` and `<DB_NAME>`):

```sh
docker compose -f docker-compose.prod.yml exec backup mongorestore --uri mongodb://mongo:27017 --gzip --archive=/backups/<file> --nsFrom "<DB_NAME>.*" --nsTo "<DB_NAME>_drill.*"
```

Verify the `patients` count in the side database:

```sh
docker compose -f docker-compose.prod.yml exec mongo mongosh --quiet --eval 'db.getSiblingDB("<DB_NAME>_drill").patients.countDocuments()'
```

Drop the side database:

```sh
docker compose -f docker-compose.prod.yml exec mongo mongosh --quiet --eval 'db.getSiblingDB("<DB_NAME>_drill").dropDatabase()'
```

## Drill log

- Date last run:
