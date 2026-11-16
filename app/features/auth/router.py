import hmac

from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from app.core import dates
from app.core.db import transaction
from app.core.deps import CurrentUser, Session, eligible
from app.core.errors import DomainError, finish
from app.core.presentation import user_detail
from app.core.security import keyed_digest, token_hash
from app.core.sms import SmsDeliveryError
from app.features.auth import service
from app.models import RefreshToken, User
from app.schemas.auth import ChangePassword, Login, ResendSms, VerifySms

router = APIRouter(prefix="/auth")
COOKIE = "crm_refresh"


def origin_check(request):
    if request.headers.get("origin") not in request.app.state.settings.cors_origins:
        raise DomainError(403, "forbidden")


def csrf_value(request, raw):
    return keyed_digest(request.app.state.settings.csrf_secret.get_secret_value(), raw)


def csrf_check(request):
    raw = request.cookies.get(COOKIE)
    origin_check(request)
    if not raw or not hmac.compare_digest(
        csrf_value(request, raw), request.headers.get("x-csrf-token", "")
    ):
        raise DomainError(403, "forbidden")
    return raw


def set_session(response, request, raw):
    settings = request.app.state.settings
    response.set_cookie(
        COOKIE,
        raw,
        max_age=settings.refresh_token_days * 86400,
        httponly=True,
        secure=settings.environment != "dev",
        samesite="strict",
        path="/api/v1/auth",
    )
    response.headers["Cache-Control"] = "no-store"


async def deliver(request, prepare):
    database, settings, adapter = (
        request.app.state.database,
        request.app.state.settings,
        request.app.state.sms,
    )
    async with transaction(database) as session:
        delivery = finish(await prepare(session, settings, adapter))
    try:
        await adapter.send(delivery.mobile, delivery.code)
        success = True
    except SmsDeliveryError:
        success = False
    async with transaction(database) as session:
        return finish(
            await service.finalize_delivery(session, delivery, success, request, settings)
        )


@router.post("/login", status_code=202)
async def login(body: Login, request: Request, response: Response):
    origin_check(request)
    response.headers["Cache-Control"] = "no-store"
    return await deliver(
        request,
        lambda session, settings, adapter: service.prepare_login(
            session, body, request, settings, adapter
        ),
    )


@router.post("/resend-sms", status_code=202)
async def resend(body: ResendSms, request: Request, response: Response):
    origin_check(request)
    response.headers["Cache-Control"] = "no-store"
    return await deliver(
        request,
        lambda session, settings, adapter: service.prepare_resend(
            session, body.challenge_id, request, settings, adapter
        ),
    )


@router.post("/verify-sms")
async def verify(body: VerifySms, request: Request, response: Response, session: Session):
    origin_check(request)
    payload, raw = finish(
        await service.verify_sms(session, body, request, request.app.state.settings)
    )
    set_session(response, request, raw)
    payload["csrf_token"] = csrf_value(request, raw)
    return payload


@router.get("/csrf")
async def csrf(request: Request, response: Response, session: Session):
    origin_check(request)
    raw = request.cookies.get(COOKIE, "")
    token = await session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash(raw),
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > dates.now(),
        )
    )
    if token is None:
        raise DomainError(401, "invalid_credentials")
    eligible(await session.get(User, token.user_id))
    response.headers["Cache-Control"] = "no-store"
    return {"csrf_token": csrf_value(request, raw)}


@router.post("/refresh")
async def refresh(request: Request, response: Response, session: Session):
    raw = csrf_check(request)
    payload, replacement = finish(
        await service.refresh(session, raw, request, request.app.state.settings)
    )
    set_session(response, request, replacement)
    payload["csrf_token"] = csrf_value(request, replacement)
    return payload


@router.get("/me")
async def me(session: Session, user: CurrentUser):
    return await user_detail(session, user)


@router.post("/change-password", status_code=204)
async def change_password(
    body: ChangePassword, request: Request, session: Session, user: CurrentUser
):
    raw = csrf_check(request) if request.cookies.get(COOKIE) else None
    await service.change_password(session, user.id, body, raw, request)
    return Response(status_code=204)


@router.post("/logout", status_code=204)
async def logout(request: Request, session: Session, user: CurrentUser):
    raw = csrf_check(request) if request.cookies.get(COOKIE) else None
    await service.logout(session, user, raw, request)
    response = Response(status_code=204)
    response.delete_cookie(
        COOKIE,
        path="/api/v1/auth",
        secure=request.app.state.settings.environment != "dev",
        httponly=True,
        samesite="strict",
    )
    return response
