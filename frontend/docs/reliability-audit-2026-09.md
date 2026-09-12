# Frontend reliability audit — September 2026

## Verified failures and fixes

- A pending registration-number or patient-QR lookup left the previous patient's print action visible. New lookups now clear the old patient immediately.
- A pending or failed name search retained the previous search results. New name searches now clear previous patient, result-list and door-scan actions before requesting the next result.
- A search that superseded a pending scan left the scanner permanently busy because the stale scan could no longer clear its loading state. Both number lookups and name searches now release that state; two interleaving regressions cover the transition.
- Login occupancy polling issued overlapping requests when responses exceeded five seconds and continued while the page was hidden. Polling now permits one pending request, pauses while hidden and refreshes when the page becomes visible.
- An initial analytics request failure left the page displaying only “Loading analytics…”. The page now exposes the error through an alert and recovers on the next refresh.
- Prescription wizard navigation advanced before draft persistence completed. Navigation now waits for a successful save, preserves the current step after failure and supports retry. The existing busy state prevents patient and line changes during persistence.

Eight deterministic regression scenarios failed before their fixes. The affected page and wizard suites pass, and the modified JavaScript passes ESLint with zero warnings. Repository-wide checks are release gates owned by the integration workflow.

## Decision: serialize existing asynchronous operations

Context: out-of-order or incomplete requests must not expose actions for the wrong patient or imply that a draft has persisted.

Decision: retain the existing request-sequence guards, clear stale actionable state at the start of each search, allow one occupancy request at a time and await the existing draft-save callback. Use the existing visibility, error and busy-state patterns.

Rejected alternative: a shared request/cache manager would expand the affected surface without being necessary to reproduce or fix these failures.

Consequence: a slow draft save intentionally delays wizard navigation. Failed saves remain on the same step and show an actionable error; current form values remain in memory for retry. A hidden login page makes no scheduled occupancy requests.

## Prescription wizard callback contract

`Clinical.saveStep` resolves `true` after draft persistence and `false` after a failure, which it also displays. It owns the busy state for the duration of the request. `PrescriptionWizard` awaits that result before advancing; `false` retains the current step. The final prescription commit continues to own the mark-seen transition.

## Audit coverage and limits

The review covered asynchronous control flow in the Desk, Clinical, Login and Board pages, the prescription wizard, fulfilment submission and authentication loading. It also inspected helper boundaries for incremental static checking. It did not establish that every frontend path or hardware scanner behavior is defect-free; browser, device and production-load testing were outside this verification pass.

The redundant analytics status conditional was removed. No whole module was deleted without a proven absence of live callers.

An initial checked-JavaScript scope passes for `uuid`, `operatorLines`, role constants, `guideRoi`, `grabFrame` and `templateHelpers`. This is partial static coverage; React component prop inference and custom browser globals need explicit typing before the entire frontend can be checked.
