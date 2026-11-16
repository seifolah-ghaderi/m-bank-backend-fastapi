import hashlib
import hmac
import secrets
import string
from datetime import timedelta
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

from app.core import dates
from app.core.errors import DomainError
from app.core.text import digits

hasher = PasswordHasher()
DUMMY_HASH = hasher.hash("DummyPass123ForTiming")


def password_policy(password: str, mobile: str):
    if not (
        8 <= len(password) <= 128
        and any(c.isalpha() for c in password)
        and any(c.isdigit() for c in password)
        and digits(password) != mobile
    ):
        raise DomainError(422, "invalid_password")


def verify_password(password: str, encoded: str) -> bool:
    try:
        return hasher.verify(encoded, password)
    except VerificationError:
        return False


def temporary_password() -> str:
    while True:
        value = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(10))
        if any(c.isalpha() for c in value) and any(c.isdigit() for c in value):
            return value


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def keyed_digest(secret: str, value: str) -> str:
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def access_token(settings, user) -> str:
    now = dates.now()
    return jwt.encode(
        {
            "sub": str(user.id),
            "role": user.role,
            "branch_id": str(user.branch_id) if user.branch_id else None,
            "jti": str(uuid4()),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=settings.access_token_minutes)).timestamp()),
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def decode_access(settings, raw: str) -> UUID:
    try:
        payload = jwt.decode(
            raw,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            options={
                "require": ["sub", "role", "jti", "iat", "exp"],
                "verify_exp": False,
                "verify_iat": False,
            },
        )
        now = dates.now().timestamp()
        if "branch_id" not in payload:
            raise ValueError("Missing branch claim")
        if not isinstance(payload["exp"], (int, float)) or payload["exp"] <= now:
            raise DomainError(401, "token_expired")
        if not isinstance(payload["iat"], (int, float)) or payload["iat"] > now:
            raise ValueError("Invalid issue time")
        UUID(payload["jti"])
        return UUID(payload["sub"])
    except DomainError:
        raise
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        raise DomainError(401, "invalid_credentials") from None
