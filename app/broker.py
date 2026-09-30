"""Persistent RabbitMQ delivery backed by a transactional SQL outbox."""

import json
import time

import pika
from sqlalchemy import select

from app import config
from app.db import Message, Outbox, Session, now
from app.service import log, transition


def connect():
    parameters = pika.URLParameters(config.BROKER_URL)
    parameters.socket_timeout = 3
    parameters.blocked_connection_timeout = 5
    parameters.heartbeat = 30
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    channel.queue_declare(queue=config.QUEUE, durable=True)
    return connection, channel


def dispatch_once(channel):
    with Session.begin() as session:
        rows = session.scalars(
            select(Outbox)
            .where(Outbox.published_at.is_(None))
            .order_by(Outbox.id)
            .limit(50)
            .with_for_update(skip_locked=True)
        ).all()
        for row in rows:
            message = session.scalar(
                select(Message).where(Message.id == row.message_id).with_for_update()
            )
            if message.generation == row.generation and message.status == "VALIDATED":
                channel.basic_publish(
                    exchange="",
                    routing_key=config.QUEUE,
                    body=json.dumps({"id": row.message_id, "generation": row.generation}),
                    properties=pika.BasicProperties(
                        delivery_mode=2,
                        content_type="application/json",
                        correlation_id=row.message_id,
                    ),
                    mandatory=True,
                )
                transition(session, message, "QUEUED")
            row.published_at = now()
        return len(rows)


def run():
    while True:
        connection = None
        try:
            connection, channel = connect()
            channel.confirm_delivery()
            while True:
                dispatch_once(channel)
                connection.process_data_events(time_limit=1)
        except Exception as exc:
            log(type(exc).__name__, level="ERROR", component="dispatcher")
            time.sleep(2)
        finally:
            if connection and connection.is_open:
                connection.close()


if __name__ == "__main__":
    run()
