# Reliability verification and CI

Date: 2026-09-12

## Context

The previous serial workflow could report success when all HTTP tests skipped because the API URL or credentials were missing. Lint warnings did not fail the frontend job, static types were unchecked, and test reports disappeared with the runner. The active application is the React frontend and FastAPI/Motor backend; the retired root application is outside this release.

## Decision

Run frontend, backend, dependency and workflow checks independently, then require all four results to be successful in the existing `verify` check. Each job has a deadline. Checkout/setup/artifact actions use immutable commit references and the workflow token has read-only repository access. GitHub's [workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax) defines the permissions and dependency behavior; [artifacts](https://docs.github.com/en/actions/tutorials/store-and-share-data) retain test and coverage reports for fourteen days.

The frontend job installs the lockfile, checks JavaScript utilities, fails on lint warnings, runs the complete Jest suite with coverage, rejects skipped/todo tests, builds production assets and checks initial gzip budgets of 150,000 JavaScript bytes and 15,000 CSS bytes. The current entry is approximately 85,600 and 5,450 bytes respectively. These are transfer-size regression limits, not latency benchmarks.

The backend job installs pinned tooling, checks dependency compatibility, runs mypy over every production Python module with untyped function bodies included, checks compilation and fatal lint errors, validates production Compose/Caddy/nginx configuration, builds isolated production images and runs the entire backend suite against real HTTP and MongoDB. `SNP_REQUIRE_LIVE_TESTS=1` makes any skipped test fail the run. JUnit and coverage XML remain available as artifacts. Dependency auditing includes development dependencies in both languages. Actionlint validates workflow expressions and embedded shell.

Rejected alternative: adding another framework for checks or distributed transactions would expand operational dependencies. Existing compilers, linters, test runners, Docker images, MongoDB conditional writes and Node's standard library cover the verified failures. Splitting checks exposes independent failures without waiting for unrelated jobs to finish.

## Application changes

Identity replacement and arrival use conditional updates, preserve the first successful writer and avoid a follow-up database read on the successful path. A concurrently deleted camp/day returns 404 rather than failing during serialization. Exact patient-code collisions retry within a bounded limit; other unique-index failures retain their original handling. Historical UUID patient codes remain readable. Retired duplicate-check and clinical cleanup helpers have no live callers and were removed.

Superseded for clinical writes by ADR 0065 (transactions). Clinical completion participates in the existing write claim and can recover its post-commit bookkeeping on retry. Undo and correction use the same claim as issuing. Frontend searches remove stale actions, polling avoids overlap, draft navigation waits for persistence, and failed initial analytics loads display the error. The companion audit documents describe regression scenarios and remaining recovery limits.

## Consequences and limits

Frontend static checking is intentionally limited to the six modules listed in `frontend/tsconfig.json`; React component props and custom browser globals still need an explicit typing migration. Python imports without published types remain unchecked at that library boundary; the application bodies are checked. [TypeScript checkJs](https://www.typescriptlang.org/tsconfig/checkJs.html) and [mypy incremental adoption](https://mypy.readthedocs.io/en/stable/existing_code.html) describe these boundaries. Test-process coverage does not measure code running inside the separate HTTP container.

The GitHub API reports that this private repository's plan does not support branch protection. The `verify` result is a release gate for this deployment, but repository settings cannot currently enforce it against every future manual merge. No workflow can establish absence of every bug. Hardware scanner/printer acceptance and representative production-load benchmarks remain separate checks. SMS provider delivery requires configured credentials/templates; accepted sends whose receipt could not be stored require reconciliation. Clinical writes are transactions since ADR 0065, which removes the crash-recovery limitation `clinical-audit.md` described.

## Verification record

Local final checks passed: 289 frontend tests and one snapshot, 580 backend tests with zero skips against rebuilt isolated HTTP/MongoDB services, mypy for all 24 production modules, warning-free ESLint, fatal Python lint, compilation, production builds, dependency audits, Actionlint and Compose/Caddy/nginx configuration validation. Application statement coverage is approximately 80% frontend and 83% backend. Negative fixtures confirmed the CI guards reject skipped tests and oversized assets. The two parallel adversarial reviews found one unused-dependency issue, which was fixed; a further correctness review accepted the sparse-record correction compatibility fix.

## Database and deployment

No schema or destructive data migration is required. Deployment must back up the existing database, preserve the `snp` Compose project and its volumes, start the reviewed release so the existing idempotent index initializer runs, and verify HTTPS health plus collection counts. Never substitute a database reset for an update. Keep the previous release directory until the new release is healthy.
