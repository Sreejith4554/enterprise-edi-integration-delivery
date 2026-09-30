# Verification record — 2026-09-30

## Observed passes

- Python 3.12 isolated suite: **43 tests passed**, including canonical mapping, malformed EDI, business validation, API flows, concurrent duplicate claims, transactional outbox failure/recovery, retry limits, stale generations, ERP replay after a simulated worker crash, error classification and OpenAPI schema.
- Ruff lint and formatting checks passed.
- Actual API and ERP HTTP processes were started on loopback. JSON and EDI orders reached completion through the manually invoked production worker; ERP IDs and confirmations were retrieved over HTTP.
- Live HTTP duplicate rejection, failed-input persistence, correction/retry, ERP connection-refusal recovery, filtered history and dashboard serving passed. See [live-http-evidence.json](live-http-evidence.json) for recorded checks and synthetic correlation IDs.
- Health correctly returned 503 with database ok and broker down in this limited live environment.
- Compose and GitHub Actions YAML parsed successfully. Dependency graph, readiness conditions and workflow commands were inspected. This is not a Docker execution result.

## Explicitly unverified / blocked

- Docker is absent in the authoring environment. System package installation was denied. PostgreSQL, RabbitMQ and the complete Docker Compose stack were **not run here**.
- The real asynchronous infrastructure smoke test is implemented in `scripts/smoke.py` and wired into CI, but **not executed** in this session.
- GitHub repository metadata was accessible and reported repository-level push permission. The actual content-write API returned **403 Resource not accessible by integration**. No repository files or commits were published, and no GitHub Actions run occurred.
- No browser visual/accessibility audit, load test, penetration test, disaster-recovery exercise or full-EDIFACT certification is claimed.

The live HTTP check used SQLite, not PostgreSQL, and invoked the worker directly, not through RabbitMQ. Its evidence cannot be used as proof of queue delivery or PostgreSQL concurrency. Unit tests explicitly substitute broker transport.

Pinned FastAPI/Starlette test tooling emits one upstream deprecation warning about TestClient's httpx backend; the tests pass. Before declaring the brief's definition of done satisfied, publish/import the repository and obtain a passing real Compose smoke run. Follow [publishing.md](publishing.md).
