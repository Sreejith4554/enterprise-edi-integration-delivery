"""Live HTTP smoke against the real Compose stack; optional controlled ERP outage."""

import argparse
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://localhost:8000")
parser.add_argument("--chaos", action="store_true", help="Stop/restart ERP using Docker Compose")
args = parser.parse_args()
client = httpx.Client(
    base_url=args.base_url, headers={"X-API-Key": os.getenv("API_KEY", "")}, timeout=15
)
run = uuid.uuid4().hex[:10]
results = []


def record(check, trace=None):
    results.append(
        {"check": check, "result": "PASS", "correlation_id": trace and trace["correlation_id"]}
    )
    print(check + ": PASS", flush=True)


def wait(cid, status):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        response = client.get("/api/v1/messages/" + cid)
        response.raise_for_status()
        trace = response.json()
        if trace["status"] == status:
            return trace
        if trace["status"] == "FAILED" and status != "FAILED":
            raise AssertionError(trace)
        time.sleep(0.5)
    raise AssertionError(f"{cid} did not reach {status}")


health = client.get("/health")
health.raise_for_status()
assert health.json() == {"application": "ok", "database": "ok", "broker": "ok"}
record("API, PostgreSQL, RabbitMQ health")
order = json.loads(Path("examples/valid_order.json").read_text())
order["external_order_id"] = "SMOKE-" + run
response = client.post("/api/v1/orders", json=order)
assert response.status_code == 202, response.text
trace = wait(response.json()["correlation_id"], "COMPLETED")
assert trace["canonical"]["items"][0]["unit_price"] == "24.50"
assert trace["erp_order_id"] and trace["acknowledgement"]["status"] == "ACCEPTED"
assert {"RECEIVED", "VALIDATED", "QUEUED", "PROCESSING", "COMPLETED"} <= {
    s["status"] for s in trace["processing_steps"]
}
record("JSON → outbox → RabbitMQ → worker → ERP HTTP → acknowledgement", trace)
assert client.post("/api/v1/orders", json=order).status_code == 409
record("Duplicate order rejected")
edi = Path("examples/valid_order.edi").read_text().replace("PO-EDI-1001", "EDI-" + run)
response = client.post("/api/v1/edi/orders", content=edi, headers={"Content-Type": "text/plain"})
assert response.status_code == 202, response.text
trace = wait(response.json()["correlation_id"], "COMPLETED")
assert "ORDRSP:D:96A:UN" in trace["acknowledgement"]["edi"]
record("EDI parser, canonical mapping and order response", trace)
response = client.post("/api/v1/edi/orders", content=Path("examples/invalid_order.edi").read_text())
assert response.status_code == 422
record("Malformed EDI persisted", wait(response.json()["correlation_id"], "FAILED"))
bad = json.loads(Path("examples/invalid_order.json").read_text())
bad["external_order_id"] = "FIX-" + run
response = client.post("/api/v1/orders", json=bad)
assert response.status_code == 422
cid = response.json()["correlation_id"]
trace = wait(cid, "FAILED")
assert trace["error"]["code"] == "INVALID_MESSAGE"
bad["items"][0]["sku"] = "ATLAS-100"
assert (
    client.post(
        f"/api/v1/messages/{cid}/retry", json={"replacement_raw": json.dumps(bad)}
    ).status_code
    == 202
)
trace = wait(cid, "COMPLETED")
assert trace["retry_count"] == 1 and any(
    s["status"] == "CORRECTED" for s in trace["processing_steps"]
)
record("Business failure, correction, retry and audit preservation", trace)
if args.chaos:
    subprocess.run(["docker", "compose", "stop", "erp"], check=True)
    try:
        order["external_order_id"] = "OUTAGE-" + run
        response = client.post("/api/v1/orders", json=order)
        assert response.status_code == 202
        cid = response.json()["correlation_id"]
        trace = wait(cid, "FAILED")
        assert trace["error"]["retryable"]
        record("ERP outage captured as retryable failure", trace)
    finally:
        subprocess.run(["docker", "compose", "start", "erp"], check=True)
    # Probe readiness inside the actual ERP container before requesting the retry.
    for attempt in range(30):
        probe = subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "erp",
                "python",
                "-c",
                "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')",
            ],
            capture_output=True,
        )
        if probe.returncode == 0:
            break
        time.sleep(1)
    else:
        raise AssertionError("ERP failed to restart")
    assert client.post(f"/api/v1/messages/{cid}/retry").status_code == 202
    record("ERP recovery and retry completed", wait(cid, "COMPLETED"))
assert client.get("/api/v1/messages?source=EDI&limit=2").json()["total"] >= 1
assert client.get("/").status_code == 200
record("History filters and dashboard served")
Path("verification-local.json").write_text(json.dumps(results, indent=2) + "\n")
