# Operations

## Inspect

- `docker compose ps`: init exits successfully; API, ERP, dispatcher, worker, db and broker stay running.
- `curl -i localhost:8000/health`: 200 only if API, SQL connection and broker connection work; 503 otherwise. This endpoint does not prove the worker or ERP is alive: submit a smoke order for that.
- `docker compose logs -f api dispatcher worker erp`: structured domain events contain timestamp, component, level, correlation_id and event. Uvicorn access logs remain conventional. Credentials/raw bodies are not included in domain logs.
- Dashboard: counts over the full database, recent paginated rows, status filter, raw/canonical/acknowledgement timeline and manual retry.
- RabbitMQ management: queue `integration.orders.v1`, ready/unacknowledged counts and connected consumers. Management credentials are in ignored `.env`.

## Recovery decision table

| Symptom | Interpretation | Action |
|---|---|---|
| VALIDATED accumulating | Outbox not published, likely broker/dispatcher outage | Check logs, restore broker/dispatcher; automatic dispatch resumes |
| QUEUED accumulating | Worker offline or ERP call in progress | Inspect worker and queue consumers; restore service |
| FAILED / INVALID_MESSAGE | Input/schema/business rejection | Correct full original-format payload and retry; prior input remains audited |
| FAILED / DUPLICATE_ORDER | Customer/order key already reserved | Inspect original correlation ID; do not retry |
| FAILED / ERP_UNAVAILABLE or 5xx ERP_REJECTED | Technical downstream failure | Restore ERP; explicit retry without replacement |
| ERP 4xx rejection | Contract/auth problem, nonretryable | Diagnose code/configuration; no blind retry |
| Unexpected worker exception loop | Code/infrastructure defect, rolled back delivery | Stop affected worker, inspect logs, fix/redeploy; message remains unacknowledged for redelivery |

Retry count is capped at MAX_RETRIES (default 3). There is no automatic business/ERP retry storm. Operator retries increment generation, making stale queue envelopes harmless. If retry capacity is exhausted, investigate and fix deliberately; do not edit database records casually to bypass controls.

## Security and data

Loopback host bindings; no CORS middleware means no cross-origin browser API access by default. Internal ERP requires a generated secret. Optional API key protects intake, read and retry APIs together, with no roles or user-level audit attribution. Dashboard key stays in memory and is not written to localStorage. Change credentials by coordinating service configuration and broker/database user changes; changing `.env` alone does not rotate credentials in existing volumes. Use synthetic data only. Raw input/audit persistence has no redaction or retention policy.

Back up before schema/code changes: `docker compose exec -T db pg_dump -U integration -d integration > integration-backup.sql`. Protect that file. Restore into a clean compatible database during a maintenance window; restoring the database alone does not atomically restore broker state. Replays are idempotent, but coordinated recovery needs validation. Never run `docker compose down -v` on data you intend to retain.
