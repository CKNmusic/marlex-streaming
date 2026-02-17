from typing import Optional
from pydantic import BaseModel, ConfigDict

class ProtocolBase(BaseModel):
    protocol: str
    port: int
    is_active: bool = True

class ProtocolCreate(ProtocolBase):
    pass

class ProtocolUpdate(BaseModel):
    protocol: Optional[str] = None
    port: Optional[int] = None
    is_active: Optional[bool] = None

class Protocol(ProtocolBase):
    id: int
    
    model_config = ConfigDict(from_attributes=True)
