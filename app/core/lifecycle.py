from sqlalchemy import select, update

from app.core import dates
from app.core.errors import DomainError
from app.models import Branch, LoginChallenge, RefreshToken, User


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
