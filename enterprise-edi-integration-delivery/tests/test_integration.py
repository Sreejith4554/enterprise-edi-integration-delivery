import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import config
from app.broker import dispatch_once
from app.db import ERPOrder, Message, Outbox, Session
from app.erp import app as erp_app
from app.mapping import acknowledgement, map_order, parse_edi
from app.service import intake
from app.worker import process


class ConfirmingChannel:
    def __init__(self, fail=False):
        self.messages, self.fail = [], fail

    def basic_publish(self, **kwargs):
        if self.fail:
            raise ConnectionError("broker unavailable")
        self.messages.append(json.loads(kwargs["body"]))


def erp_client(correlation_id, canonical):
    with TestClient(erp_app) as client:
        r = client.post(
            "/internal/erp/orders",
            json={"correlation_id": correlation_id, "order": canonical},
            headers={"X-Internal-Key": config.INTERNAL_API_KEY},
        )
        r.raise_for_status()
        return r.json()["erp_order_id"]


def drain():
    channel = ConfirmingChannel()
    dispatch_once(channel)
    for envelope in channel.messages:
        process(envelope["id"], envelope["generation"], erp_client)
    return channel


def test_json_mapping_decimal(order):
    canonical = map_order(json.dumps(order), "JSON")
    assert str(canonical.items[0].unit_price) == "24.50"
    assert canonical.customer_id == "NORDIC-001"


def test_edi_mapping():
    raw = Path("examples/valid_order.edi").read_text()
    parsed = parse_edi(raw)
    assert parsed["items"][0]["sku"] == "ATLAS-100"
    assert map_order(raw, "EDI").currency == "EUR"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda s: s.replace("UNT+12+1", "UNT+13+1"),
        lambda s: s.replace("UNT+12+1", "UNT+12+2"),
        lambda s: s.replace("QTY+21:12:EA", "QTY+21:0:EA"),
        lambda s: s.replace("DTM+137:20260930:102", "DTM+137:20260230:102"),
        lambda s: s.replace("NAD+BY+NORDIC-001", "NAD+BY"),
        lambda s: s.replace("NAD+BY+NORDIC-001", "NAD+BY+UNKNOWN"),
        lambda s: s.replace("CUX+2:EUR:9", "CUX+2:CHF:9"),
        lambda s: s.replace("PRI+AAA:24.50", "XXX+AAA:24.50"),
        lambda s: s.rstrip()[:-1],
        lambda s: s.replace("Household", "House?hold"),
    ],
)
def test_invalid_edi_persisted(client, mutation):
    response = client.post(
        "/api/v1/edi/orders", content=mutation(Path("examples/valid_order.edi").read_text())
    )
    assert response.status_code == 422
    trace = client.get("/api/v1/messages/" + response.json()["correlation_id"]).json()
    assert trace["status"] == "FAILED" and trace["error"]["code"] == "INVALID_MESSAGE"


@pytest.mark.parametrize(
    "field,value", [("customer_id", ""), ("currency", "CHF"), ("order_date", "bad"), ("items", [])]
)
def test_invalid_json_fields(client, order, field, value):
    order[field] = value
    response = client.post("/api/v1/orders", json=order)
    assert response.status_code == 422
    assert (
        client.get("/api/v1/messages/" + response.json()["correlation_id"]).json()["status"]
        == "FAILED"
    )


def test_json_complete_and_redelivery(client, order):
    response = client.post("/api/v1/orders", json=order)
    assert response.status_code == 202
    cid = response.json()["correlation_id"]
    channel = drain()
    trace = client.get("/api/v1/messages/" + cid).json()
    assert trace["status"] == "COMPLETED"
    assert trace["acknowledgement"]["erp_order_id"].startswith("ERP-")
    assert [e["status"] for e in trace["processing_steps"]] == [
        "RECEIVED",
        "VALIDATED",
        "QUEUED",
        "PROCESSING",
        "COMPLETED",
    ]
    process(cid, channel.messages[0]["generation"], erp_client)
    with Session() as s:
        assert s.scalar(select(func.count()).select_from(ERPOrder)) == 1


def test_edi_complete(client):
    response = client.post(
        "/api/v1/edi/orders", content=Path("examples/valid_order.edi").read_text()
    )
    assert response.status_code == 202
    drain()
    trace = client.get("/api/v1/messages/" + response.json()["correlation_id"]).json()
    assert trace["status"] == "COMPLETED"
    assert "UNT+4+" in trace["acknowledgement"]["edi"]


