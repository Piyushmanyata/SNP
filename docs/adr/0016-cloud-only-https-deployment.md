# ADR 0016: Cloud-only deployment over HTTPS

Amends ADR 0006. The browser-derived API origin and the RFC1918 CORS regex stay for local development; they are no longer the production path.

## Context

`docker-compose.yml` is a development stack: the CRA dev server, uvicorn with reload, bind mounts, plain HTTP, and a default admin password. ADR 0006 made phones on a LAN reach the backend at `http://<host-IP>:8000`, which is correct for development.

It cannot be the camp-day path. `getUserMedia` requires a secure context, and Chrome treats only loopback as secure. Over `http://<LAN-IP>` the desk camera will not start on Android at all, so Live scan — the primary capture route — is unavailable on exactly the deployment shape it was reached through. Trusting a certificate on a hundred volunteer phones is not workable, and split-horizon DNS for a venue LAN is not something the trust can operate.

Load is not the constraint. A hundred staff at roughly one action every fifteen seconds is about seven requests per second. An Aadhaar Decode is an RSA-2048 verification and an inflate, five to fifteen milliseconds of CPU. Fifteen thousand patients with their transcriptions and fulfilments is well under a gigabyte of working set.

## Decision

- One cloud VPS, Hostinger KVM 4, running the whole stack.
- A real domain, with a reverse proxy terminating TLS and renewing certificates automatically. HTTPS is a prerequisite for Live scan, not a hardening step.
- A separate production compose: built frontend served as static files, uvicorn without reload, no bind mounts, secrets from the environment, no default admin password.
- Venue connectivity is handled operationally with a mobile router and a second SIM, not in the application.

## Consequences

One environment and one database, so there is no synchronisation code to write or debug. Live scan works on volunteer phones. Venue internet is a single point of failure for camp-day registration, and that is accepted and mitigated operationally.

KVM 4 is roughly ten times the capacity the measured workload needs. KVM 2 would serve; the margin is bought so that Mongo, the backend, the proxy, and a nightly backup coexist without tuning. KVM 8 is not justified by any figure above.

## Rejected alternatives

- An on-site box at the venue syncing to cloud afterwards — immune to venue internet, but requires solving LAN TLS, writing bidirectional sync, and it still needs internet for SMS. It adds the most code of any option.
- Cloud primary with an on-site read-only mirror — protects lookup and printing during an outage while registration stops anyway, and still requires LAN TLS plus a second deployment to maintain.
