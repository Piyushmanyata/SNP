# Deploy

The camp runs from Docker Compose on the Hostinger KVM. Caddy serves one HTTPS origin. MongoDB, the API, reminders and backups stay on the internal network. Do not run `docker compose down -v` on the production project. That deletes the database volumes.

## First deploy

1. Point the domain at the VPS and open TCP 80 and 443.
2. Copy `.env.production.example` to `.env.production`. Set the domain, TLS email, a 6-digit `ADMIN_BOOTSTRAP_PIN` that is not one digit repeated or a straight run, and independent random values for `JWT_SECRET`, `AADHAAR_HASH_PEPPER`, `CRON_SECRET`, `MONGO_PASSWORD`, `MONGO_APP_PASSWORD`, `MONGO_BACKUP_PASSWORD` and `RESTIC_PASSWORD`. Keep a copy of `RESTIC_PASSWORD` off the VPS.
3. From the release directory:

```sh
docker compose --env-file .env.production -f docker-compose.prod.yml config --quiet
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build --wait
```

4. Sign in as `admin` with the bootstrap PIN and choose a new PIN. Create the camp only after that.
5. Put the MSG91 key and the approved template ids in `.env.production` before any real SMS. Without them, sends are skipped.

## Update

```sh
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build --wait
```

This rebuilds images and recreates containers. It does not remove volumes.

## Rollback

Check out the previous release, then run the same update command. The database is not rolled back with the code. Restore a snapshot only from [backups](backups.md), after a drill of that snapshot prints `DRILL OK`.

## Wipe a test database

This destroys every camp, patient and backup snapshot stored on the VPS volumes. Do it only when the operator has said the data is disposable, and only after a copy of anything worth keeping is off the machine.

```sh
docker compose --env-file .env.production -f docker-compose.prod.yml down
docker volume rm snp_mongo_data snp_mongo_config
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build --wait
```

The volume names follow the Compose project. Confirm them with `docker volume ls` before removing any. The next start creates a new admin from `ADMIN_BOOTSTRAP_PIN`.
