# Five-to-seven minute interview demo

Prepare: start Compose, install pinned test dependencies, open dashboard and Swagger. Run `python scripts/smoke.py` beforehand to confirm readiness. The standard fixture order IDs can be submitted only once; change BGM/JSON IDs for every new order or use the smoke script's fresh IDs.

**0:00–1:00 — Purpose and boundaries.** “I built this learning implementation with AI assistance to understand integration delivery. Nordic Retail and Atlas are fictional. It integrates an API or a limited EDI message with an ERP simulator, not SAP.” Show the README architecture. Explain that the canonical model avoids two downstream workflows.

**1:00–2:00 — Submit EDI.** Show the valid EDI fixture and its BGM, NAD, LIN, QTY and PRI mappings. Submit the curl example with a fresh BGM order number. Copy the returned correlation ID. Explain why 202 is acceptance into durable asynchronous work, not order completion.

**2:00–3:00 — Trace.** Refresh dashboard, open the message. Show raw EDI, canonical JSON, RECEIVED → VALIDATED → QUEUED → PROCESSING → COMPLETED events and ERP ID. Explain the outbox closes the database/broker gap and the queue decouples intake from downstream availability.

**3:00–4:00 — Confirm and deduplicate.** Show the stored JSON/ORDRSP acknowledgement. Resubmit the same order; demonstrate 409 and the original correlation reference. Distinguish a customer business key from a technical correlation ID.

**4:00–5:00 — Correct a failure.** Submit invalid_order.json with a new ID, inspect the unknown-SKU failure, then paste a corrected complete payload into dashboard detail and retry. Show the same correlation ID, retry count, previous raw text and successful confirmation.

**5:00–6:00 — Technical recovery (optional).** Use `python scripts/smoke.py --chaos` or stop/start ERP manually with a fresh order. Show persisted technical error and bounded manual retry. Do not imply exactly-once transport: the ERP correlation key prevents replayed effects.

**6:00–7:00 — Evidence and release.** Show pytest output and actual GitHub Actions run, the mapping contract and go/no-go runbook. State limitations plainly. The delivery contribution is understanding requirements, mappings, test evidence, operational risks, defect handling and release readiness; this project does not claim employment experience or unaided authorship of every component.
