# Backend address recovery

## Context

Docker can assign a new IP address when replacing the backend container. Resolving `backend` only when nginx starts leaves the frontend sending API requests to the old address indefinitely. The previous configuration failed a live address-change regression.

## Decision

Use nginx's shared upstream with `resolve` and Docker's internal DNS resolver, refreshing addresses every five seconds, instead of requiring a frontend restart after each backend replacement. Both ordinary API requests and logo uploads use this upstream. Paths, request bodies, forwarding headers and response cache rules remain intact.

The [nginx upstream documentation](https://nginx.org/en/docs/http/ngx_http_upstream_module.html#server) defines dynamic resolution and the shared-memory requirement. This feature requires nginx 1.27.3 or later; the verified production image runs nginx 1.30.4.

## Consequence and verification

A brief API outage remains possible during backend replacement and DNS refresh. An otherwise healthy frontend recovers automatically. The resolver address is specific to Docker's user-defined networks used by both Compose stacks.

Start a disposable project from the repository root with `APP_PORT=3101`, `DB_NAME=snp_final_review` and `docker compose --env-file .env.example -p snp-final-review up -d --build --wait`. Then run `python frontend/scripts/verify-proxy-recovery.py`. This test changes only that project's backend network address, requires API recovery within 15 seconds without restarting the frontend, and restores the original address in cleanup. Do not run other integration tests against that project at the same time. Remove it afterward with `docker compose --env-file .env.example -p snp-final-review down -v`.
