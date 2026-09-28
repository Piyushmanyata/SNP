# ADR 0095: The public self-register limits live in MongoDB

**Replaces the in-process limiter. The Household limit, the registration SMS cap and ADR 0043 (no UIDAI signature check) stand.**

## Context

- Self-registration and anonymous decode were limited to 30 and 60 requests per client address per 10 minutes, held in process memory (#89 slice 8, grilling #81).
- Mobile carrier NAT puts thousands of phones behind a few addresses. A pre-registration SMS blast would trip the per-address limit for honest households.
- A restart forgot every limit.
- Nothing limited one Household phone, and nothing capped how many self-registrations one camp takes in a day.

## Decision

- **Counters in MongoDB.** `limits.spend` increments a fixed-window counter in `rate_limits`. The document id is `scope:subject:window start`, and a TTL index on `expires_at` removes each counter when its window ends. The counters survive a restart and would hold across processes. `limits.used` and `limits.add` keep the per-camp daily count.
- **The limits** (named constants in `routes_registration.py`):
  - **per client address:** 120 self-registrations and 240 anonymous decodes per 10 minutes, up from 30 and 60, for carrier NAT;
  - **per Household phone:** 12 self-register attempts per hour, counted only when the phone is a valid number;
  - **per camp:** 6,000 self-registrations per IST day. This counts registrations actually created, so a flood of refused requests cannot use up the ceiling.
- Every refusal is the existing 429 `TOO_MANY_ATTEMPTS_PLEASE_TRY_AGAIN_LATER`. Staff decode is never limited.
- **Unchanged:** the Household limit of 6 patients per camp, the registration SMS cap of 6 a day, one uvicorn worker, and the client-address chain Caddy → nginx → uvicorn. The deploy runbook states the chain's one assumption: nginx is reachable only through Caddy.

## Rejected alternatives

- **UIDAI Secure QR signature verification.** ADR 0043 stands; it is revisited only if abuse appears.
- **Redis or a proxy-level limiter.** A new service for three counters the database already holds.
- **Keeping the in-process limiter with higher numbers.** A restart would still forget, and there would still be no per-phone or per-camp limit.

## Consequences

- Each self-registration costs three small counter writes and one read.
- A camp whose honest demand passes 6,000 self-registrations a day needs the constant raised.
