from app.models import Branch, City
from app.schemas.users import UserOut


async def user_detail(session, user):
    result = UserOut.model_validate(user).model_dump(mode="json")
    result["branch"] = None
    result["city"] = None
    if user.branch_id:
        branch = await session.get(Branch, user.branch_id)
        city = await session.get(City, branch.city_id)
        result["branch"] = {"id": str(branch.id), "code": branch.code, "name": branch.name}
        result["city"] = {"id": str(city.id), "name": city.name}
    return result


async def visit_out(session, visit):
    from sqlalchemy import select

    from app.models import PosTag, PosVisitTagLink
    from app.schemas.pos import PosVisitOut, SelectionSnapshotOut

    values = {key: getattr(visit, key) for key in PosVisitOut.model_fields if hasattr(visit, key)}
    values["selection_snapshot"] = SelectionSnapshotOut(
        **{key: getattr(visit, "snapshot_" + key) for key in SelectionSnapshotOut.model_fields}
    )
    values["tag_codes"] = list(
        await session.scalars(
            select(PosTag.code)
            .join(PosVisitTagLink, PosVisitTagLink.tag_id == PosTag.id)
            .where(PosVisitTagLink.pos_visit_id == visit.id, PosVisitTagLink.is_active.is_(True))
            .order_by(PosTag.code)
        )
    )
    return PosVisitOut(**values)
