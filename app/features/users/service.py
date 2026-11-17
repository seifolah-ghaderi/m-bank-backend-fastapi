from sqlalchemy import func, or_, select, text

from app.core import dates
from app.core.audit import record, snapshot
from app.core.deps import eligible, require_roles, scope_for
from app.core.errors import DomainError
from app.core.lifecycle import active_branch, assigned_task_count, invalidate_sessions, lock_user
from app.core.pagination import paginate
from app.core.security import hasher, temporary_password
from app.core.text import search_key
from app.core.validation import validated_changes
from app.models import Branch, User
from app.schemas.users import UserCreated, UserOut


async def get_user(session, user_id, actor):
    require_roles(actor, "supervisor", "branch_manager")
    statement = scope_for(actor).apply(
        select(User).where(User.id == user_id, User.deleted_at.is_(None)), User
    )
    user = await session.scalar(statement)
    if user is None:
        raise DomainError(404, "not_found")
    return user


async def list_users(
    session, actor, params, branch_id=None, city_id=None, role=None, is_active=None, q=None
):
    require_roles(actor, "supervisor", "branch_manager")
    statement = scope_for(actor).apply(select(User).where(User.deleted_at.is_(None)), User)
    if branch_id:
        if actor.role != "supervisor" and branch_id != actor.branch_id:
            raise DomainError(403, "forbidden")
        statement = statement.where(User.branch_id == branch_id)
    if city_id:
        statement = statement.where(
            User.branch_id.in_(select(Branch.id).where(Branch.city_id == city_id))
        )
    if role:
        statement = statement.where(User.role == role)
    if is_active is not None:
        statement = statement.where(User.is_active == is_active)
    if q:
        q = search_key(q)
        statement = statement.where(
            or_(
                func.lower(User.first_name + " " + User.last_name).contains(q, autoescape=True),
                User.mobile.contains(q, autoescape=True),
                User.national_code.contains(q, autoescape=True),
            )
        )
    page = await paginate(
        session,
        statement,
        params,
        {
            "created_at": User.created_at,
            "first_name": User.first_name,
            "last_name": User.last_name,
            "mobile": User.mobile,
        },
        "-created_at",
        User.id,
    )
    page["items"] = [UserOut.model_validate(row) for row in page["items"]]
    return page


async def create_user(session, body, actor, request):
    values = body.model_dump()
    if values["role"] == "supervisor":
        if values["branch_id"] is not None:
            raise DomainError(422, "invalid_branch")
    else:
        await active_branch(session, values["branch_id"])
    password = temporary_password()
    user = User(
        **values, password_hash=hasher.hash(password), created_by=actor.id, updated_by=actor.id
    )
    session.add(user)
    await session.flush()
    record(session, actor, "create", "users", user.id, after=snapshot(user), request=request)
    return UserCreated(**UserOut.model_validate(user).model_dump(), temporary_password=password)


async def update_user(session, user_id, actor, request, body=None, action="update"):
    changes = (
        validated_changes(body, {"first_name", "last_name", "mobile", "role", "is_active"})
        if body
        else {}
    )
    # Serialize all administrative lifecycle writes before taking any user row locks.
    await session.execute(text("SELECT pg_advisory_xact_lock(72851901)"))
    actor = await lock_user(session, actor.id)
    eligible(actor)
    require_roles(actor, "supervisor")
    user = await lock_user(session, user_id)
    if user is None or user.deleted_at is not None:
        raise DomainError(404, "not_found")
    before = snapshot(user)
    final_role = changes.get("role", user.role)
    final_active = changes.get("is_active", user.is_active)
    if action == "deactivate":
        final_active = False
        changes["is_active"] = False
    elif action == "activate":
        final_active = True
        changes["is_active"] = True
    destructive = (
        action == "delete"
        or not final_active
        or final_role != user.role
        or ("branch_id" in changes and changes["branch_id"] != user.branch_id)
    )
    if user.id == actor.id and destructive:
        raise DomainError(409, "cannot_modify_self")
    if user.role == "employee" and destructive:
        count = await assigned_task_count(session, user.id)
        if count:
            raise DomainError(409, "user_has_open_tasks", details={"task_count": count})
    if (
        user.role == "supervisor"
        and user.is_active
        and (action == "delete" or not final_active or final_role != "supervisor")
    ):
        count = await session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == "supervisor", User.is_active.is_(True), User.deleted_at.is_(None))
        )
        if count <= 1:
            raise DomainError(409, "last_supervisor")
    if final_role == "supervisor":
        changes["branch_id"] = None
    elif "branch_id" in changes or "role" in changes:
        if user.role == "supervisor" and "branch_id" not in changes:
            raise DomainError(422, "invalid_branch")
        await active_branch(session, changes.get("branch_id", user.branch_id))
    elif changes.get("is_active") is True and user.branch_id:
        await active_branch(session, user.branch_id)
    password = None
    if action == "reset_password":
        password = temporary_password()
        user.password_hash = hasher.hash(password)
        user.must_change_password = True
        user.failed_login_count = 0
        user.locked_until = None
        user.password_changed_at = dates.now()
    if action == "delete":
        user.deleted_at, user.deleted_by = dates.now(), actor.id
    if (
        action in {"delete", "deactivate", "reset_password"}
        or not final_active
        or ("mobile" in changes and changes["mobile"] != user.mobile)
    ):
        await invalidate_sessions(session, user.id)
    for field, value in changes.items():
        setattr(user, field, value)
    user.updated_by = actor.id
    await session.flush()
    record(session, actor, action, "users", user.id, before, snapshot(user), request)
    output = UserOut.model_validate(user)
    return UserCreated(**output.model_dump(), temporary_password=password) if password else output
