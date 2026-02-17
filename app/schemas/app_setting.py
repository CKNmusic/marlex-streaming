from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class AppSettingBase(BaseModel):
    name: str
    description: str
    host: str
    recordings_dir: str = "/recordings"
    output_format: str = "mp4"
    scan_start_in: int = Field(default=60, ge=5, le=600, strict=True)


class AppSettingUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    host: Optional[str] = None
    recordings_dir: Optional[str] = None
    output_format: Optional[str] = None
    scan_start_in: Optional[int] = Field(default=None, ge=5, le=600, strict=True)


class AppSetting(AppSettingBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
