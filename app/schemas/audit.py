from uuid import UUID

from app.core.dates import JalaliDateTime
from app.schemas.common import Output


class AuditOut(Output):
    id: int
    occurred_at: JalaliDateTime
    actor_id: UUID | None
    actor_role: str | None
    action: str
    entity_type: str
    entity_id: UUID | None
    before: dict | None
    after: dict | None
    ip: str | None
    request_id: UUID | None
