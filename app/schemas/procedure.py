from typing import Optional
from pydantic import BaseModel, ConfigDict

class ProcedureBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True

class ProcedureCreate(ProcedureBase):
    pass

class ProcedureUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class Procedure(ProcedureBase):
    id: int
    
    model_config = ConfigDict(from_attributes=True)