def test_duplicate_and_nonretryable(client, order):
    first = client.post("/api/v1/orders", json=order)
    second = client.post("/api/v1/orders", json=order)
    assert second.status_code == 409
    assert (
        second.json()["error"]["detail"]["original_correlation_id"]
        == first.json()["correlation_id"]
    )
    assert (
        client.post("/api/v1/messages/" + second.json()["correlation_id"] + "/retry").status_code
        == 409
    )


def test_concurrent_duplicate_claim(order):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: intake(json.dumps(order), "JSON"), range(4)))
    assert sorted(code for _, code in results) == [202, 409, 409, 409]


def test_invalid_correct_retry_preserves_history(client, order):
    response = client.post("/api/v1/orders", content='{"broken":')
    assert response.status_code == 422
    cid = response.json()["correlation_id"]
    assert client.post(f"/api/v1/messages/{cid}/retry").status_code == 409
    assert (
        client.post(
            f"/api/v1/messages/{cid}/retry", json={"replacement_raw": json.dumps(order)}
        ).status_code
        == 202
    )
    drain()
    trace = client.get("/api/v1/messages/" + cid).json()
    assert trace["status"] == "COMPLETED" and trace["retry_count"] == 1
    assert any(e["detail"].get("previous_raw") == '{"broken":' for e in trace["processing_steps"])
    assert client.post(f"/api/v1/messages/{cid}/retry").status_code == 409


def test_erp_unavailable_retry_and_stale_envelope(client, order):
    cid = client.post("/api/v1/orders", json=order).json()["correlation_id"]
    channel = ConfirmingChannel()
    dispatch_once(channel)

    def unavailable(*args):
        raise httpx.ConnectError("offline")

    process(cid, 0, unavailable)
    trace = client.get("/api/v1/messages/" + cid).json()
    assert trace["error"]["retryable"]
    assert (
        client.post(f"/api/v1/messages/{cid}/retry", json={"replacement_raw": "{}"}).status_code
        == 409
    )
    assert client.post(f"/api/v1/messages/{cid}/retry").status_code == 202
    process(cid, 0, erp_client)
    assert client.get("/api/v1/messages/" + cid).json()["status"] == "VALIDATED"
    drain()
    assert client.get("/api/v1/messages/" + cid).json()["status"] == "COMPLETED"


def test_retry_limit(client):
    cid = client.post("/api/v1/orders", content="{}").json()["correlation_id"]
    for _ in range(config.MAX_RETRIES):
        assert (
            client.post(f"/api/v1/messages/{cid}/retry", json={"replacement_raw": "{}"}).status_code
            == 422
        )
    assert (
        client.post(f"/api/v1/messages/{cid}/retry", json={"replacement_raw": "{}"}).status_code
        == 409
    )


def test_broker_outage_retains_outbox(client, order):
    cid = client.post("/api/v1/orders", json=order).json()["correlation_id"]
    with pytest.raises(ConnectionError):
        dispatch_once(ConfirmingChannel(fail=True))
    with Session() as s:
        assert s.scalar(select(Outbox)).published_at is None
        assert s.get(Message, cid).status == "VALIDATED"
    drain()
    assert client.get("/api/v1/messages/" + cid).json()["status"] == "COMPLETED"


def test_erp_idempotent_http(client, order):
    cid = client.post("/api/v1/orders", json=order).json()["correlation_id"]
    assert erp_client(cid, order) == erp_client(cid, order)
    changed = dict(order, currency="USD")
    with pytest.raises(httpx.HTTPStatusError):
        erp_client(cid, changed)


def test_filters_pagination_auth_and_missing(client, order, monkeypatch):
    cid = client.post("/api/v1/orders", json=order).json()["correlation_id"]
    trace = client.get("/api/v1/messages/" + cid).json()
    day = trace["received_at"][:10]
    assert (
        client.get(
            f"/api/v1/messages?source=JSON&customer=NORDIC-001&status=VALIDATED&date={day}"
        ).json()["total"]
        == 1
    )
    assert client.get("/api/v1/messages?source=EDI").json()["total"] == 0
    assert client.get("/api/v1/messages?offset=1").json()["items"] == []
    assert client.get("/api/v1/messages?limit=101").status_code == 422
    assert client.get("/api/v1/messages/missing").status_code == 404
    monkeypatch.setattr(config, "API_KEY", "test-key")
    assert client.get("/api/v1/messages").status_code == 401
    assert client.get("/api/v1/messages", headers={"X-API-Key": "test-key"}).status_code == 200


