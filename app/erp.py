"""Fictional Atlas ERP simulator, served as a separate HTTP process."""

import os
import secrets
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import config
from app.db import ERPOrder, Session
from app.schemas import CanonicalPurchaseOrder, business_validate
from app.service import log

app = FastAPI(title="Atlas ERP Simulator (fictional)")


def authenticate(x_internal_key: str = Header(default="")):
    if not config.INTERNAL_API_KEY or not secrets.compare_digest(
        x_internal_key, config.INTERNAL_API_KEY
    ):
        raise HTTPException(401, "Internal key required")


class ERPRequest(BaseModel):
    correlation_id: uuid.UUID
    order: CanonicalPurchaseOrder


@app.get("/health")
def health():
    return {"status": "ok", "simulator": True}


@app.post("/internal/erp/orders", dependencies=[Depends(authenticate)])
def create_order(payload: ERPRequest):
    if os.getenv("ERP_FAIL_MODE", "false").lower() == "true":
        raise HTTPException(503, "Simulated ERP maintenance")
    business_validate(payload.order)
    correlation_id = str(payload.correlation_id)
    canonical = payload.order.model_dump(mode="json")

    def existing_result(record):
        if record.canonical != canonical:
            raise HTTPException(409, "Correlation key reused with different order")
        return {"erp_order_id": record.id}

    try:
        with Session.begin() as session:
            record = session.scalar(
                select(ERPOrder).where(ERPOrder.correlation_id == correlation_id)
            )
            if record:
                return existing_result(record)
            record = ERPOrder(
                id="ERP-" + uuid.uuid4().hex.upper(),
                correlation_id=correlation_id,
                canonical=canonical,
            )
            session.add(record)
            session.flush()
            result = {"erp_order_id": record.id}
        log("ERP_ORDER_CREATED", correlation_id, component="erp")
        return result
    except IntegrityError:
        with Session() as session:
            return existing_result(
                session.scalar(select(ERPOrder).where(ERPOrder.correlation_id == correlation_id))
            )
