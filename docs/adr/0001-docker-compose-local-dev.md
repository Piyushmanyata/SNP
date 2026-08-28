# ADR 0001: Docker Compose for local development

## Context

The SNP Camps stack is React (CRA), FastAPI, and MongoDB. Contributors on Windows need a single command to run the whole app without installing Python, Node, or MongoDB on the host.

## Decision

Ship a root `docker-compose.yml` with three services: `mongo`, `backend`, `frontend`.

- MongoDB uses a named volume `mongo_data` and is not published to the host.
- Backend connects with `MONGO_URL=mongodb://mongo:27017` and database `snp_camps`.
- Frontend `REACT_APP_BACKEND_URL` defaults to `http://localhost:8000` for the browser. LAN devices rewrite loopback API hosts to `window.location.hostname:8000` (ADR 0006).
- Source trees are bind-mounted; uvicorn `--reload` and CRA `npm start` provide hot reload.
- Local HTTP cookies use `COOKIE_SECURE=false` and `COOKIE_SAMESITE=lax`. Production defaults stay `secure=true` / `samesite=none`.

## Consequences

`docker compose up --build` starts the stack on `:3000` and `:8000`. Mongo data survives `docker compose down`. Production/Emergent deploy is unchanged.

## Rejected alternatives

- Install MongoDB, Python, and Node on the Windows host — more moving parts than Docker Desktop, which is already installed.
- Publish MongoDB on `localhost:27017` — unnecessary for the app; backend reaches it on the compose network.
- Multi-stage production images, reverse proxies, or cloud databases — out of scope for local development.
