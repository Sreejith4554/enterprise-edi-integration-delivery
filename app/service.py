"""Transactional intake, order claims, outbox, and bounded operator recovery."""

import json
import logging

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import MAX_RETRIES
from app.db import Event, Message, OrderClaim, Outbox, Session, now
from app.mapping import map_order

logger = logging.getLogger("integration")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def log(event: str, correlation_id: str | None = None, level="INFO", component="integration"):
    logger.log(
        getattr(logging, level),
        json.dumps(
            {
                "timestamp": now().isoformat(),
                "component": component,
                "level": level,
                "correlation_id": correlation_id,
                "event": event,
            }
        ),
    )


def transition(session, message, status, detail=None):
    message.status, message.updated_at = status, now()
    session.add(Event(message_id=message.id, status=status, detail=detail or {}))
    log(status, message.id)


def fail(session, message, kind, code, detail, retryable):
    message.error = {"kind": kind, "code": code, "detail": detail, "retryable": retryable}
    transition(session, message, "FAILED", message.error)


def validate_and_queue(session, message):
    try:
        canonical = map_order(message.raw, message.source).model_dump(mode="json")
    except (ValueError, ValidationError) as exc:
        detail = (
            json.loads(exc.json(include_url=False, include_context=False))
            if isinstance(exc, ValidationError)
            else str(exc)
        )
        fail(session, message, "BUSINESS", "INVALID_MESSAGE", detail, False)
        return 422
    message.external_order_id = canonical["external_order_id"]
    message.customer_id = canonical["customer_id"]
    message.canonical = canonical
    key = canonical["customer_id"] + ":" + canonical["external_order_id"]
    existing = session.get(OrderClaim, key)
    if existing and existing.message_id != message.id:
        fail(
            session,
            message,
            "BUSINESS",
            "DUPLICATE_ORDER",
            {"original_correlation_id": existing.message_id},
            False,
        )
        return 409
    if not existing:
        try:
            with session.begin_nested():
                session.add(OrderClaim(key=key, message_id=message.id))
                session.flush()
        except IntegrityError:
            fail(session, message, "BUSINESS", "DUPLICATE_ORDER", "Order already claimed", False)
            return 409
    message.error = None
    transition(session, message, "VALIDATED")
    session.add(Outbox(message_id=message.id, generation=message.generation))
    return 202


def intake(raw: str, source: str):
    with Session.begin() as session:
        message = Message(raw=raw, source=source)
        session.add(message)
        session.flush()
        transition(session, message, "RECEIVED")
        code = validate_and_queue(session, message)
        result = {"correlation_id": message.id, "status": message.status, "error": message.error}
    return result, code


def retry(correlation_id: str, replacement_raw: str | None = None):
    with Session.begin() as session:
        message = session.scalar(
            select(Message).where(Message.id == correlation_id).with_for_update()
        )
        if message is None:
            return {"detail": "Message not found"}, 404
        if message.status != "FAILED" or message.retries >= MAX_RETRIES:
            return {"detail": "Only failed messages below the retry limit can be retried"}, 409
        if message.error["code"] == "DUPLICATE_ORDER":
            return {"detail": "Duplicate orders cannot be retried"}, 409
        if replacement_raw is not None and message.error["code"] != "INVALID_MESSAGE":
            return {"detail": "Only validation failures may change payload"}, 409
        if replacement_raw is None and not message.error["retryable"]:
            return {"detail": "Validation failure requires corrected replacement_raw"}, 409
        message.retries += 1
        message.generation += 1
        message.last_retry_at = now()
        if replacement_raw is not None:
            session.add(
                Event(
                    message_id=message.id,
                    status="CORRECTED",
                    detail={"previous_raw": message.raw, "retry": message.retries},
                )
            )
            message.raw = replacement_raw
        transition(session, message, "RECEIVED", {"retry": message.retries})
        code = validate_and_queue(session, message)
        result = {"correlation_id": message.id, "status": message.status, "error": message.error}
    return result, code
