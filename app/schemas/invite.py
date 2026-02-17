from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class InviteOut(BaseModel):
    id: int
    code: str
    created_by: int
    used_by: Optional[int] = None
    used_at: Optional[datetime] = None
    expires_at: datetime
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class RegisterRequest(BaseModel):
    invite_code: str
    username: str
    password: str
    full_name: str
