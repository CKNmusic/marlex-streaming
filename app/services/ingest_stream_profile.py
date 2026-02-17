import asyncio
import json
import logging
import shutil
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from app.services.stream_protocols import ffprobe_input_args_for_url
from app.services.ingest_runtime_metadata import ingest_runtime_metadata
from app.services.ingest_logging import log_ingest_info


logger = logging.getLogger(__name__)

_probe_tasks: dict[str, asyncio.Task] = {}
_profile_cache: dict[str, dict[str, Any]] = {}

_DEFAULT_PROFILE_CACHE_MAX_AGE_SEC = 15 * 60


def _safe_int(value: Any) -> Optional[int]:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _safe_float(value: Any) -> Optional[float]:
    if value in (None, "", "N/A"):
        return None
    text = str(value).strip()
    if not text:
        return None
    if "/" in text:
        left, _, right = text.partition("/")
        try:
            numerator = float(left)
            denominator = float(right)
            if denominator == 0:
                return None
            return numerator / denominator
        except (TypeError, ValueError):
            return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _normalize_streamid_for_probe(streamid_value: str) -> str:
    raw = str(streamid_value or "").strip()
    if not raw:
        return raw
    prefix, sep, remainder = raw.partition(":")
    normalized_prefix = prefix.strip().lower()
    if sep and normalized_prefix in {"publish", "request"}:
        return f"read:{remainder.strip()}"
    return raw


def build_probe_stream_url(stream_url: str) -> str:
    normalized = str(stream_url or "").strip()
    if not normalized:
        return normalized
    parsed = urlparse(normalized)
    if str(parsed.scheme or "").strip().lower() != "srt":
        return normalized

    query = parse_qs(parsed.query or "", keep_blank_values=True)
    streamid = str((query.get("streamid") or [None])[0] or "").strip()
    if not streamid:
        return normalized

    query["streamid"] = [_normalize_streamid_for_probe(streamid)]
    encoded_query = urlencode(query, doseq=True, safe=":/")
    return urlunparse(parsed._replace(query=encoded_query))


