from typing import List

from pydantic import BaseModel


class NetworkMetric(BaseModel):
    download_bps: int
    upload_bps: int


class ManagerMetric(BaseModel):
    timestamp: str
    cpu_percent: float
    memory_percent: float
    network: NetworkMetric
    recordings_active: int
    publishers_online: int
    manager_clients: int
    app_users_online: int


class ManagerMetricHistory(BaseModel):
    items: List[ManagerMetric]


class IngestGatewayVideoProfile(BaseModel):
    resolution: str
    codec: str
    configured_bitrate_mbps: float


class IngestGatewayUploadAttempt(BaseModel):
    timestamp: str
    record_id: int
    worker_id: int
    attempt: int
    success: bool
    final: bool
    status_code: int | None
    error: str | None
    elapsed_sec: float
    bitrate_mbps: float
    file_size_bytes: int
    checksum_sha256: str
    file_path: str


class IngestGatewayStatus(BaseModel):
    enabled: bool
    upload_url: str
    queue_size: int
    in_flight: int
    workers: int
    retry_max_attempts: int
    retry_backoff_sec: float
    checksum_algorithm: str
    successful_uploads: int
    failed_uploads: int
    measured_bitrate_last_mbps: float | None
    measured_bitrate_avg_mbps: float | None
    video_profile: IngestGatewayVideoProfile
    recent_uploads: List[IngestGatewayUploadAttempt]


class IngestGatewayBandwidthEstimate(BaseModel):
    upload_count: int
    bitrate_mbps: float
    bitrate_source: str
    overhead_factor: float
    link_utilization_target: float
    minimum_upload_mbps: float
    video_profile: IngestGatewayVideoProfile
