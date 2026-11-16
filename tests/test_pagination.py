from typing import Annotated

from fastapi import Query
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Integer, column, select, values

from app.core.pagination import PageParams, order_columns, paginate
from app.main import create_app


async def test_pagination_http_bounds(settings):
    app = create_app(settings)

    @app.get("/test-page")
    async def page(params: Annotated[PageParams, Query()]):
        order_columns(params, {"id": column("id")}, "id", column("id"))
        return params

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for query in ("page=0", "page_size=101", "page_size=0", "sort=secret"):
            assert (await client.get(f"/test-page?{query}")).status_code == 422
        assert (await client.get("/test-page")).json() == {"page": 1, "page_size": 20, "sort": None}


async def test_stable_scoped_pagination(database):
    source = values(column("id", Integer), column("group", Integer), name="v").data(
        [(1, 1), (2, 1), (3, 1), (4, 2)]
    )
    statement = select(source.c.id).where(source.c.group == 1)
    async with database.sessions() as session:
        first = await paginate(
            session,
            statement,
            PageParams(page_size=2),
            {"group": source.c.group},
            "group",
            source.c.id,
        )
        second = await paginate(
            session,
            statement,
            PageParams(page=2, page_size=2),
            {"group": source.c.group},
            "group",
            source.c.id,
        )
    assert first == {"items": [1, 2], "total": 3, "page": 1, "page_size": 2}
    assert second["items"] == [3]
