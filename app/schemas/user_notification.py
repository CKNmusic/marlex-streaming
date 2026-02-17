from datetime import datetime
from pydantic import BaseModel, ConfigDict


class UserNotification(BaseModel):
    id: int
    code: str
    user_id: int
    user_name: str | None = None
    record_id: int | None = None
    record_public_id: str | None = None
    notification_type: str
    title: str
    message: str
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
