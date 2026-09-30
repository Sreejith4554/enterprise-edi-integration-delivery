# Release / cutover runbook

Owner roles for this single-person demo: release owner executes commands; a reviewer can independently verify evidence. Record actual names, commit, time and decisions when executing; this file is not evidence of a historical release.

## Pre-release

1. Pin the candidate Git commit and review its diff, open defects and limitations.
2. Generate/validate ignored environment configuration; ensure loopback ports and no committed secrets.
3. Run lint, isolated tests and the real Compose smoke job; retain artifacts.
4. Confirm SQL/broker readiness, init exit success, API health and sample EDI/JSON acknowledgements.
5. Confirm backup exists and restore procedure has been reviewed. Schema v1 initializes fresh data only; a schema-changing upgrade requires a separate migration.

## Deployment / cutover

1. Pause new submissions and let pending outbox/queue work drain, or record remaining correlation IDs.
2. Create a timestamped PostgreSQL backup using the operations guide; preserve current `.env` securely and record prior image/commit.
3. Check out the approved commit, build with `docker compose build`, then `docker compose up -d --wait --wait-timeout 180`.
4. Init creates missing v1 tables. Do not deploy an incompatible schema change with create_all.
5. Check `docker compose ps`, `/health`, consumer presence and a fresh-ID live smoke run.
6. Inspect ERP ID, response and events, then resume submissions after go/no-go decision.

## Go / no-go

Go only if tests and actual stack smoke pass, no known data-loss/idempotency defect is open, both formats produce acknowledgements, correction/retry succeeds and rollback materials are ready. No-go on migration uncertainty, persistent health failure, missing consumer, missing acknowledgement, duplicate ERP effects or unresolved critical defect. A missing verification result is not a pass.

## Rollback

Trigger on repeat smoke failure, incorrect mapping, loss of audit data or duplicate side effects. Pause intake; preserve logs and affected IDs. Stop API/dispatcher/worker to avoid concurrent processing. Restore previous application commit/images and start dependency services. If schema is unchanged, keep the database; verify replay safety before resuming. For incompatible schema damage, restore the tested backup into a compatible database and reconcile orders created in the ERP since backup. Queue/database snapshots are not atomic; do not simply purge queues. Resume workers, check outstanding messages, submit a fresh sample and document reconciliation. Never discard volumes as a rollback shortcut.

## Stabilization and handover

During the first demo/release session, monitor errors, VALIDATED/QUEUED age, ready/unacknowledged queue counts, consumer connectivity and acknowledgement presence. Validate at least one new order of each format after restart. Capture defects with reproducible payloads and correlation IDs. Handover includes commit/run evidence, configuration ownership, this runbook, operations guide, mapping contract, known limitations and recovery demonstration. Hypercare ends after agreed observation and all critical defects are resolved or the release is rolled back; no invented availability metrics.
