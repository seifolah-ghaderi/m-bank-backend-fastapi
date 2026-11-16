from sqlalchemy import text


async def test_real_postgresql(database):
    async with database.sessions() as session:
        assert await session.scalar(text("SELECT 1")) == 1
        version = await session.scalar(text("SHOW server_version"))
        assert version.startswith("16.")
