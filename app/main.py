"""Integration HTTP API. Invalid intake is persisted, including malformed JSON."""

import secrets
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text

from app import config
from app.broker import connect
from app.db import Event, Message, Session, engine
from app.schemas import CanonicalPurchaseOrder
from app.service import intake, log, retry

app = FastAPI(title="Enterprise EDI Integration Delivery", version="1.0.0")


def authenticate(x_api_key: str = Header(default="")):
    if config.API_KEY and not secrets.compare_digest(x_api_key, config.API_KEY):
        raise HTTPException(401, "API key required")


@app.get("/health")
def health():
    result = {"application": "ok", "database": "down", "broker": "down"}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        result["database"] = "ok"
    except Exception as exc:
        log(type(exc).__name__, level="ERROR", component="health")
    try:
        connection, _ = connect()
        connection.close()
        result["broker"] = "ok"
    except Exception as exc:
        log(type(exc).__name__, level="ERROR", component="health")
    return JSONResponse(result, status_code=200 if all(v == "ok" for v in result.values()) else 503)


async def read_raw(request):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 262144:
            raise HTTPException(413, "Maximum body size is 256 KiB")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "Body must be UTF-8") from None


@app.post(
    "/api/v1/orders",
    dependencies=[Depends(authenticate)],
    status_code=202,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/CanonicalPurchaseOrder"},
                }
            },
        }
    },
)
async def orders(request: Request):
    result, code = intake(await read_raw(request), "JSON")
    return JSONResponse(result, status_code=code)


@app.post(
    "/api/v1/edi/orders",
    dependencies=[Depends(authenticate)],
    status_code=202,
    openapi_extra={
        "requestBody": {"required": True, "content": {"text/plain": {"schema": {"type": "string"}}}}
    },
)
async def edi_orders(request: Request):
    result, code = intake(await read_raw(request), "EDI")
    return JSONResponse(result, status_code=code)


def serialize(message):
    return {
        "correlation_id": message.id,
        "external_order_id": message.external_order_id,
        "customer_id": message.customer_id,
        "source": message.source,
        "status": message.status,
        "received_at": message.received_at,
        "updated_at": message.updated_at,
        "erp_order_id": message.erp_order_id,
        "retry_count": message.retries,
        "last_retry_at": message.last_retry_at,
        "error": message.error,
    }


@app.get("/api/v1/messages", dependencies=[Depends(authenticate)])
def messages(
    status: str | None = None,
    source: str | None = None,
    customer: str | None = None,
    date: date | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    query = select(Message)
    for column, value in [
        (Message.status, status),
        (Message.source, source),
        (Message.customer_id, customer),
    ]:
        if value:
            query = query.where(column == value)
    if date:
        start = datetime.combine(date, time.min, tzinfo=UTC)
        query = query.where(
            Message.received_at >= start, Message.received_at < start + timedelta(days=1)
        )
    with Session() as session:
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        rows = session.scalars(
            query.order_by(Message.received_at.desc(), Message.id).limit(limit).offset(offset)
        )
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [serialize(m) for m in rows],
        }


@app.get("/api/v1/metrics", dependencies=[Depends(authenticate)])
def metrics():
    with Session() as session:
        counts = dict(
            session.execute(select(Message.status, func.count()).group_by(Message.status)).all()
        )
        return {"total": sum(counts.values()), "by_status": counts}


@app.get("/api/v1/messages/{correlation_id}", dependencies=[Depends(authenticate)])
def message_detail(correlation_id: str):
    with Session() as session:
        message = session.get(Message, correlation_id)
        if not message:
            raise HTTPException(404, "Message not found")
        events = session.scalars(
            select(Event).where(Event.message_id == correlation_id).order_by(Event.id)
        )
        return dict(
            serialize(message),
            raw=message.raw,
            canonical=message.canonical,
            acknowledgement=message.acknowledgement,
            processing_steps=[{"at": e.at, "status": e.status, "detail": e.detail} for e in events],
        )


class RetryRequest(BaseModel):
    replacement_raw: str | None = Field(default=None, max_length=262144)


@app.post(
    "/api/v1/messages/{correlation_id}/retry", dependencies=[Depends(authenticate)], status_code=202
)
def retry_message(correlation_id: str, payload: RetryRequest | None = None):
    result, code = retry(correlation_id, payload.replacement_raw if payload else None)
    return JSONResponse(result, status_code=code)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard():
    return Path(__file__).with_name("dashboard.html").read_text()


def custom_openapi():
    """Document the canonical JSON contract while retaining raw-input error auditing."""
    if app.openapi_schema is None:
        document = get_openapi(title=app.title, version=app.version, routes=app.routes)
        canonical = CanonicalPurchaseOrder.model_json_schema(
            ref_template="#/components/schemas/{model}"
        )
        definitions = canonical.pop("$defs", {})
        schemas = document.setdefault("components", {}).setdefault("schemas", {})
        schemas.update(definitions)
        schemas["CanonicalPurchaseOrder"] = canonical
        app.openapi_schema = document
    return app.openapi_schema


app.openapi = custom_openapi