def parse_stream_profile(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    streams = payload.get("streams", []) if isinstance(payload, dict) else []
    if not isinstance(streams, list):
        return None

    video_stream = next(
        (item for item in streams if isinstance(item, dict) and str(item.get("codec_type") or "").strip() == "video"),
        None,
    )
    audio_stream = next(
        (item for item in streams if isinstance(item, dict) and str(item.get("codec_type") or "").strip() == "audio"),
        None,
    )
    if not isinstance(video_stream, dict) and not isinstance(audio_stream, dict):
        return None

    video_codec = str((video_stream or {}).get("codec_name") or "").strip().lower() or None
    audio_codec = str((audio_stream or {}).get("codec_name") or "").strip().lower() or None
    width = _safe_int((video_stream or {}).get("width"))
    height = _safe_int((video_stream or {}).get("height"))
    resolution = f"{width}x{height}" if width and height else None
    fps = _safe_float((video_stream or {}).get("avg_frame_rate"))
    video_bitrate = _safe_int((video_stream or {}).get("bit_rate"))
    audio_bitrate = _safe_int((audio_stream or {}).get("bit_rate"))
    audio_channels = _safe_int((audio_stream or {}).get("channels"))
    audio_sample_rate = _safe_int((audio_stream or {}).get("sample_rate"))

    return {
        "video_codec": video_codec,
        "audio_codec": audio_codec,
        "resolution": resolution,
        "fps": round(fps, 3) if fps is not None else None,
        "video_bitrate_bps": video_bitrate,
        "audio_bitrate_bps": audio_bitrate,
        "audio_channels": audio_channels,
        "audio_sample_rate": audio_sample_rate,
    }


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _cache_stream_profile(device_key: str, profile: dict[str, Any]) -> None:
    _profile_cache[device_key] = {
        **profile,
        "detected_at": _now_utc(),
    }


def get_cached_stream_profile(
    device_key: str,
    *,
    max_age_sec: int = _DEFAULT_PROFILE_CACHE_MAX_AGE_SEC,
) -> Optional[dict[str, Any]]:
    normalized_key = _normalize_probe_key(device_key)
    payload = _profile_cache.get(normalized_key)
    if not payload:
        return None

    detected_at = payload.get("detected_at")
    if not isinstance(detected_at, datetime):
        _profile_cache.pop(normalized_key, None)
        return None

    age_limit = max(int(max_age_sec), 1)
    age_sec = (_now_utc() - detected_at).total_seconds()
    if age_sec > age_limit:
        _profile_cache.pop(normalized_key, None)
        return None

    return dict(payload)


def clear_stream_profile_cache() -> None:
    _profile_cache.clear()


def remember_stream_profile(device_key: str, profile: dict[str, Any]) -> None:
    if not isinstance(profile, dict):
        return
    normalized_key = _normalize_probe_key(device_key)
    _cache_stream_profile(normalized_key, profile)


async def _run_ffprobe_once(stream_url: str, *, timeout_sec: float) -> Optional[dict[str, Any]]:
    if not shutil.which("ffprobe"):
        return None

    probe_url = build_probe_stream_url(stream_url)
    args = [
        "ffprobe",
        "-v",
        "error",
        *ffprobe_input_args_for_url(probe_url),
        "-show_streams",
        "-of",
        "json",
        probe_url,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except Exception:
        return None

    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
    except asyncio.TimeoutError:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        return None
    except Exception:
        return None

    if proc.returncode != 0:
        return None

    try:
        payload = json.loads((stdout or b"{}").decode("utf-8", errors="ignore"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


async def detect_stream_profile(
    stream_url: Optional[str],
    *,
    retries: int = 4,
    retry_delay_sec: float = 0.5,
    timeout_sec: float = 4.0,
) -> Optional[dict[str, Any]]:
    normalized_url = str(stream_url or "").strip()
    if not normalized_url:
        return None

    attempts = max(1, int(retries))
    for attempt in range(attempts):
        payload = await _run_ffprobe_once(normalized_url, timeout_sec=timeout_sec)
        profile = parse_stream_profile(payload or {})
        if profile:
            return profile
        if attempt < attempts - 1:
            await asyncio.sleep(max(retry_delay_sec, 0.1))
    return None


def _normalize_probe_key(device_key: str) -> str:
    return "".join(ch for ch in str(device_key or "").upper() if ch.isalnum()) or "UNKNOWN"


async def _probe_and_log(
    *,
    device_key: str,
    stream_url: str,
    protocol: Optional[str],
    context: str,
) -> None:
    try:
        profile = await detect_stream_profile(stream_url)
        if not profile:
            logger.info(
                "ingest_stream_profile_unavailable key=%s protocol=%s context=%s stream_url=%s",
                device_key,
                protocol or "-",
                context,
                stream_url,
            )
            log_ingest_info(
                device_key,
                f"stream_profile_unavailable protocol={protocol or '-'} context={context}",
            )
            return

        _cache_stream_profile(device_key, profile)
        ingest_runtime_metadata.update_from_stream_profile(
            device_key=device_key,
            profile=profile,
        )
        logger.info(
            "ingest_stream_profile key=%s protocol=%s context=%s resolution=%s video_codec=%s audio_codec=%s fps=%s v_bitrate_bps=%s a_bitrate_bps=%s channels=%s sample_rate=%s",
            device_key,
            protocol or "-",
            context,
            profile.get("resolution") or "-",
            profile.get("video_codec") or "-",
            profile.get("audio_codec") or "-",
            profile.get("fps") if profile.get("fps") is not None else "-",
            profile.get("video_bitrate_bps") if profile.get("video_bitrate_bps") is not None else "-",
            profile.get("audio_bitrate_bps") if profile.get("audio_bitrate_bps") is not None else "-",
            profile.get("audio_channels") if profile.get("audio_channels") is not None else "-",
            profile.get("audio_sample_rate") if profile.get("audio_sample_rate") is not None else "-",
        )
        log_ingest_info(
            device_key,
            (
                "stream_profile_detected "
                f"protocol={protocol or '-'} context={context} "
                f"resolution={profile.get('resolution') or '-'} "
                f"codec={profile.get('video_codec') or '-'}"
            ),
        )
    finally:
        _probe_tasks.pop(device_key, None)


def schedule_stream_profile_probe(
    *,
    device_key: str,
    stream_url: Optional[str],
    protocol: Optional[str],
    context: str,
) -> None:
    normalized_key = _normalize_probe_key(device_key)
    normalized_url = str(stream_url or "").strip()
    if not normalized_url:
        return

    active = _probe_tasks.get(normalized_key)
    if active is not None and not active.done():
        return

    protocol_name = str(protocol or "").strip().lower() or normalize_protocol_from_url(normalized_url)
    _probe_tasks[normalized_key] = asyncio.create_task(
        _probe_and_log(
            device_key=normalized_key,
            stream_url=normalized_url,
            protocol=protocol_name,
            context=context,
        )
    )


def normalize_protocol_from_url(stream_url: str) -> str:
    scheme = str(urlparse(stream_url).scheme or "").strip().lower()
    return scheme or "unknown"
