from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.errors import DomainError


class PageParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    sort: str | None = None


def order_columns(params: PageParams, allowed: dict, default: str, tie_breaker):
    sort = params.sort or default
    key = sort.removeprefix("-")
    if key not in allowed:
        raise DomainError(422, "invalid_sort")
    column = allowed[key]
    return [column.desc() if sort.startswith("-") else column.asc(), tie_breaker.asc()]


async def paginate(session, statement, params, allowed, default, tie_breaker):
    order = order_columns(params, allowed, default, tie_breaker)
    total = await session.scalar(
        select(func.count()).select_from(statement.order_by(None).subquery())
    )
    rows = list(
        await session.scalars(
            statement.order_by(*order)
            .offset((params.page - 1) * params.page_size)
            .limit(params.page_size)
        )
    )
    return {"items": rows, "total": total, "page": params.page, "page_size": params.page_size}
