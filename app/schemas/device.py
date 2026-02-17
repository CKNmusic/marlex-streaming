from typing import Any, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, model_validator

class DeviceBase(BaseModel):
    model: str
    # Compatibilidade temporaria com payload antigo.
    name: Optional[str] = None
    mark_id: Optional[int] = None
    mark_name: Optional[str] = None
    sn: str
    protocol: Optional[str] = None
    place_id: int
    is_active: bool = True

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        raw_model = str(payload.get("model") or "").strip()
        raw_name = str(payload.get("name") or "").strip()
        if raw_model:
            payload["model"] = raw_model
        elif raw_name:
            payload["model"] = raw_name
        raw_mark_name = str(payload.get("mark_name") or "").strip()
        if raw_mark_name:
            payload["mark_name"] = raw_mark_name
        if "sn" in payload and payload.get("sn") is not None:
            payload["sn"] = str(payload["sn"]).strip()
        return payload

class DeviceCreate(DeviceBase):
    pass

class DeviceUpdate(BaseModel):
    model: Optional[str] = None
    # Compatibilidade temporaria com payload antigo.
    name: Optional[str] = None
    mark_id: Optional[int] = None
    mark_name: Optional[str] = None
    sn: Optional[str] = None
    protocol: Optional[str] = None
    place_id: Optional[int] = None
    is_active: Optional[bool] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        raw_model = str(payload.get("model") or "").strip()
        raw_name = str(payload.get("name") or "").strip()
        if not raw_model and raw_name:
            payload["model"] = raw_name
        if "sn" in payload and payload.get("sn") is not None:
            payload["sn"] = str(payload["sn"]).strip()
        raw_mark_name = str(payload.get("mark_name") or "").strip()
        if raw_mark_name:
            payload["mark_name"] = raw_mark_name
        return payload

class Device(DeviceBase):
    id: int
    key: Optional[str] = None
    status: Optional[str] = None
    last_seen: Optional[datetime] = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class DeviceBind(BaseModel):
    key: str

class DeviceStatus(BaseModel):
    device_id: int
    online: bool
    status: str
    stream_url: Optional[str] = None
    checked_at: datetime
    metadata: Optional[dict[str, str]] = None
