from app.core.dates import JalaliDateTime
from app.schemas.common import MetadataOut


class NotificationOut(MetadataOut):
    event_type: str
    title: str
    body: str | None
    payload: dict
    channel: str
    is_read: bool
    read_at: JalaliDateTime | None
