from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings
from app.core.db import Database
from app.core.errors import DomainError, install_handlers
from app.core.middleware import RequestContextMiddleware
from app.core.sms import SmsAdapter


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    production = settings.environment == "production"

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            await app.state.database.close()

    app = FastAPI(
        title="Bank Marketing CRM",
        version="0.1.0",
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.database = Database(settings.database_url.get_secret_value())
    app.state.sms = SmsAdapter(settings)
    install_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware, timezone=settings.app_timezone)

    from app.features.audit.router import router as audit_router
    from app.features.auth.router import router as auth_router
    from app.features.notifications.router import router as notifications_router
    from app.features.org.router import router as org_router
    from app.features.pos.router_devices import router as devices_router
    from app.features.pos.router_imports import router as imports_router
    from app.features.pos.router_settings import router as settings_router
    from app.features.pos.router_transactions import router as transactions_router
    from app.features.pos.router_visits import router as visits_router
    from app.features.reports.router import router as reports_router
    from app.features.users.router import router as users_router

    for router in (
        auth_router,
        org_router,
        users_router,
        audit_router,
        devices_router,
        transactions_router,
        settings_router,
        imports_router,
        notifications_router,
        visits_router,
        reports_router,
    ):
        app.include_router(router, prefix="/api/v1")

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/v1/health/ready")
    async def ready():
        from sqlalchemy import text

        try:
            async with app.state.database.sessions() as session:
                await session.execute(text("SELECT 1"))
        except Exception:
            raise DomainError(503, "not_ready") from None
        return {"status": "ready"}

    return app
