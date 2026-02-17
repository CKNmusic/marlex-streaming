from typing import Any, Dict, List, Optional, Union
from pydantic import AnyHttpUrl, validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Medical Streaming API"
    APP_HOST: str = "192.168.10.19"
    APP_PORT: int = 8001
    APP_NAME: str = "surgwaze"
    APP_VERSION: str = "v1"
    API_V1_STR: str = f"/{APP_NAME}/{APP_VERSION}"
    
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    
    # Database
    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_PORT: str

    METRICS_INTERVAL_SEC: float = 2.0
    METRICS_ALWAYS_ON: bool = False
    METRICS_HISTORY_FILE: str = ".runtime/manager_metrics/metrics_history.jsonl"
    INGEST_STATUS_FILE: str = ".runtime/rtmp_ingest_manager/receiver_status.json"
    INGEST_API_ENABLED: bool = True
    INGEST_API_SCHEME: str = "http"
    INGEST_API_HOST: str = "127.0.0.1"
    INGEST_API_PORT: int = 9997
    INGEST_API_USER: str = "api"
    INGEST_API_PASS: str = "api"
    INGEST_API_TIMEOUT_SEC: float = 1.5
    SRT_PASSPHRASE: str = ""
    SRT_PBKEYLEN: int = 32
    RECORDER_ENABLE_FFMPEG: bool = True
    INGEST_GATEWAY_ENABLED: bool = False
    INGEST_GATEWAY_UPLOAD_URL: str = ""
    INGEST_GATEWAY_AUTH_TOKEN: str = ""
    INGEST_GATEWAY_TIMEOUT_SEC: float = 30.0
    INGEST_GATEWAY_MAX_RETRIES: int = 3
    INGEST_GATEWAY_RETRY_BACKOFF_SEC: float = 1.0
    INGEST_GATEWAY_WORKERS: int = 2
    INGEST_GATEWAY_HISTORY_FILE: str = ".runtime/ingest_gateway/upload_history.jsonl"
    INGEST_GATEWAY_OVERHEAD_FACTOR: float = 1.2
    INGEST_GATEWAY_LINK_UTILIZATION_TARGET: float = 0.7
    INGEST_GATEWAY_VIDEO_RESOLUTION: str = "1080p"
    INGEST_GATEWAY_VIDEO_CODEC: str = "h264"
    INGEST_GATEWAY_VIDEO_TARGET_BITRATE_MBPS: float = 6.0
    REALTIME_EVENT_BUS: str = "memory"
    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    REDIS_EVENTS_CHANNEL: str = "surgwaze:realtime:events"
    DEVICE_PRESENCE_MONITOR_ENABLED: bool = True
    DEVICE_PRESENCE_MONITOR_INTERVAL_SEC: float = 3.0
    DEVICE_STATUS_OFFLINE_GRACE_SECONDS: int = 5
    DEVICE_CONNECTING_TIMEOUT_SECONDS: int = 20
    STREAM_PROBE_ALLOW_FFMPEG_FALLBACK: bool = False

    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env")

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

settings = Settings()
