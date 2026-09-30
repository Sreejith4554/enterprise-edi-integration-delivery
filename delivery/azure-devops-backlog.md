# Azure DevOps recreation guide

No Azure DevOps board or professional usage is claimed. Recreate this structure manually in an Agile-process project if useful. One **Epic: Enterprise Customer Integration**. Features sit under the Epic; User Stories under Features; Tasks and any actually observed Bugs beneath the relevant story. Link this GitHub repository and actual CI evidence. Implemented does not automatically mean owner-accepted; set stories to Resolved pending UAT, then Closed only after recorded acceptance.

| Feature | User story | Acceptance criteria | Implemented tasks / evidence |
|---|---|---|---|
| Inbound Integration | As a customer, submit a JSON purchase order | Valid returns 202 + ID; invalid returns 422 + persisted error; oversized body rejected | main.orders, read_raw; JSON tests; valid/invalid fixtures |
| EDI Processing | As a partner, submit the agreed ORDERS subset | Required envelope/segments/qualifiers validated; malformed input audited | mapping.parse_edi; parser parametrized tests |
| Canonical Mapping | As an integration owner, use one downstream contract | Both inputs produce CanonicalPurchaseOrder; precise prices and unique lines | schemas.py, map_order, edi-mapping.md |
| ERP Integration | As supplier operations, create one ERP effect | Durable asynchronous processing; ERP ID and confirmation; replay safe | broker.py, worker.py, erp.py; full Compose smoke |
| Message Monitoring | As an operator, trace a message | Raw/canonical/events/ack visible; filters/pagination; total counts | detail/history/metrics APIs; dashboard |
| Error Recovery | As an operator, recover appropriate failures | Correct validation errors; immutable technical retries; cap; prior data retained | service.retry; retry/duplicate/stale-generation tests |
| Release & Operations | As release owner, deploy and demonstrate | Real stack smoke passes; runbook and handover available | CI, Docker, docs, evidence artifacts |

Suggested task fields: Title, Assigned To (actual owner), Remaining Work (owner estimate), Parent story, repository paths, linked commit and verification result. Avoid fictitious effort or business-value metrics.

## Bug template (use only for observed defects)

Title; affected commit/environment; synthetic input and correlation ID; exact reproduction steps; expected/actual result; severity and impact; log excerpt without credentials; owner; fix commit; regression test; retest evidence. State flow: New → Active → Resolved → Closed; reopen if retest fails. Do not invent resolved bug records to populate a portfolio board.

## Future backlog (not implemented)

Versioned migrations, partner authentication/RBAC, negative EDI responses, dead-letter handling for poison envelopes, metrics/alerts, retention controls and a standards-compliant partner-specific EDIFACT parser. These should be separate future stories, not marked complete.
