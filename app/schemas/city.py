from typing import Optional
from pydantic import BaseModel, ConfigDict


class CityBase(BaseModel):
    name: str
    uf: str
    is_active: bool = True


class CityCreate(CityBase):
    pass


class CityUpdate(BaseModel):
    name: Optional[str] = None
    uf: Optional[str] = None
    is_active: Optional[bool] = None


class City(CityBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
