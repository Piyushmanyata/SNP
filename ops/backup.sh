#!/bin/sh
set -u

while true; do
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  if ! mongodump --uri mongodb://mongo:27017 --db "$DB_NAME" --gzip --archive="/backups/${DB_NAME}-${ts}.archive.gz"; then
    echo "mongodump failed at ${ts}" >&2
  fi
  find /backups -name "${DB_NAME}-*.archive.gz" -mmin +$((BACKUP_KEEP_DAYS * 1440)) -delete
  sleep "$BACKUP_INTERVAL_SECONDS"
done
