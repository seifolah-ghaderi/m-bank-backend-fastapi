from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert

from app.core.audit import record
from app.core.errors import DomainError
from app.core.text import mobile, national_code, normalize_text, search_key
from app.models import City, Lead, Occupation
from app.schemas.marketing import LeadFields


def row_error(code, column):
    return DomainError(422, code, details={"column": column})


def lead_rows(sheet):
    identity_fields = {"mobile": mobile, "national_code": national_code}
    other_fields = set(sheet.columns) - identity_fields.keys()
    seen = {column: set() for column in identity_fields}
    for number, cells in sheet.rows:
        values = sheet.values(cells, other_fields)
        error = None
        for column, validate in identity_fields.items():
            try:
                value = sheet.values(cells, {column}).get(column)
                if value is None:
                    if column == "mobile":
                        raise row_error("missing_required", column)
                    continue
                identity = validate(value)
                if identity in seen[column]:
                    raise row_error("duplicate_in_file", column)
                seen[column].add(identity)
                values[column] = identity
            except ValueError as invalid:
                error = error or row_error(str(invalid), column)
            except DomainError as invalid:
                error = error or invalid
        yield number, values if error is None else None, error


async def city_id_for(session, name):
    if name is None:
        raise row_error("missing_required", "city")
    if not isinstance(name, str):
        raise row_error("invalid_city", "city")
    city = await session.scalar(
        select(City)
        .where(func.lower(City.name) == normalize_text(name).lower(), City.deleted_at.is_(None))
        .with_for_update(read=True)
    )
    if city is None:
        raise row_error("unknown_city", "city")
    if not city.is_active:
        raise row_error("inactive_city", "city")
    return city.id


async def resolve_occupation(session, name):
    if name is None:
        return None, []
    occupation_id = await session.scalar(
        select(Occupation.id)
        .where(Occupation.name_key == search_key(name), Occupation.is_active)
        .with_for_update(read=True)
    )
    return occupation_id, [] if occupation_id else ["unknown_occupation"]


def lead_fields(values, city_id, occupation_id):
    for column in ("first_name", "last_name"):
        if values.get(column) is None:
            raise row_error("missing_required", column)
        if not isinstance(values[column], str):
            raise row_error("invalid_field", column)
    source_details = [
        f"{label}: {values[field]}"
        for label, field in (("نام فروشگاه", "shop_name"), ("فعالیت", "activity"))
        if values.get(field) is not None
    ]
    if values.get("additional_info") is not None:
        raw_details = values["additional_info"]
        if not isinstance(raw_details, str):
            raise row_error("invalid_field", "additional_info")
        source_details.insert(0, raw_details)
    try:
        return LeadFields(
            city_id=city_id,
            occupation_id=occupation_id,
            additional_info="\n".join(source_details) or None,
            **{
                key: values[key]
                for key in (
                    "first_name",
                    "last_name",
                    "mobile",
                    "national_code",
                    "address",
                    "referrer",
                )
                if key in values
            },
        )
    except ValidationError as error:
        column = error.errors(include_input=False)[0]["loc"][0]
        raise row_error("invalid_field", column) from None


async def find_existing(session, fields):
    match = Lead.mobile == fields.mobile
    if fields.national_code:
        match = or_(match, Lead.national_code == fields.national_code)
    matches = (await session.scalars(select(Lead).where(match))).all()
    if not matches:
        return None
    lead = matches[0]
    if len(matches) != 1 or lead.mobile != fields.mobile:
        raise row_error("identity_conflict", "mobile")
    if fields.national_code and lead.national_code not in (None, fields.national_code):
        raise row_error("identity_conflict", "national_code")
    if lead.city_id != fields.city_id:
        raise row_error("city_mismatch", "city")
    return lead


async def import_lead(session, actor, import_id, values):
    city_id = await city_id_for(session, values.get("city"))
    occupation_id, warnings = await resolve_occupation(session, values.get("occupation"))
    fields = lead_fields(values, city_id, occupation_id)
    if await find_existing(session, fields):
        return "unchanged", warnings
    lead_id = await session.scalar(
        insert(Lead)
        .values(**fields.model_dump(), created_by=actor.id, updated_by=actor.id)
        .on_conflict_do_nothing()
        .returning(Lead.id)
    )
    if lead_id is None:
        # A concurrent import or manual creation may have claimed an identity.
        if await find_existing(session, fields):
            return "unchanged", warnings
        raise row_error("identity_conflict", "mobile")
    record(
        session,
        actor,
        "create",
        "leads",
        lead_id,
        after={"city_id": city_id, "import_id": import_id},
    )
    return "created", warnings
