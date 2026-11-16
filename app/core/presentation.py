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
