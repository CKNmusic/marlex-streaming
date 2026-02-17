from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

class RecordBase(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None

class RecordCreate(RecordBase):
    device_id: int
    procedure_id: Optional[int] = None

class RecordUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    end_time: Optional[datetime] = None

class Record(RecordBase):
    id: int
    public_id: Optional[str] = None
    owner_id: int
    device_id: int
    place_id: int
    procedure_id: Optional[int] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    seq: Optional[int] = None
    output_path: Optional[str] = None
    file_size_bytes: Optional[int] = None
    transfer_rate_bps: Optional[float] = None
    final_status: Optional[str] = None
    stop_reason: Optional[str] = None
    lifecycle_log: Optional[str] = None
    video_resolution: Optional[str] = None
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)
