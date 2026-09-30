# Risks, assumptions, issues and dependencies

| Type | Item | Response / owner role |
|---|---|---|
| Risk | Crash between queue publish and SQL commit repeats delivery | Publisher confirms + outbox replay + idempotent worker/ERP; integration owner |
| Risk | Partner assumes full EDIFACT support | Explicit subset contract and rejection of unsupported syntax; integration owner |
| Risk | Raw/audit data grows without retention | Synthetic data only; design retention before production use; operations owner |
| Risk | Unexpected worker defect repeatedly redelivers | Stop/fix worker; future dead-letter policy; technical owner |
| Assumption | Known customer and two SKUs sufficient for demonstrator | Documented catalog in schemas.py; expand only with tests |
| Assumption | Local loopback demo, not internet-facing deployment | Review auth/TLS/RBAC before broader access |
| Issue | Version 1 has initialization but no schema migration engine | Future releases must supply explicit migration plan |
| Dependency | Docker Compose, PostgreSQL and RabbitMQ | CI smoke checks exact deployment path |
| Dependency | Owner UAT and interview preparation | Follow acceptance checklist and technical walkthrough |

These are design observations and open limitations, not invented historical incidents.
