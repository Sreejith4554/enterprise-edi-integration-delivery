# Testing and verification

## Isolated suite

Install `requirements.lock`, then `python -m pytest -q`. `tests/conftest.py` sets a temporary SQLite URL before importing application modules and recreates tables for each test. Actual business functions, FastAPI routes, ORM transactions and ERP endpoint are tested. The broker channel is a controlled test double; it can deliberately fail publishing. ERP transport failures use httpx exceptions. No unit test claims to prove PostgreSQL locks or RabbitMQ delivery.

Covered: decimal canonical mapping, ORDERS parsing and malformed variants, date/currency/customer checks, asynchronous state transitions through the dispatcher/worker entry points, success confirmations, concurrent duplicate claims, failed-input persistence, correction history, nonretryable duplicates, retry limit, stale-generation handling, outbox retention during outage, ERP key replay, pagination/filtering, authentication, input limits, dashboard serving and dependency health failure.

## Live stack

`docker compose up --build -d --wait --wait-timeout 180`, then `python scripts/smoke.py --chaos`.

This calls the network API and lets real dispatcher, RabbitMQ worker and ERP HTTP service finish each order. It checks all dependency health states, JSON and EDI completions, canonical values, ERP ID, acknowledgement, invalid EDI, invalid SKU, duplicate rejection, correction/retry, history and dashboard response. The chaos step stops the ERP container, waits for a persisted technical failure, restarts and probes it, then retries to completion. Unique order IDs allow repeated runs without clearing data.

The script writes `verification-local.json`; GitHub Actions uploads it alongside `compose.log`. CI also checks Ruff lint/format and executes the isolated suite. Workflow timeout is 15 minutes; teardown removes CI volumes only. Local `docker compose down` preserves data; `down -v` deletes it.

## Interpreting evidence

A green unit suite does not prove Compose works. A successful live smoke does not prove production scalability, full EDIFACT support, disaster recovery, hostile-network security, or browser visual/accessibility conformance. The dashboard is functionally served and uses textContent for untrusted values; no full browser test suite is provided. Current observed results belong in `docs/verification.md`, with the actual CI link where available.
