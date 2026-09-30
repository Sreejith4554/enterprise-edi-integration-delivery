"""Environment configuration; local-only defaults contain no credentials."""

import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./integration.db")
BROKER_URL = os.getenv("BROKER_URL", "amqp://localhost:5672/")
ERP_URL = os.getenv("ERP_URL", "http://localhost:8001")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")
API_KEY = os.getenv("API_KEY", "")
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
QUEUE = "integration.orders.v1"
