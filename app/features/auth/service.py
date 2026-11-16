import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, update

from app.core import dates
from app.core.audit import record
from app.core.deps import eligible
from app.core.errors import DomainError, Rejected
from app.core.lifecycle import invalidate_sessions, lock_user
from app.core.presentation import user_detail
from app.core.security import (
    DUMMY_HASH,
    access_token,
    hasher,
    keyed_digest,
    password_policy,
    token_hash,
    verify_password,
)
from app.core.text import digits, masked_mobile
from app.models import LoginChallenge, RefreshToken, User


@dataclass
class Delivery:
    challenge_id: UUID
    user_id: UUID
    mobile: str
    code: str


def rejection(status, code, **details):
    return Rejected(DomainError(status, code, details=[details] if details else []))


async def new_challenge(session, user, request, settings, adapter, previous=None):
    now = dates.now()
    latest = await session.scalar(
        select(LoginChallenge)
        .where(LoginChallenge.user_id == user.id)
        .order_by(LoginChallenge.last_sent_at.desc())
        .limit(1)
    )
    if (
        latest
        and (latest.last_sent_at + timedelta(seconds=settings.sms_resend_cooldown_seconds)) > now
    ):
        remaining = max(
            1,
            int(
                (
                    latest.last_sent_at
                    + timedelta(seconds=settings.sms_resend_cooldown_seconds)
                    - now
                ).total_seconds()
            ),
        )
        return rejection(429, "sms_rate_limited", retry_after_seconds=remaining)
    attempts = previous.failed_attempts if previous else 0
    expiry = (
        previous.expires_at if previous else now + timedelta(seconds=settings.sms_code_ttl_seconds)
    )
    await session.execute(
        update(LoginChallenge)
        .where(
            LoginChallenge.user_id == user.id,
            LoginChallenge.consumed_at.is_(None),
            LoginChallenge.invalidated_at.is_(None),
        )
        .values(invalidated_at=now)
    )
    challenge_id, code = uuid4(), adapter.generate_code()
    challenge = LoginChallenge(
        id=challenge_id,
        user_id=user.id,
        mobile=user.mobile,
        code_digest=keyed_digest(
            settings.sms_digest_secret.get_secret_value(), f"{challenge_id}:{code}"
        ),
        created_at=now,
        expires_at=expiry,
        last_sent_at=now,
        failed_attempts=attempts,
        delivery_state="pending",
    )
    session.add(challenge)
    await session.flush()
    record(
        session,
        None,
        "sms_challenge_created",
        "login_challenges",
        challenge_id,
        after={"mobile": masked_mobile(user.mobile)},
        request=request,
    )
    return Delivery(challenge_id, user.id, user.mobile, code)


