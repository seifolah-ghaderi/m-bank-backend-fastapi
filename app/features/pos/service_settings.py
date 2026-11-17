from sqlalchemy import select

from app.core import dates
from app.core.audit import record, snapshot
from app.core.deps import require_roles
from app.features.pos.service_transactions import transaction_actor
from app.models import PosPerformanceSettings


async def get_settings(session, actor):
    require_roles(actor, "supervisor", "branch_manager")
    return await session.get(PosPerformanceSettings, 1)


async def update_settings(session, actor, body, request=None):
    actor = await transaction_actor(session, actor)
    row = await session.scalar(
        select(PosPerformanceSettings)
        .where(PosPerformanceSettings.id == 1)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    before = snapshot(row)
    row.lower_threshold, row.upper_threshold = body.lower_threshold, body.upper_threshold
    row.policy_version += 1
    row.updated_at, row.updated_by = dates.now(), actor.id
    await session.flush()
    record(
        session,
        actor,
        "update",
        "pos_performance_settings",
        before=before,
        after=snapshot(row),
        request=request,
    )
    return row
