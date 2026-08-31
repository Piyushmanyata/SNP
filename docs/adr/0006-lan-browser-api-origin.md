# ADR 0006: Browser-derived API origin for LAN devices

## Context

The CRA bundle baked `REACT_APP_BACKEND_URL=http://localhost:8000`. Phones on the same LAN loaded the UI at `http://<PC-IP>:3000` but API calls went to the phone's own localhost. Backend CORS also listed only `localhost`/`127.0.0.1` origins, so even a corrected API host would be blocked.

## Decision

- If the page host is not loopback and the configured backend URL is missing or loopback, call `{window.location.protocol}//{window.location.hostname}:8000`.
- Keep `REACT_APP_BACKEND_URL` for localhost and for production hosts that are not loopback.
- Allow CORS for RFC1918 + loopback frontend origins via `allow_origin_regex`, in addition to `CORS_ORIGINS`.
- `cors_origin_list` drops `*` so credentialed cookies never pair with a wildcard origin. Unset `CORS_ORIGINS` means LAN/loopback only.

## Consequences

`http://localhost:3000` and `http://<LAN-IP>:3000` both reach the backend on port 8000 of that same host. The PC IP is not hardcoded.

## Rejected alternatives

- Reverse proxy / same-origin `/api` — rejected in ADR 0001 for local Docker.
- Hardcoding the current PC LAN IP in env — the address changes.
- `CORS_ORIGINS=*` as the Docker default — broader than needed; credentials + explicit/LAN origins are enough.
