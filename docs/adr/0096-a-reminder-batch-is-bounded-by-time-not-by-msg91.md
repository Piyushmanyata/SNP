# ADR 0096: A reminder batch is bounded by time, not by MSG91

## Context

- The reminder worker posts one batch and waits at most 120 seconds for the reply. The batch holds a 90-second lease (#89 slice 7, research note `sms-volume-msg91`).
- MSG91 was called through `asyncio.to_thread` with a 20-second socket timeout, four at a time, and the 60-second sweep budget was checked only between pages. A hung MSG91 could therefore stretch one batch of 200 far past the lease: a second worker call would take the lease and start while the first was still sending.
- The hung calls also sat in the default thread pool, which the door's Aadhaar decode shares. The 10:00 reminder slot runs during the camp.

## Decision

- **Each provider call is bounded.** `sms._submit` runs `_provider.send` on its own eight-thread pool. It waits at most `SEND_SECONDS` (10) for a free thread, then at most `SEND_SECONDS` for the answer, so time spent queued never eats the provider's answer time. MSG91's socket timeout drops to 8 seconds, and because a socket timeout bounds each read rather than the whole reply, `msg91.send` also shuts its socket down 8 seconds after it starts: a reply that trickles in byte by byte cannot hold an SMS thread. MSG91's own timeout keeps its own message.
- **The batch stops starting sends when its time is spent.** A send whose turn comes after the 60-second budget is deferred, not attempted. The call returns `complete: false`, the cursor stays on the first deferred patient, and the worker calls again at once, as before. With four sends at a time and eight threads, a send started just before the budget waits for a thread only while earlier sends time out, so the worst case is about 60 + 20 seconds plus database work: inside the 90-second lease and the 120-second worker timeout.
- **A timed-out send is never guessed at.**
  - If the call had reached the provider when time ran out, the intent is settled `uncertain` and never sent again (ADR 0087's ledger rule).
  - If it was still waiting for a free SMS thread, it is withdrawn under a lock before it can start, settled `failed` and retried on a later run.
- `complete` is now derived in one place: true only when every reminder type's cursor is done and nothing is waiting. A batch that ran out of time on its last type used to report `complete: true`.
- The test recorder gains a scripted `hang` outcome, released when the test ends.

## Rejected alternatives

- **Cancelling the hung HTTP call.** A thread cannot be cancelled. Bounding it and freeing the event loop is the most Python offers without replacing `http.client`.
- **An async HTTP client for MSG91.** It is a new dependency, and the timeout and uncertainty rules would be the same.
- **Re-sending timed-out sends.** A timeout after the request left does not say whether MSG91 accepted it; re-sending risks a second SMS and a second charge.

## Consequences

- When MSG91 hangs, a batch takes several calls, and some reminders end `uncertain`. SMS Health counts them and Patients to phone covers anyone who needs a call.
- The Aadhaar decode never waits behind a hung SMS call.
