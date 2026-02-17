from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional


logger = logging.getLogger("app.ingest")


def _normalize_key(value: Optional[str]) -> str:
    normalized = "".join(ch for ch in str(value or "").upper() if ch.isalnum())
    return normalized or "-"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log_ingest_info(device_key: Optional[str], info: str) -> None:
    logger.info("%s | %s | %s", _timestamp(), _normalize_key(device_key), str(info or "").strip())


def log_ingest_warning(device_key: Optional[str], info: str) -> None:
    logger.warning("%s | %s | %s", _timestamp(), _normalize_key(device_key), str(info or "").strip())

