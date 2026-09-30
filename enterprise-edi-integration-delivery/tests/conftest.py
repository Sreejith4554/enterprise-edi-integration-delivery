"""Isolated SQLite tests; real Postgres/RabbitMQ are exercised by Compose smoke CI."""

import os
import tempfile
from pathlib import Path

_test_dir = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_test_dir.name) / "test.db")
os.environ["INTERNAL_API_KEY"] = "test-only-internal-key"
os.environ["API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app


@pytest.fixture(autouse=True)
def database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


@pytest.fixture
def order():
    import json

    return json.loads(Path("examples/valid_order.json").read_text())
