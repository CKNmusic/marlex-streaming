from typing import Optional
from urllib.parse import parse_qs, urlparse

from app.core.config import settings
from app.services.ingest_control import infer_protocol_from_source_type, ingest_api_get_json
from app.services.stream_protocols import normalize_protocol_name


def stream_path_from_url(stream_url: Optional[str]) -> Optional[str]:
    if not stream_url:
        return None
    parsed = urlparse(stream_url)
    scheme = normalize_protocol_name(parsed.scheme)
    path = (parsed.path or "").strip("/")
    if path:
        return path
    if scheme != "srt":
        return None

    # SRT readers/publishers usually encode the path in streamid (e.g. read:app/v1/key/stream).
    values = parse_qs(parsed.query or "", keep_blank_values=True)
    streamid = str((values.get("streamid") or [None])[0] or "").strip()
    if not streamid:
        return None
    prefix, sep, remainder = streamid.partition(":")
    if sep and prefix.strip().lower() in {"read", "publish", "request"}:
        normalized = remainder.strip("/")
        return normalized or None
    normalized = streamid.strip("/")
    return normalized or None


async def ingest_stream_url_is_online(stream_url: Optional[str]) -> Optional[bool]:
    if not settings.INGEST_API_ENABLED:
        return None

    path_name = stream_path_from_url(stream_url)
    if not path_name:
        return None
    expected_protocol = normalize_protocol_name(urlparse(stream_url).scheme)

    payload = await ingest_api_get_json("/paths/list")
    if payload is None:
        return None

    items = payload.get("items", [])
    for item in items:
        name = str(item.get("name") or "").strip("/")
        if name != path_name:
            continue
        # MediaMTX has both ready/available/online depending on state and version.
        is_online = bool(item.get("online") or item.get("ready") or item.get("available"))
        if not is_online:
            return False
        source = item.get("source") if isinstance(item, dict) else None
        source_type = str(source.get("type") or "").strip() if isinstance(source, dict) else ""
        source_protocol = infer_protocol_from_source_type(source_type)
        if expected_protocol and source_protocol and source_protocol != expected_protocol:
            return False
        return True
    return False
