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


async def load_references(session, rows):
    city_names, occupation_names = set(), set()
    for _, values, error in rows:
        if error is None:
            if isinstance(name := values.get("city"), str):
                city_names.add(normalize_text(name).lower())
            if (name := values.get("occupation")) is not None:
                occupation_names.add(search_key(name))

    # Scope the maps and row locks to this transaction so later chunks see directory edits.
    cities, occupations = {}, {}
    if city_names:
        city_key = func.lower(City.name)
        result = await session.execute(
            select(city_key, City.id, City.is_active)
            .where(city_key.in_(city_names), City.deleted_at.is_(None))
            .order_by(City.id)
            .with_for_update(read=True)
        )
        cities = {key: (city_id, active) for key, city_id, active in result}
    if occupation_names:
        result = await session.execute(
            select(Occupation.name_key, Occupation.id)
            .where(Occupation.name_key.in_(occupation_names), Occupation.is_active)
            .order_by(Occupation.id)
            .with_for_update(read=True)
        )
        occupations = dict(result.all())
    return cities, occupations


def resolve_fields(values, cities, occupations):
    name = values.get("city")
    if name is None:
        raise row_error("missing_required", "city")
    if not isinstance(name, str):
        raise row_error("invalid_city", "city")
    city = cities.get(normalize_text(name).lower())
    if city is None:
        raise row_error("unknown_city", "city")
    city_id, active = city
    if not active:
        raise row_error("inactive_city", "city")

    name = values.get("occupation")
    occupation_id = occupations.get(search_key(name)) if name is not None else None
    warnings = ["unknown_occupation"] if name is not None and occupation_id is None else []
    return lead_fields(values, city_id, occupation_id), warnings


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


async def load_existing(session, candidates):
    if not candidates:
        return {}, {}
    mobiles = {fields.mobile for fields, _ in candidates.values()}
    codes = {fields.national_code for fields, _ in candidates.values() if fields.national_code}
    match = Lead.mobile.in_(mobiles)
    if codes:
        match = or_(match, Lead.national_code.in_(codes))
    result = await session.execute(
        select(Lead.id, Lead.mobile, Lead.national_code, Lead.city_id).where(match)
    )
    matches = result.all()
    return (
        {lead.mobile: lead for lead in matches},
        {lead.national_code: lead for lead in matches if lead.national_code},
    )


def match_existing(fields, by_mobile, by_code):
    lead = by_mobile.get(fields.mobile)
    code_match = by_code.get(fields.national_code)
    if code_match is not None and (lead is None or lead.id != code_match.id):
        raise row_error("identity_conflict", "mobile")
    if lead is None:
        return False
    if fields.national_code and lead.national_code not in (None, fields.national_code):
        raise row_error("identity_conflict", "national_code")
    if lead.city_id != fields.city_id:
        raise row_error("city_mismatch", "city")
    return True


async def insert_candidates(session, actor, import_id, candidates, outcomes):
    if not candidates:
        return
    result = await session.execute(
        insert(Lead)
        .values(
            [
                dict(fields.model_dump(), created_by=actor.id, updated_by=actor.id)
                for fields, _ in candidates.values()
            ]
        )
        .on_conflict_do_nothing()
        .returning(Lead.mobile, Lead.id)
    )
    inserted = dict(result.all())
    conflicts = {}
    for number, (fields, warnings) in candidates.items():
        if (lead_id := inserted.get(fields.mobile)) is None:
            conflicts[number] = (fields, warnings)
            continue
        record(
            session,
            actor,
            "create",
            "leads",
            lead_id,
            after={"city_id": fields.city_id, "import_id": import_id},
        )
        outcomes[number] = ("created", None, warnings)

    # Manual creation can claim an identity between the lookup and insert.
    references = await load_existing(session, conflicts)
    for number, (fields, warnings) in conflicts.items():
        try:
            if not match_existing(fields, *references):
                raise row_error("identity_conflict", "mobile")
        except DomainError as error:
            outcomes[number] = ("failed", error, [])
        else:
            outcomes[number] = ("unchanged", None, warnings)


async def import_leads(session, actor, import_id, rows):
    cities, occupations = await load_references(session, rows)
    outcomes, candidates = {}, {}
    for number, values, error in rows:
        try:
            if error is not None:
                raise error
            candidates[number] = resolve_fields(values, cities, occupations)
        except DomainError as rejection:
            outcomes[number] = ("failed", rejection, [])

    references = await load_existing(session, candidates)
    new_leads = {}
    for number, (fields, warnings) in candidates.items():
        try:
            if match_existing(fields, *references):
                outcomes[number] = ("unchanged", None, warnings)
            else:
                new_leads[number] = (fields, warnings)
        except DomainError as rejection:
            outcomes[number] = ("failed", rejection, [])

    await insert_candidates(session, actor, import_id, new_leads, outcomes)
    return [(number, *outcomes[number]) for number, _, _ in rows]


async def import_lead(session, actor, import_id, values):
    [(_, outcome, error, warnings)] = await import_leads(
        session, actor, import_id, [(0, values, None)]
    )
    if error is not None:
        raise error
    return outcome, warnings
