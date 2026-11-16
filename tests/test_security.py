from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest

from app.core.errors import DomainError
from app.core.security import (
    access_token,
    decode_access,
    hasher,
    password_policy,
    temporary_password,
    token_hash,
    verify_password,
)


@pytest.mark.parametrize("password", ["short1", "abcdefgh", "12345678", "x" * 129])
def test_password_policy_rejects(password):
    with pytest.raises(DomainError):
        password_policy(password, "09123456789")


def test_hashing_and_generated_passwords():
    for _ in range(10):
        password = temporary_password()
        assert len(password) == 10
        password_policy(password, "09123456789")
    encoded = hasher.hash("ValidPass123")
    assert "argon2id" in encoded
    assert verify_password("ValidPass123", encoded)
    assert not verify_password("wrong", encoded)
    assert token_hash("refresh-secret") != "refresh-secret"


def test_jwt_validation(settings, clock):
    user = SimpleNamespace(id=uuid4(), role="supervisor", branch_id=None)
    raw = access_token(settings, user)
    assert decode_access(settings, raw) == user.id
    claims = jwt.decode(
        raw,
        settings.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        options={"verify_exp": False, "verify_iat": False},
    )
    assert isinstance(claims["exp"], int)
    for bad in (
        jwt.encode(claims, "wrong" * 10, algorithm="HS256"),
        jwt.encode(claims, "k" * 64, algorithm="HS384"),
    ):
        with pytest.raises(DomainError):
            decode_access(settings, bad)
    clock.advance(minutes=16)
    with pytest.raises(DomainError, match="token_expired"):
        decode_access(settings, raw)
