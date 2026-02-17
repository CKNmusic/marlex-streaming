from typing import Optional
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.services.stream_protocols import normalize_protocol_name


_INGEST_API_BASE_CANDIDATES = ("v3", "v2")
_cached_ingest_api_base: Optional[str] = None


def infer_protocol_from_source_type(source_type: Optional[str]) -> Optional[str]:
    normalized = str(source_type or "").strip().lower()
    if not normalized:
        return None
    if normalized.startswith("rtmp"):
        return "rtmp"
    if normalized.startswith("srt"):
        return "srt"
    if normalized.startswith("rtsp"):
        return "rtsp"
    if normalized.startswith("rtsps"):
        return "rtsps"
    return None


def _base_endpoint(api_base: str) -> str:
    return (
        f"{settings.INGEST_API_SCHEME}://"
        f"{settings.INGEST_API_HOST}:{settings.INGEST_API_PORT}/{api_base}"
    )


def _ordered_ingest_api_bases() -> list[str]:
    if _cached_ingest_api_base and _cached_ingest_api_base in _INGEST_API_BASE_CANDIDATES:
        others = [base for base in _INGEST_API_BASE_CANDIDATES if base != _cached_ingest_api_base]
        return [_cached_ingest_api_base, *others]
    return list(_INGEST_API_BASE_CANDIDATES)


def _cache_ingest_api_base(api_base: str) -> None:
    global _cached_ingest_api_base
    _cached_ingest_api_base = api_base


async def ingest_api_get_json(path: str) -> Optional[dict]:
    if not settings.INGEST_API_ENABLED:
        return None

    async with httpx.AsyncClient(timeout=settings.INGEST_API_TIMEOUT_SEC) as client:
        for api_base in _ordered_ingest_api_bases():
            endpoint = f"{_base_endpoint(api_base)}{path}"
            try:
                response = await client.get(
                    endpoint,
                    auth=(settings.INGEST_API_USER, settings.INGEST_API_PASS),
                )
            except Exception:
                continue

            if response.status_code == 404:
                continue
            if 200 <= response.status_code < 300:
                _cache_ingest_api_base(api_base)
                try:
                    payload = response.json()
                except ValueError:
                    return None
                return payload if isinstance(payload, dict) else None
            return None
    return None


async def ingest_api_post_ok(path: str) -> bool:
    if not settings.INGEST_API_ENABLED:
        return False

    async with httpx.AsyncClient(timeout=settings.INGEST_API_TIMEOUT_SEC) as client:
        for api_base in _ordered_ingest_api_bases():
            endpoint = f"{_base_endpoint(api_base)}{path}"
            try:
                response = await client.post(
                    endpoint,
                    auth=(settings.INGEST_API_USER, settings.INGEST_API_PASS),
                )
            except Exception:
                continue

            if response.status_code == 404:
                continue
            if 200 <= response.status_code < 300:
                _cache_ingest_api_base(api_base)
                return True
            return False
    return False


async def get_path_source(path_name: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    if not settings.INGEST_API_ENABLED:
        return None, None, None

    normalized_path = str(path_name or "").strip().strip("/")
    if not normalized_path:
        return None, None, None

    payload = await ingest_api_get_json("/paths/list")
    if payload is None:
        return None, None, None

    items = payload.get("items", []) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        return None, None, None

    for item in items:
        name = str(item.get("name") or "").strip("/")
        if name != normalized_path:
            continue

        source = item.get("source") if isinstance(item, dict) else None
        if not isinstance(source, dict):
            return None, None, None

        source_type = str(source.get("type") or "").strip()
        source_id = str(source.get("id") or "").strip()
        if not source_type or not source_id:
            return None, None, None

        source_protocol = infer_protocol_from_source_type(source_type)
        return source_protocol, source_type, source_id

    return None, None, None


async def kick_ingest_source(source_type: Optional[str], source_id: Optional[str]) -> bool:
    if not settings.INGEST_API_ENABLED:
        return False

    normalized_type = str(source_type or "").strip().lower()
    normalized_id = str(source_id or "").strip()
    if not normalized_type or not normalized_id:
        return False

    return await ingest_api_post_ok(f"/{normalized_type}s/kick/{quote(normalized_id, safe='')}")


async def kick_mismatched_source_for_path(
    *,
    path_name: Optional[str],
    expected_protocol: Optional[str],
) -> bool:
    normalized_expected = normalize_protocol_name(expected_protocol)
    if not normalized_expected:
        return False

    source_protocol, source_type, source_id = await get_path_source(path_name)
    if not source_type or not source_id or not source_protocol:
        return False

    if source_protocol == normalized_expected:
        return False

    return await kick_ingest_source(source_type, source_id)