def test_acknowledgement(order):
    ack = acknowledgement(order, "ERP-1", "CID-1", "JSON")
    assert ack == {
        "correlation_id": "CID-1",
        "external_order_id": order["external_order_id"],
        "erp_order_id": "ERP-1",
        "status": "ACCEPTED",
    }


def test_limits_and_dashboard(client):
    assert client.post("/api/v1/orders", content="x" * 262145).status_code == 413
    assert client.post("/api/v1/orders", content=b"\xff").status_code == 400
    assert "Atlas Integration Monitor" in client.get("/").text


def test_health_reports_broker_failure(client, monkeypatch):
    def unavailable():
        raise ConnectionError()

    monkeypatch.setattr("app.main.connect", unavailable)
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"application": "ok", "database": "ok", "broker": "down"}


@pytest.mark.parametrize(
    "change",
    [
        "zero_quantity",
        "negative_price",
        "duplicate_line",
        "delivery_before_order",
        "missing_customer",
        "unknown_field",
    ],
)
def test_business_constraints(client, order, change):
    if change == "zero_quantity":
        order["items"][0]["quantity"] = "0"
    elif change == "negative_price":
        order["items"][0]["unit_price"] = "-1"
    elif change == "duplicate_line":
        order["items"][1]["line_number"] = 1
    elif change == "delivery_before_order":
        order["requested_delivery_date"] = "2026-09-01"
    elif change == "missing_customer":
        del order["customer_id"]
    else:
        order["uncontracted_field"] = "value"
    assert client.post("/api/v1/orders", json=order).status_code == 422


def test_missing_mandatory_segment():
    raw = Path("examples/valid_order.edi").read_text()
    raw = raw.replace("NAD+BY+NORDIC-001'\n", "").replace("UNT+12+1", "UNT+11+1")
    with pytest.raises(ValueError, match="Missing mandatory"):
        parse_edi(raw)


def test_multiple_edi_lines():
    raw = (
        Path("examples/valid_order.edi")
        .read_text()
        .replace(
            "UNT+12+1", "LIN+2++ATLAS-200:SA'IMD+F+Cloth case'QTY+21:4:EA'PRI+AAA:18.75'UNT+16+1"
        )
    )
    assert len(map_order(raw, "EDI").items) == 2


def test_worker_crash_after_erp_commit_replays_safely(client, order):
    cid = client.post("/api/v1/orders", json=order).json()["correlation_id"]
    dispatch_once(ConfirmingChannel())

    def crash_after_commit(correlation_id, canonical):
        erp_client(correlation_id, canonical)
        raise RuntimeError("Simulated worker crash after ERP commit")

    with pytest.raises(RuntimeError):
        process(cid, 0, crash_after_commit)
    assert client.get("/api/v1/messages/" + cid).json()["status"] == "QUEUED"
    process(cid, 0, erp_client)
    with Session() as session:
        assert session.scalar(select(func.count()).select_from(ERPOrder)) == 1
    assert client.get("/api/v1/messages/" + cid).json()["status"] == "COMPLETED"


@pytest.mark.parametrize("status,retryable", [(503, True), (429, True), (400, False), (401, False)])
def test_erp_http_error_classification(client, order, status, retryable):
    cid = client.post("/api/v1/orders", json=order).json()["correlation_id"]

    def fail_http(*args):
        response = httpx.Response(
            status, request=httpx.Request("POST", "http://erp/internal/erp/orders")
        )
        response.raise_for_status()

    process(cid, 0, fail_http)
    error = client.get("/api/v1/messages/" + cid).json()["error"]
    assert error["retryable"] == retryable
    assert error["code"] == "ERP_REJECTED"


def test_openapi_documents_canonical_contract(client):
    schema = client.get("/openapi.json").json()
    body = schema["paths"]["/api/v1/orders"]["post"]["requestBody"]["content"]["application/json"][
        "schema"
    ]
    assert body["$ref"] == "#/components/schemas/CanonicalPurchaseOrder"
    assert "items" in schema["components"]["schemas"]["CanonicalPurchaseOrder"]["required"]
    assert "Item" in schema["components"]["schemas"]
