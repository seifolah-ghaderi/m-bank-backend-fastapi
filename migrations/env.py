import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings
from app.models import Base


def configure(connection):
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


async def migrate():
    settings = Settings()
    url = settings.migration_database_url or settings.database_url
    engine = create_async_engine(url.get_secret_value())
    async with engine.connect() as connection:
        await connection.run_sync(configure)
    await engine.dispose()


asyncio.run(migrate())
