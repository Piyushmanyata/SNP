#!/bin/sh
set -u

while true; do
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  if mongodump --uri "mongodb://snp_backup:${MONGO_BACKUP_PASSWORD}@mongo:27017/?authSource=admin&replicaSet=rs0" --db "$DB_NAME" --gzip --archive="/backups/${DB_NAME}-${ts}.partial"; then
    mv "/backups/${DB_NAME}-${ts}.partial" "/backups/${DB_NAME}-${ts}.archive.gz"
    find /backups -name "${DB_NAME}-*.archive.gz" -mmin +$((BACKUP_KEEP_DAYS * 1440)) -delete
  else
    rm -f "/backups/${DB_NAME}-${ts}.partial"
    echo "mongodump failed at ${ts}" >&2
  fi
  sleep "$BACKUP_INTERVAL_SECONDS"
done
