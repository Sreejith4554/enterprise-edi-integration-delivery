"""At-least-once worker. ERP correlation keys make replay safe after crashes."""

import json
import time

import httpx
from sqlalchemy import select

from app import config
from app.broker import connect
from app.db import Message, Session
from app.mapping import acknowledgement
from app.service import fail, log, transition


def call_erp(correlation_id, canonical):
    response = httpx.post(
        config.ERP_URL + "/internal/erp/orders",
        json={"correlation_id": correlation_id, "order": canonical},
        headers={"X-Internal-Key": config.INTERNAL_API_KEY},
        timeout=10,
        trust_env=False,
    )
    response.raise_for_status()
    return response.json()["erp_order_id"]


def process(correlation_id, generation, erp_client=call_erp):
    # Keep row locked until result commits. A crash rolls back and RabbitMQ redelivers.
    with Session.begin() as session:
        message = session.scalar(
            select(Message).where(Message.id == correlation_id).with_for_update()
        )
        if (
            message is None
            or message.generation != generation
            or message.status not in {"QUEUED", "VALIDATED"}
        ):
            return
        transition(session, message, "PROCESSING")
        try:
            erp_id = erp_client(message.id, message.canonical)
        except httpx.HTTPStatusError as exc:
            transient = exc.response.status_code >= 500 or exc.response.status_code == 429
            fail(
                session,
                message,
                "TECHNICAL" if transient else "BUSINESS",
                "ERP_REJECTED",
                f"ERP HTTP {exc.response.status_code}",
                transient,
            )
        except httpx.RequestError:
            fail(
                session,
                message,
                "TECHNICAL",
                "ERP_UNAVAILABLE",
                "ERP transport timeout/unavailable",
                True,
            )
        else:
            message.erp_order_id = erp_id
            message.acknowledgement = acknowledgement(
                message.canonical, erp_id, message.id, message.source
            )
            message.error = None
            transition(session, message, "COMPLETED")


def run():
    while True:
        connection = None
        try:
            connection, channel = connect()
            channel.basic_qos(prefetch_count=1)

            def consume(ch, method, properties, body):
                try:
                    data = json.loads(body)
                    if not isinstance(data["id"], str) or type(data["generation"]) is not int:
                        raise ValueError("Invalid envelope")
                except (ValueError, KeyError, TypeError):
                    log("INVALID_QUEUE_ENVELOPE", level="ERROR", component="worker")
                    ch.basic_reject(method.delivery_tag, requeue=False)
                    return
                process(data["id"], data["generation"])
                ch.basic_ack(method.delivery_tag)

            channel.basic_consume(queue=config.QUEUE, on_message_callback=consume)
            channel.start_consuming()
        except Exception as exc:
            log(type(exc).__name__, level="ERROR", component="worker")
            time.sleep(2)
        finally:
            if connection and connection.is_open:
                connection.close()


if __name__ == "__main__":
    run()
