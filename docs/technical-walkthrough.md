# Technical walkthrough in plain English

| Concept | Meaning | Where to inspect or demonstrate it here |
|---|---|---|
| EDI | Trading partners exchange agreed structured business documents instead of manually retyping them. Syntax alone is insufficient; partners must agree on field meanings. | examples/valid_order.edi and docs/edi-mapping.md; only a narrow ORDERS-like subset |
| API | Software requests an operation over an interface; here HTTP with JSON. | POST /api/v1/orders and Swagger |
| API versus EDI | HTTP is a transport/interface, EDI describes a business-message format. They are not mutually exclusive: this application carries EDI text over HTTP. | POST /api/v1/edi/orders |
| Middleware | Software between systems that validates, adapts, routes and tracks information. | API, mapping, outbox and worker together |
| Canonical model | One internal shape shared by different external formats, so downstream logic is not duplicated. | CanonicalPurchaseOrder in app/schemas.py; both adapters call map_order |
| Mapping | Assigning source fields to target fields and converting their types. | BGM number becomes external_order_id; QTY text becomes Decimal in app/mapping.py |
| Validation | Checking required fields, valid syntax and business rules before processing. | Pydantic dates/quantities and business_validate customer/SKU checks |
| Business versus technical failure | A bad SKU needs corrected data; an unavailable ERP needs service recovery. | Persisted error kind/code/retryable; service.fail and worker.process |
| Correlation ID | A technical UUID connecting one inbound message to its processing events, ERP effect and confirmation. | Message.id, ERP correlation_id, logs and detail endpoint |
| Queue | A durable buffer between intake and processing; work can wait when a worker is offline. | RabbitMQ integration.orders.v1; worker acknowledges after commit |
| Transactional outbox | A database record of work to publish, committed with the accepted order, so a broker outage cannot create an accepted-but-lost message. | Outbox table and broker.dispatch_once |
| Idempotency | Repeating an operation has one intended effect. It is not a guarantee of one network delivery. | Unique customer/order claim plus ERP correlation-key uniqueness and canonical equality |
| Retry generation | A counter distinguishing a new operator attempt from a delayed old queue delivery. | Message.generation and worker check |
| Acknowledgement | A stored response reporting simulator acceptance and the ERP order ID. | mapping.acknowledgement and message detail; not sent to a real partner |
| Integration testing | Checking collaborating components, beyond one small function. | tests/test_integration.py uses actual API/database/ERP logic; scripts/smoke.py verifies real infrastructure |
| UAT | A reviewer confirms that business acceptance criteria are met with representative examples. | delivery/acceptance-criteria.md; execute and record actual evidence |
| Defect lifecycle | Reproduce, assess severity, fix, retest and close with evidence. | delivery/azure-devops-backlog.md bug template; no fabricated historic bugs |
| Deployment | Put a tested application version into a running environment. | Dockerfile, docker-compose.yml and CI |
| Cutover | Controlled switch to a new release, including readiness and a go/no-go decision. | docs/release-runbook.md deployment sequence |
| Rollback | Return to a known version while preserving/reconciling data and outstanding work. | Runbook rollback section; never blindly delete volumes |
| Stabilization / hypercare | Focused observation and prompt recovery after release. | Runbook monitoring of failed messages, queues and confirmations |
| Operational handover | Giving the next operator enough access, documentation and practice to operate safely. | docs/operations.md and runbook handover list |

## Follow one purchase order

1. A JSON payload is read as raw text so even malformed JSON can be retained with a correlation ID.
2. The adapter creates the canonical Pydantic model. Decimal values become decimal strings in JSON, preserving price precision.
3. Within one SQL transaction, a valid order claims its business key, records VALIDATED and creates an outbox record.
4. The dispatcher obtains RabbitMQ confirmation and marks QUEUED. A crash can produce another delivery, which is expected.
5. The worker locks the message and sends the canonical payload to the ERP. ERP replay returns the same ID.
6. The worker commits confirmation and audit events, then acknowledges RabbitMQ. A crash before commit causes safe replay.
7. An operator can retrieve everything using the correlation ID. Failures are explicit; corrections preserve previous raw input.

## Questions to be ready for

**Why not just call ERP during intake?** That would tie the customer's request latency and availability directly to ERP. Queueing separates acceptance from completion.

**What if RabbitMQ is down?** Valid orders remain in PostgreSQL with unpublished outbox rows. The dispatcher logs the outage and reconnects. Health is degraded; intake can still persist orders if SQL is available.

**What if ERP succeeds but the worker crashes?** RabbitMQ redelivers. ERP recognizes the correlation key and returns the existing order, preventing a second business effect.

**What would production require?** Partner-specific EDI contracts, stronger authentication/authorization, TLS, secret management, schema migrations, separate service ownership, dead-letter policy, observability, retention and measured capacity/recovery tests. These are limitations, not completed features.
