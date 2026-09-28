# ADR 0094: The camp bridges outages with a second network, and the queue waits

**ADR 0016 (cloud-only) stands.**

## Context

- At the 15,000-patient camp, 37 desks depend on one venue internet link (#77, #89 slice 5).
- Nothing detected offline. A desk kept retrying blindly, the staff sign-in occupancy kept showing old numbers as live, and a lost draft-save reply said "another operator saved this prescription", sending the operator to look for someone who does not exist.
- The runbook told the camp to write arrivals on a paper register and enter them later.

## Decision

- **Connectivity, not an offline mode.** Each group of six desks has a 4G/5G hotspot on a carrier different from the venue link, plus two spares, and laptops fail over to it automatically. Failover is tested before the doors open.
- **If every link is down, the queue waits.** The door holds the queue, clinical desks pause, and nothing is written on paper for later entry.
- **One offline banner on every staff screen** (Desk, Clinical, Board, Admin, Team), in `Layout`: "No connection to the server. Hold the queue — nothing is lost. This clears by itself when the connection returns." It appears when the browser reports offline, a request fails with no response, or the proxy answers 502–504 without an API body (the app is down). It clears on the next answer from the API; while it shows, the page asks `/api/health` every 10 seconds so a screen that does not poll recovers too. It sits beside the per-action errors and blocks nothing.
- **No silent stale reads.** The sign-in occupancy says "Not updated since HH:MM" after a failed refresh.
- **Neutral conflict wording.** `DRAFT_VERSION_CONFLICT` keeps its code; its message is "This prescription changed since you opened it. Reload to see the saved version."

## Rejected alternatives

- **A paper register with later entry.** It loses the card Lock and the Paper check, and splits the records between paper and screen.
- **A local fallback server.** It overturns ADR 0016 and is too big for the time before the camp.

## Consequences

- The owner buys 9 hotspots (7 plus 2 spares) on a second carrier.
- A Paper check that failed during an outage is retried when the banner clears (ADR 0093 covers a Print window that closed meanwhile).
