from __future__ import annotations

from pathlib import Path
from typing import Optional

SUPPORTED_OUTPUT_FORMATS = {"mp4", "mkv"}
DEFAULT_OUTPUT_FORMAT = "mp4"


def normalize_output_format(raw_value: Optional[str]) -> str:
    normalized = (raw_value or "").strip().lower()
    if normalized in SUPPORTED_OUTPUT_FORMATS:
        return normalized
    return DEFAULT_OUTPUT_FORMAT


def output_media_type(file_path: str) -> str:
    extension = Path(file_path).suffix.lower()
    if extension == ".mkv":
        return "video/x-matroska"
    return "video/mp4"
