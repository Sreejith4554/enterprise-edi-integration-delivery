# Integration flows

## Success

```mermaid
sequenceDiagram
  participant C as Customer
  participant A as API and database
  participant Q as Outbox and RabbitMQ
  participant W as Worker
  participant E as ERP simulator
  C->>A: JSON or ORDERS
  A->>A: Persist, validate, canonicalize, claim key, outbox
  A-->>C: 202 and correlation ID
  Q->>A: Lock unpublished outbox row
  Q->>Q: Persistent publish and confirmation
  Q->>A: QUEUED and publication time
  Q->>W: Deliver correlation ID and generation
  W->>A: Lock message, record PROCESSING
  W->>E: POST canonical order with correlation key
  E-->>W: Idempotent ERP order ID
  W->>A: Commit COMPLETED and acknowledgement
  W-->>Q: Consumer acknowledgement
  C->>A: Retrieve timeline and confirmation
```

## Failure and operator recovery

```mermaid
sequenceDiagram
  participant O as Operator
  participant A as API and database
  participant Q as Outbox and RabbitMQ
  participant W as Worker
  participant E as ERP simulator
  Q->>W: Queued order
  W->>E: Create order
  E-->>W: Timeout or 503
  W->>A: Commit FAILED and retryable error
  W-->>Q: Acknowledge delivery
  O->>E: Restore service
  O->>A: POST retry
  A->>A: Check limit, increment generation, persist outbox
  Q->>W: Deliver new generation
  W->>E: Retry same correlation key
  E-->>W: Existing or new ERP order
  W->>A: Commit COMPLETED and confirmation
```

For invalid input, intake returns 422 after storing FAILED. Operator retry must supply corrected raw content. A CORRECTED event holds the previous raw text, and the original failure stays in history. Technical retries reuse the canonical identity; corrections cannot mutate an order whose ERP outcome might already exist. Duplicate errors are terminal.