async def prepare_login(session, body, request, settings, adapter):
    candidate = await session.scalar(
        select(User)
        .where(User.mobile == body.mobile)
        .order_by(User.deleted_at.is_(None).desc())
        .limit(1)
    )
    if candidate is None:
        verify_password(body.password, DUMMY_HASH)
        record(
            session,
            None,
            "login_failed",
            "users",
            after={"mobile": masked_mobile(body.mobile)},
            request=request,
        )
        return rejection(401, "invalid_credentials")
    user = await lock_user(session, candidate.id)
    eligible(user)
    now = dates.now()
    if user.locked_until:
        if user.locked_until > now:
            return rejection(
                423,
                "account_locked",
                retry_after_seconds=max(1, int((user.locked_until - now).total_seconds())),
            )
        user.failed_login_count, user.locked_until = 0, None
    if not verify_password(body.password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= 5:
            user.locked_until = now + timedelta(minutes=15)
        record(
            session,
            None,
            "login_failed",
            "users",
            after={"mobile": masked_mobile(user.mobile)},
            request=request,
        )
        return rejection(401, "invalid_credentials")
    user.failed_login_count, user.locked_until = 0, None
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hasher.hash(body.password)
    return await new_challenge(session, user, request, settings, adapter)


async def locked_challenge(session, challenge_id):
    candidate = await session.get(LoginChallenge, challenge_id)
    if candidate is None:
        raise DomainError(401, "invalid_sms_code")
    user = await lock_user(session, candidate.user_id)
    challenge = await session.scalar(
        select(LoginChallenge)
        .where(LoginChallenge.id == challenge_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    eligible(user)
    if (
        challenge.invalidated_at is not None
        or challenge.consumed_at is not None
        or challenge.expires_at <= dates.now()
        or challenge.mobile != user.mobile
        or challenge.delivery_state != "sent"
    ):
        raise DomainError(401, "invalid_sms_code")
    return user, challenge


async def prepare_resend(session, challenge_id, request, settings, adapter):
    user, challenge = await locked_challenge(session, challenge_id)
    return await new_challenge(session, user, request, settings, adapter, challenge)


async def finalize_delivery(session, delivery, success, request, settings):
    user = await lock_user(session, delivery.user_id)
    challenge = await session.scalar(
        select(LoginChallenge)
        .where(LoginChallenge.id == delivery.challenge_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        challenge is None
        or challenge.invalidated_at is not None
        or challenge.consumed_at is not None
        or challenge.expires_at <= dates.now()
        or user.deleted_at is not None
        or not user.is_active
        or user.mobile != challenge.mobile
    ):
        return rejection(401, "invalid_sms_code")
    challenge.delivery_state = "sent" if success else "failed"
    if not success:
        challenge.invalidated_at = dates.now()
    record(
        session,
        None,
        "sms_sent" if success else "sms_failed",
        "login_challenges",
        challenge.id,
        after={"mobile": masked_mobile(user.mobile)},
        request=request,
    )
    if not success:
        return rejection(503, "sms_unavailable")
    return {
        "challenge_id": str(challenge.id),
        "destination": masked_mobile(user.mobile),
        "expires_in": max(0, int((challenge.expires_at - dates.now()).total_seconds())),
        "resend_after_seconds": settings.sms_resend_cooldown_seconds,
    }


async def issue_session(session, user, request, settings):
    raw = secrets.token_urlsafe(32)
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=token_hash(raw),
            expires_at=dates.now() + timedelta(days=settings.refresh_token_days),
            user_agent=request.headers.get("user-agent", "")[:255],
            ip=request.client.host[:45] if request.client else None,
        )
    )
    return {
        "access_token": access_token(settings, user),
        "token_type": "bearer",
        "expires_in": settings.access_token_minutes * 60,
        "user": await user_detail(session, user),
    }, raw


async def verify_sms(session, body, request, settings):
    user, challenge = await locked_challenge(session, body.challenge_id)
    expected = keyed_digest(
        settings.sms_digest_secret.get_secret_value(), f"{challenge.id}:{digits(body.code)}"
    )
    if challenge.failed_attempts >= settings.sms_max_attempts:
        return rejection(401, "invalid_sms_code")
    if not hmac.compare_digest(expected, challenge.code_digest):
        challenge.failed_attempts += 1
        if challenge.failed_attempts >= settings.sms_max_attempts:
            challenge.invalidated_at = dates.now()
        record(
            session,
            None,
            "sms_verification_failed",
            "login_challenges",
            challenge.id,
            after={"mobile": masked_mobile(user.mobile)},
            request=request,
        )
        return rejection(401, "invalid_sms_code")
    challenge.consumed_at = dates.now()
    user.last_login_at = dates.now()
    record(session, user, "sms_verified", "login_challenges", challenge.id, request=request)
    record(session, user, "login", "users", user.id, request=request)
    await session.flush()
    return await issue_session(session, user, request, settings)


async def refresh(session, raw, request, settings):
    candidate = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash(raw))
    )
    if candidate is None:
        raise DomainError(401, "invalid_credentials")
    user = await lock_user(session, candidate.user_id)
    eligible(user)
    token = await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.id == candidate.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if token.revoked_at:
        await invalidate_sessions(session, user.id)
        record(session, user, "refresh_token_reuse", "users", user.id, request=request)
        return rejection(401, "invalid_credentials")
    if token.expires_at <= dates.now():
        raise DomainError(401, "token_expired")
    token.revoked_at = dates.now()
    return await issue_session(session, user, request, settings)


async def change_password(session, user_id, body, raw, request):
    user = await lock_user(session, user_id)
    eligible(user)
    if not verify_password(body.current_password, user.password_hash):
        raise DomainError(401, "invalid_credentials")
    password_policy(body.new_password, user.mobile)
    keep = None
    if raw:
        token = await session.scalar(
            select(RefreshToken).where(
                RefreshToken.user_id == user.id,
                RefreshToken.token_hash == token_hash(raw),
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > dates.now(),
            )
        )
        if token is None:
            raise DomainError(401, "invalid_credentials")
        keep = token.token_hash
    await invalidate_sessions(session, user.id, keep_hash=keep)
    user.password_hash = hasher.hash(body.new_password)
    user.must_change_password = False
    user.password_changed_at = dates.now()
    record(session, user, "change_password", "users", user.id, request=request)


async def logout(session, user, raw, request):
    user = await lock_user(session, user.id)
    eligible(user)
    if raw:
        await session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user.id,
                RefreshToken.token_hash == token_hash(raw),
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=dates.now())
        )
    record(session, user, "logout", "users", user.id, request=request)
