# ADR 0081: Backups run once a day

## Context

ADR 0062 took a snapshot every hour and kept 48 hourly snapshots. The owner asked for daily backups, and the production server already overrode the interval to 86400 seconds. The Compose fallback, the example environment and the Ops status fallback still assumed an hour.

## Decision

`BACKUP_INTERVAL_SECONDS` defaults to 86400 in `ops/backup/backup.sh`, `docker-compose.prod.yml` and `.env.production.example`. A failed pass is retried an hour later rather than a day later. Retention keeps 30 daily and 12 monthly snapshots; the hourly tier is dropped. The Ops status card falls back to a one-day interval when the backup record has none.

Keeping hourly snapshots and hiding them from the card was rejected: it costs disk and restic time for copies the owner does not want.

## Consequences

Up to a day of registrations can be lost if the disk fails between snapshots. A backup is still taken whenever the backup container starts, so run one before a risky deploy by restarting it. The Ops card turns amber after two missed days and red after three.
