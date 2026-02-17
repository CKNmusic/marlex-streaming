from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from urllib.parse import quote, urlparse


@dataclass(frozen=True)
class StreamProtocolAdapter:
    scheme: str
    default_port: int
    ingest_base_path: str = "/live"
    ffprobe_input_args: Tuple[str, ...] = ()
    ffmpeg_input_args: Tuple[str, ...] = ()

    def build_ingest_url(self, host: str, *, port: Optional[int] = None) -> str:
        safe_host = str(host or "").strip() or "127.0.0.1"
        target_port = int(port) if port is not None else self.default_port
        base = f"{self.scheme}://{safe_host}:{target_port}"
        suffix = (self.ingest_base_path or "").strip()
        if not suffix:
            return base
        if not suffix.startswith("/"):
            suffix = f"/{suffix}"
        return f"{base}{suffix}"


PROTOCOL_ADAPTERS: Dict[str, StreamProtocolAdapter] = {
    "rtsp": StreamProtocolAdapter(
        scheme="rtsp",
        default_port=554,
        ffprobe_input_args=("-rtsp_transport", "tcp"),
        ffmpeg_input_args=("-rtsp_transport", "tcp"),
    ),
    "rtsps": StreamProtocolAdapter(
        scheme="rtsps",
        default_port=554,
        ffprobe_input_args=("-rtsp_transport", "tcp"),
        ffmpeg_input_args=("-rtsp_transport", "tcp"),
    ),
    "rtmp": StreamProtocolAdapter(
        scheme="rtmp",
        default_port=8554,
        ingest_base_path="/live",
    ),
    "rtmps": StreamProtocolAdapter(
        scheme="rtmps",
        default_port=443,
        ingest_base_path="/live",
    ),
    "srt": StreamProtocolAdapter(
        scheme="srt",
        default_port=9000,
        ingest_base_path="/live",
    ),
}

SUPPORTED_INGEST_PROTOCOLS: Tuple[str, ...] = ("rtmp", "srt")


def normalize_stream_url(stream_url: Optional[str]) -> Optional[str]:
    if stream_url is None:
        return None
    normalized = stream_url.strip()
    return normalized or None


def infer_stream_protocol(stream_url: Optional[str]) -> Optional[str]:
    normalized = normalize_stream_url(stream_url)
    if not normalized:
        return None
    parsed = urlparse(normalized)
    scheme = (parsed.scheme or "").strip().lower()
    return scheme or None


def normalize_protocol_name(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def get_protocol_adapter(protocol: Optional[str]) -> Optional[StreamProtocolAdapter]:
    normalized = normalize_protocol_name(protocol)
    if not normalized:
        return None
    return PROTOCOL_ADAPTERS.get(normalized)


def resolve_protocol_default_port(protocol: Optional[str], *, fallback: int = 1935) -> int:
    adapter = get_protocol_adapter(protocol)
    if adapter:
        return adapter.default_port
    return fallback


def is_supported_ingest_protocol(protocol: Optional[str]) -> bool:
    normalized = normalize_protocol_name(protocol)
    if not normalized:
        return False
    return normalized in SUPPORTED_INGEST_PROTOCOLS


def is_known_protocol(protocol: Optional[str]) -> bool:
    return get_protocol_adapter(protocol) is not None


def build_ingest_url_for_protocol(
    protocol: Optional[str],
    *,
    host: str,
    port: Optional[int] = None,
    stream_name: Optional[str] = None,
    srt_passphrase: Optional[str] = None,
    srt_pbkeylen: Optional[int] = None,
) -> Optional[str]:
    adapter = get_protocol_adapter(protocol)
    if adapter is None:
        return None
    base_url = adapter.build_ingest_url(host, port=port)
    if adapter.scheme != "srt":
        return base_url

    normalized_stream_name = str(stream_name or "").strip().strip("/")
    if not normalized_stream_name:
        return base_url

    stream_id_value = f"publish:{normalized_stream_name}"
    query_parts = [f"streamid={stream_id_value}"]
    passphrase = str(srt_passphrase or "").strip()
    if passphrase:
        key_len = int(srt_pbkeylen or 32)
        if key_len not in {16, 24, 32}:
            key_len = 32
        query_parts.append(f"passphrase={quote(passphrase, safe='')}")
        query_parts.append(f"pbkeylen={key_len}")

    parsed = urlparse(base_url)
    return f"{adapter.scheme}://{parsed.netloc}?{'&'.join(query_parts)}"


def resolve_stream_port(stream_url: str, *, default_port: int = 1935) -> int:
    parsed = urlparse(stream_url)
    if parsed.port:
        return parsed.port
    adapter = get_protocol_adapter(parsed.scheme)
    if adapter:
        return adapter.default_port
    return default_port


def ffprobe_input_args_for_url(stream_url: str) -> Tuple[str, ...]:
    parsed = urlparse(stream_url)
    adapter = get_protocol_adapter(parsed.scheme)
    return adapter.ffprobe_input_args if adapter else ()


def ffmpeg_input_args_for_url(stream_url: str) -> Tuple[str, ...]:
    parsed = urlparse(stream_url)
    adapter = get_protocol_adapter(parsed.scheme)
    return adapter.ffmpeg_input_args if adapter else ()
