# ADR 0067: Board counts stay in the database, and the camp export streams

Issue #50, slice S9 (stories 22–25, 69).

## Context

- The camp-day transcription backlog was seen patients minus any transcription document. A printed patient waiting for a prescription was missing, and a seen patient was counted before paper was in hand.
- The board and Admin SMS Health loaded every ledger row for the day into Python. At 15,000 patients that is about 60,000 rows, and every lead polls the board every 15 seconds.
- `/kpis` with no camp returned `pre_registered` instead of `pending`.
- The leaderboard field `arrivals` was the completed-prescription count, and the screen labelled it "arrivals". The same count was also returned as `doctor_seen` and `points`.
- Arrival windows could be misread if a laptop clock built "last 15 minutes".
- Camp-records export loaded every patient, transcription and fulfilment, then one CSV string. A large camp could omit rows past an in-memory cap and grow server memory with the camp.

## Decision

- Transcription backlog is today's arrived patients with paper in hand (`printed_at`) and no completed prescription (`committed_revision_id`).
- New `reminder_ledger` rows store `camp_id`. The board and SMS Health each run one `$group` on camp (board only), event date, message type and status. They do not `find` ledger rows.
- `/kpis` always returns `active_camp`, `registered`, `seen` and `pending`.
- The leaderboard returns `completed` for that prescription count. The screen says "completed prescriptions".
- `last_15m` and `last_60m` are counted with the server clock. The board shows `Updated hh:mm:ss` from `server_time`.
- Camp-records export yields the header, then batches of 200 patients.

## Consequences

- A draft transcription with no committed revision stays in the backlog.
- SMS Health "today" is still messages created in the IST day, summed across camps. The board total is the active camp only.
- Delivery-report failures on a sent row still count as board failures, via the same aggregation.

## Rejected alternatives

- **Keep loading ledger rows and counting in Python.** The board is polled too often for that to stay timely.
- **Cap the export and tell the admin to filter.** Story 24 requires every row.
