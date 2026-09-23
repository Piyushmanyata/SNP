# Backups

Production compose runs one `backup` service against the `backups` volume. It dumps MongoDB every `BACKUP_INTERVAL_SECONDS` (default 3600) into `/backups/${DB_NAME}-<UTC timestamp>.archive.gz` and deletes dumps older than `BACKUP_KEEP_DAYS` (default 14) days. A failed dump leaves earlier dumps in place.

During camp, keep the interval at 3600 so a failure loses at most an hour. To change it, set `BACKUP_INTERVAL_SECONDS` in `.env.production` and recreate the service.

Dumps stay on the box; a backup on the same disk is not disaster recovery. Copy them off yourself, with your provider's backup tool or by exporting the directory and uploading it:

```sh
docker compose --env-file .env.production -f docker-compose.prod.yml cp backup:/backups ./backup-export
```

## Restore drill

Run this once before camp. Record the date at the bottom of this file.

List dumps:

```sh
docker compose --env-file .env.production -f docker-compose.prod.yml exec backup ls -1 /backups
```

Restore one dump into a side database (replace `<file>`). The backup container already holds `MONGO_PASSWORD` and `DB_NAME`, and authenticates as `snp` like `ops/backup.sh`:

```sh
docker compose --env-file .env.production -f docker-compose.prod.yml exec backup sh -c 'mongorestore --host mongo --username snp --password "$MONGO_PASSWORD" --authenticationDatabase admin --gzip --archive=/backups/<file> --nsFrom "$DB_NAME.*" --nsTo "${DB_NAME}_drill.*"'
```

Verify the `patients` count in the side database:

```sh
docker compose --env-file .env.production -f docker-compose.prod.yml exec backup sh -c 'mongosh --host mongo --username snp --password "$MONGO_PASSWORD" --authenticationDatabase admin --quiet --eval "db.getSiblingDB(\"${DB_NAME}_drill\").patients.countDocuments()"'
```

Drop the side database:

```sh
docker compose --env-file .env.production -f docker-compose.prod.yml exec backup sh -c 'mongosh --host mongo --username snp --password "$MONGO_PASSWORD" --authenticationDatabase admin --quiet --eval "db.getSiblingDB(\"${DB_NAME}_drill\").dropDatabase()"'
```

## Drill log

- Date last run:
