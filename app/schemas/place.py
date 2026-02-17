from typing import Optional
from pydantic import BaseModel, ConfigDict


class PlaceBase(BaseModel):
    name: str
    description: Optional[str] = None
    city_id: int
    is_active: bool = True


class PlaceCreate(PlaceBase):
    pass


class PlaceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    city_id: Optional[int] = None
    is_active: Optional[bool] = None


class Place(PlaceBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
