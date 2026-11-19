from collections import Counter

from pydantic import ValidationError
from sqlalchemy import func, or_, select

from app.core.errors import DomainError
from app.core.lifecycle import lifecycle_actor
from app.features.crm_imports import history
from app.features.org.service import create_entity
from app.models import Branch, City
from app.schemas.org import BranchCreate, CityCreate, branch_code


async def resolve_city(session, actor, request, city_data):
    city = await session.scalar(
        select(City).where(
            func.lower(City.name) == city_data.name.lower(), City.deleted_at.is_(None)
        )
    )
    if city is None:
        created = await create_entity(session, City, city_data, actor, request)
        return created.id, "city_created"
    if not city.is_active:
        raise DomainError(422, "inactive_city", details={"column": "city"})
    return city.id, "city_unchanged"


def first_branch_code(code, seen):
    if code is None:
        raise DomainError(422, "missing_required", details={"column": "branch_code"})
    try:
        code = branch_code(code)
    except ValueError:
        raise DomainError(422, "invalid_branch_code", details={"column": "branch_code"}) from None
    if code in seen:
        raise DomainError(422, "duplicate_in_file", details={"column": "branch_code"})
    seen.add(code)
    return code


async def import_branch(session, actor, request, code, name, city_id):
    if not isinstance(name, str):
        raise DomainError(422, "invalid_branch_name", details={"column": "branch_name"})
    try:
        body = BranchCreate(city_id=city_id, code=code, name=name)
    except ValidationError:
        raise DomainError(422, "invalid_branch_name", details={"column": "branch_name"}) from None

    name_match = (Branch.city_id == city_id) & (func.lower(Branch.name) == body.name.lower())
    matches = (
        await session.scalars(
            select(Branch).where(Branch.deleted_at.is_(None), or_(Branch.code == code, name_match))
        )
    ).all()
    if not matches:
        await create_entity(session, Branch, body, actor, request)
        return "created"
    branch = matches[0]
    if (
        len(matches) != 1
        or branch.code != code
        or branch.city_id != city_id
        or branch.name.lower() != body.name.lower()
    ):
        raise DomainError(409, "branch_conflict", details={"column": "branch_code"})
    if not branch.is_active:
        raise DomainError(422, "inactive_branch", details={"column": "branch_code"})
    return "unchanged"


async def process(session, actor, request, job, sheet):
    actor = await lifecycle_actor(session, actor, "supervisor")
    counts, city_cache, cities_by_row = Counter(), {}, {}
    for number, cells in sheet.rows:
        name = sheet.values(cells, {"city"}).get("city")
        if name is None:
            cities_by_row[number] = DomainError(422, "missing_required", details={"column": "city"})
            continue
        if not isinstance(name, str):
            cities_by_row[number] = DomainError(422, "invalid_city", details={"column": "city"})
            continue
        try:
            data = CityCreate(name=name)
        except ValidationError:
            cities_by_row[number] = DomainError(422, "invalid_city", details={"column": "city"})
            continue
        key = data.name.lower()
        if key not in city_cache:
            try:
                city_id, outcome = await resolve_city(session, actor, request, data)
                city_cache[key] = city_id
                counts[outcome] += 1
            except DomainError as error:
                city_cache[key] = error
                counts["city_failed"] += 1
        cities_by_row[number] = city_cache[key]

    codes = set()
    for number, cells in sheet.rows:
        city_id = cities_by_row[number]
        try:
            values = sheet.values(cells)
            code = first_branch_code(values.get("branch_code"), codes)
            if isinstance(city_id, DomainError):
                raise city_id
            outcome = await import_branch(
                session, actor, request, code, values.get("branch_name"), city_id
            )
        except DomainError as error:
            outcome = "failed"
            history.add_outcome(session, job, number, outcome, error)
        else:
            history.add_outcome(session, job, number, outcome)
        counts[outcome] += 1
    history.update_counts(job, counts)
    history.finish(job)
