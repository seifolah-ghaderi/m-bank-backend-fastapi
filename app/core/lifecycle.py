from sqlalchemy import func, select, text, update

from app.core import dates
from app.core.errors import DomainError
from app.models import Branch, LoginChallenge, RefreshToken, User


async def lifecycle_actor(session, actor, *roles):
    from app.core.deps import eligible, require_roles

    await session.execute(text("SELECT pg_advisory_xact_lock(72851901)"))
    current = await lock_user(session, actor.id)
    eligible(current)
    if current.must_change_password:
        raise DomainError(403, "password_change_required")
    if roles:
        require_roles(current, *roles)
    return current


async def assigned_task_count(session, user_id):
    from app.models import PosVisit

    return await session.scalar(
        select(func.count())
        .select_from(PosVisit)
        .where(PosVisit.assigned_to == user_id, PosVisit.status == "assigned")
    )


async def lock_user(session, user_id):
    return await session.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def invalidate_sessions(session, user_id, *, keep_hash=None):
    statement = update(RefreshToken).where(
        RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
    )
    if keep_hash:
        statement = statement.where(RefreshToken.token_hash != keep_hash)
    await session.execute(statement.values(revoked_at=dates.now()))
    await session.execute(
        update(LoginChallenge)
        .where(
            LoginChallenge.user_id == user_id,
            LoginChallenge.consumed_at.is_(None),
            LoginChallenge.invalidated_at.is_(None),
        )
        .values(invalidated_at=dates.now())
    )


async def active_branch(session, branch_id):
    branch = await session.scalar(
        select(Branch)
        .where(Branch.id == branch_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not branch or branch.deleted_at is not None or not branch.is_active:
        raise DomainError(422, "branch_inactive")
    return branch
