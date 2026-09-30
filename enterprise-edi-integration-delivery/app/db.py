"""Schema initialization and transactional message/audit persistence."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import DATABASE_URL


def now():
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Message(Base):
    __tablename__ = "integration_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source: Mapped[str] = mapped_column(String(8))
    raw: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="RECEIVED", index=True)
    external_order_id: Mapped[str | None] = mapped_column(String(80), index=True)
    customer_id: Mapped[str | None] = mapped_column(String(80), index=True)
    canonical: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[dict | None] = mapped_column(JSON)
    acknowledgement: Mapped[dict | None] = mapped_column(JSON)
    erp_order_id: Mapped[str | None] = mapped_column(String(50))
    retries: Mapped[int] = mapped_column(Integer, default=0)
    generation: Mapped[int] = mapped_column(Integer, default=0)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OrderClaim(Base):
    __tablename__ = "order_claims"
    key: Mapped[str] = mapped_column(String(170), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(36), unique=True)


class Event(Base):
    __tablename__ = "processing_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[str] = mapped_column(String(36), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    status: Mapped[str] = mapped_column(String(30))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class Outbox(Base):
    __tablename__ = "outbox"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[str] = mapped_column(String(36), index=True)
    generation: Mapped[int] = mapped_column(Integer)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ERPOrder(Base):
    __tablename__ = "erp_orders"
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    correlation_id: Mapped[str] = mapped_column(String(36), unique=True)
    canonical: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
Session = sessionmaker(engine, expire_on_commit=False)


def init_db():
    Base.metadata.create_all(engine)


if __name__ == "__main__":
    init_db()
