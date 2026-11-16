"""Create a private local .env, refusing to replace existing configuration."""

import os
import secrets
from pathlib import Path

target = Path(__file__).resolve().parents[1] / ".env"
owner = secrets.token_hex(24)
runtime = secrets.token_hex(24)
values = {
    "DATABASE_URL": f"postgresql+asyncpg://crm_runtime:{runtime}@localhost:55432/crm",
    "MIGRATION_DATABASE_URL": f"postgresql+asyncpg://crm_owner:{owner}@localhost:55432/crm",
    "POSTGRES_DB": "crm",
    "POSTGRES_USER": "crm_owner",
    "POSTGRES_PASSWORD": owner,
    "RUNTIME_DB_PASSWORD": runtime,
    "JWT_SECRET": secrets.token_hex(32),
    "CSRF_SECRET": secrets.token_hex(32),
    "SMS_DIGEST_SECRET": secrets.token_hex(32),
    "ENVIRONMENT": "dev",
    "SMS_MODE": "fixed",
    "CORS_ORIGINS": '["http://localhost:5173"]',
}
with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as output:
    output.writelines(f"{key}={value}\n" for key, value in values.items())
print("Created private .env for local development; no secrets printed.")
