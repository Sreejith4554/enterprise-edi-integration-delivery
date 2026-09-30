"""Generate local demo credentials without overwriting existing configuration."""

import secrets
from pathlib import Path

path = Path(".env")
with path.open("x") as file:
    for key in ("POSTGRES_PASSWORD", "RABBITMQ_PASSWORD", "INTERNAL_API_KEY"):
        file.write(f"{key}={secrets.token_hex(24)}\n")
    file.write("API_KEY=\nMAX_RETRIES=3\nERP_FAIL_MODE=false\n")
path.chmod(0o600)
print("Created .env with unique local demo credentials")
