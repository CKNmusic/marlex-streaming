from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class MarkBase(BaseModel):
    name: str
    is_active: bool = True


class MarkCreate(MarkBase):
    pass


class MarkUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None


class Mark(MarkBase):
    id: int
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
