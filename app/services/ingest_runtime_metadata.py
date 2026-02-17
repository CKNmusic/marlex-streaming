from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


_REQUIRED_FIELDS = ("key", "protocol")
_OPTIONAL_FIELDS = ("audio_codec",)
_ALL_FIELDS = (*_REQUIRED_FIELDS, *_OPTIONAL_FIELDS)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_key(value: Optional[str]) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _normalize_ip(value: Optional[str]) -> Optional[str]:
    normalized = str(value or "").strip()
    return normalized or None


def _normalize_protocol(value: Optional[str]) -> Optional[str]:
    normalized = str(value or "").strip().lower()
    return normalized or None


def _normalize_codec(value: Optional[str]) -> Optional[str]:
    normalized = str(value or "").strip().lower()
    return normalized or None


def _normalize_resolution(value: Optional[str]) -> Optional[str]:
    normalized = str(value or "").strip().lower()
    return normalized or None


def _extract_codec(profile: dict[str, Any]) -> Optional[str]:
    return _normalize_codec(
        str(profile.get("video_codec") or "").strip()
        or str(profile.get("codec") or "").strip()
    )


def _extract_audio_codec(profile: dict[str, Any]) -> Optional[str]:
    return _normalize_codec(str(profile.get("audio_codec") or "").strip())


def _extract_resolution(profile: dict[str, Any]) -> Optional[str]:
    return _normalize_resolution(str(profile.get("resolution") or "").strip())


class IngestRuntimeMetadataStore:
    """
    In-memory metadata assembled from ingest-auth + stream profile probing.
    Used to avoid promoting a device to Online before metadata is complete.
    """

    def __init__(self) -> None:
        self._by_key: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    def clear_all(self) -> None:
        with self._lock:
            self._by_key.clear()

    def clear(self, device_key: Optional[str]) -> None:
        normalized_key = _normalize_key(device_key)
        if not normalized_key:
            return
        with self._lock:
            self._by_key.pop(normalized_key, None)

    def update_from_ingest_auth(
        self,
        *,
        device_key: Optional[str],
        ip: Optional[str],
        protocol: Optional[str],
    ) -> Optional[dict[str, Any]]:
        normalized_key = _normalize_key(device_key)
        if not normalized_key:
            return None

        normalized_ip = _normalize_ip(ip)
        normalized_protocol = _normalize_protocol(protocol)

        with self._lock:
            payload = self._by_key.get(normalized_key, {"key": normalized_key})
            payload["key"] = normalized_key
            if normalized_ip:
                payload["ip"] = normalized_ip
            if normalized_protocol:
                payload["protocol"] = normalized_protocol
            payload["updated_at"] = _now_utc()
            self._by_key[normalized_key] = payload
            return dict(payload)

    def update_from_stream_profile(
        self,
        *,
        device_key: Optional[str],
        profile: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        normalized_key = _normalize_key(device_key)
        if not normalized_key:
            return None

        codec = _extract_codec(profile)
        resolution = _extract_resolution(profile)
        audio_codec = _extract_audio_codec(profile)

        with self._lock:
            payload = self._by_key.get(normalized_key, {"key": normalized_key})
            payload["key"] = normalized_key
            if codec:
                payload["codec"] = codec
            if resolution:
                payload["resolution"] = resolution
            if audio_codec:
                payload["audio_codec"] = audio_codec
            payload["updated_at"] = _now_utc()
            self._by_key[normalized_key] = payload
            return dict(payload)

    def update_protocol_hint(
        self,
        *,
        device_key: Optional[str],
        protocol: Optional[str],
    ) -> Optional[dict[str, Any]]:
        normalized_key = _normalize_key(device_key)
        normalized_protocol = _normalize_protocol(protocol)
        if not normalized_key:
            return None
        if not normalized_protocol:
            return self.get(device_key)

        with self._lock:
            payload = self._by_key.get(normalized_key, {"key": normalized_key})
            payload["key"] = normalized_key
            payload["protocol"] = normalized_protocol
            payload["updated_at"] = _now_utc()
            self._by_key[normalized_key] = payload
            return dict(payload)

    def get(self, device_key: Optional[str]) -> Optional[dict[str, Any]]:
        normalized_key = _normalize_key(device_key)
        if not normalized_key:
            return None
        with self._lock:
            payload = self._by_key.get(normalized_key)
            if not payload:
                return None
            return dict(payload)

    def is_complete(self, payload: Optional[dict[str, Any]]) -> bool:
        if not isinstance(payload, dict):
            return False
        for field in _REQUIRED_FIELDS:
            value = str(payload.get(field) or "").strip()
            if not value:
                logger.debug("is_complete_failed missing_field=%s payload=%s", field, payload)
                return False
        return True

    def sanitize(self, payload: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if not isinstance(payload, dict):
            return None
        normalized_key = _normalize_key(payload.get("key"))
        if not normalized_key:
            return None

        result: dict[str, Any] = {"key": normalized_key}
        ip = _normalize_ip(payload.get("ip"))
        protocol = _normalize_protocol(payload.get("protocol"))
        codec = _normalize_codec(payload.get("codec"))
        resolution = _normalize_resolution(payload.get("resolution"))
        audio_codec = _normalize_codec(payload.get("audio_codec"))

        if ip:
            result["ip"] = ip
        if protocol:
            result["protocol"] = protocol
        if codec:
            result["codec"] = codec
        if resolution:
            result["resolution"] = resolution
        if audio_codec:
            result["audio_codec"] = audio_codec

        return result


ingest_runtime_metadata = IngestRuntimeMetadataStore()

