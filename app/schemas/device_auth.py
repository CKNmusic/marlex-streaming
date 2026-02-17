from pydantic import BaseModel
from typing import Optional

class DeviceAuthRequest(BaseModel):
    qr_token: str

class DeviceAuthResponse(BaseModel):
    device_session_token: str
    device_id: str
    expires_in: int
    # Provisioning info for the physical device (protocol-agnostic).
    ingest_url: str
    protocol: str
    stream_key: str
    auth_user: Optional[str] = None
    auth_password: Optional[str] = None

class DeviceHeartbeatRequest(BaseModel):
    device_id: str
    status: str = "ready"

class DeviceHeartbeatResponse(BaseModel):
    status: str
    next_heartbeat_in: int


class IngestAuthRequest(BaseModel):
    ip: Optional[str] = None
    user: Optional[str] = None
    password: Optional[str] = None
    path: Optional[str] = None
    protocol: Optional[str] = None
    id: Optional[str] = None
    action: str
    query: Optional[str] = None
