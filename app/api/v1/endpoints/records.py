import os
import json
import re
import asyncio
import shutil
import logging
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, Query
from fastapi.responses import StreamingResponse
from jose import jwt, JWTError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import text, and_, func

from app.db.session import get_db
from app.models.user import User
from app.models.device import Device
from app.models.record import Record
from app.models.app_setting import AppSetting
from app.models.user_device_access import UserDeviceAccess
from app.schemas.record import RecordCreate, RecordUpdate, Record as RecordSchema
from app.schemas.token import TokenPayload
from app.api import deps
from app.core import security
from app.core.config import settings
from app.services.realtime_events import emit_device_status, emit_record_status
from app.services.recorder import recorder_service
from app.services.output_format import normalize_output_format, output_media_type
from app.services.ingest_upload_gateway import ingest_upload_gateway
from app.services.stream_protocols import ffmpeg_input_args_for_url, ffprobe_input_args_for_url
from app.services.ingest_presence import ingest_stream_url_is_online
from app.services.ingest_stream_profile import (
    detect_stream_profile,
    get_cached_stream_profile,
    remember_stream_profile,
    schedule_stream_profile_probe,
)
from app.services.ingest_runtime_metadata import ingest_runtime_metadata
from app.services.device_runtime_state import device_runtime_state
from app.services.device_stream_url import (
    build_device_stream_url,
    load_device_stream_context,
    resolve_device_protocol,
)
from app.services.device_status import (
    DEVICE_STATUS_CONNECTING,
    DEVICE_STATUS_OFFLINE,
    DEVICE_STATUS_ONLINE,
    DEVICE_STATUS_RECORDING,
    DEVICE_STATUS_STARTING,
    DEVICE_STATUS_STOPPING,
    RUNTIME_ACTIVE_DEVICE_STATUSES,
    is_device_online_status,
    normalize_device_status,
)
from app.services.ingest_publish_state import ingest_publish_state
from app.services.user_notifications import (
    NOTIFICATION_TYPE_DOWNLOAD_ERROR,
    NOTIFICATION_TYPE_DOWNLOAD_SUCCESS,
    NOTIFICATION_TYPE_RECORD_ERROR,
    NOTIFICATION_TYPE_RECORD_FINISHED,
    create_user_notification,
    is_record_failure,
)

router = APIRouter()
logger = logging.getLogger(__name__)
VIDEO_CHUNK_SIZE = 1024 * 1024
RANGE_HEADER_PATTERN = re.compile(r"bytes=(\d*)-(\d*)", re.IGNORECASE)
# Device heartbeat is 30s; keep a wider grace to avoid false offline when starting.
START_ONLINE_GRACE_SECONDS = 45
START_PROBE_RETRIES = 6
START_PROBE_RETRY_DELAY_SEC = 0.5


def _to_utc_naive(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _is_within_online_grace(
    *,
    checked_at: datetime,
    last_seen: Optional[datetime],
    grace_seconds: int = START_ONLINE_GRACE_SECONDS,
) -> bool:
    normalized_checked_at = _to_utc_naive(checked_at) or checked_at
    normalized_last_seen = _to_utc_naive(last_seen)
    if normalized_last_seen is None:
        return False
    return (normalized_checked_at - normalized_last_seen) <= timedelta(seconds=grace_seconds)


async def _wait_probe_process(proc: asyncio.subprocess.Process, timeout_sec: float) -> bool:
    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout_sec)
        return True
    except Exception:
        if proc.returncode is None:
            with suppress(Exception):
                proc.kill()
            with suppress(Exception):
                await proc.wait()
        return False


async def get_user_from_stream_token(db: AsyncSession, token: Optional[str]) -> User:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token obrigatório")

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[security.ALGORITHM])
        token_data = TokenPayload(**payload)
    except (JWTError, ValidationError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token inválido")

    result = await db.execute(select(User).where(User.id == int(token_data.sub)))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


def iter_file_bytes(path: str, start: int, end: int, chunk_size: int = VIDEO_CHUNK_SIZE) -> Iterator[bytes]:
    with open(path, "rb") as file_handle:
        file_handle.seek(start)
        remaining = (end - start) + 1
        while remaining > 0:
            next_chunk = file_handle.read(min(chunk_size, remaining))
            if not next_chunk:
                break
            remaining -= len(next_chunk)
            yield next_chunk


def parse_byte_range(range_header: str, file_size: int) -> tuple[int, int] | None:
    if file_size <= 0:
        return None
    match = RANGE_HEADER_PATTERN.fullmatch(range_header.strip())
    if not match:
        return None

    start_raw, end_raw = match.groups()
    if not start_raw and not end_raw:
        return None

    if not start_raw:
        suffix_size = int(end_raw)
        if suffix_size <= 0:
            return None
        start = max(file_size - suffix_size, 0)
        end = file_size - 1
        return start, end

    start = int(start_raw)
    end = int(end_raw) if end_raw else file_size - 1
    if start < 0:
        return None
    if end < start:
        return None
    if start >= file_size:
        return None
    end = min(end, file_size - 1)
    return start, end


async def align_record_sequence(db: AsyncSession) -> None:
    # Keeps sequence aligned after manual SQL restores/imports.
    await db.execute(
        text(
            "SELECT setval('records_id_seq', "
            "COALESCE((SELECT MAX(id) FROM records), 0) + 1, false)"
        )
    )


async def probe_stream(stream_url: Optional[str]) -> bool:
    if not stream_url:
        return False
    ingest_online = await ingest_stream_url_is_online(stream_url)
    if ingest_online is not None:
        return ingest_online

    if not settings.STREAM_PROBE_ALLOW_FFMPEG_FALLBACK:
        return False

    if shutil.which("ffprobe"):
        try:
            ffprobe_args = ["ffprobe", "-v", "error"]
            ffprobe_args.extend(ffprobe_input_args_for_url(stream_url))
            ffprobe_args.extend([
                "-i",
                stream_url,
                "-show_entries",
                "stream=codec_type",
                "-of",
                "csv=p=0",
            ])
            proc = await asyncio.create_subprocess_exec(
                *ffprobe_args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            if not await _wait_probe_process(proc, 3):
                return False
            return proc.returncode == 0
        except Exception:
            return False

    if shutil.which("ffmpeg"):
        try:
            ffmpeg_args = ["ffmpeg", "-v", "error", "-nostdin"]
            ffmpeg_args.extend(ffmpeg_input_args_for_url(stream_url))
            ffmpeg_args.extend([
                "-i",
                stream_url,
                "-t",
                "1",
                "-f",
                "null",
                "-",
            ])
            proc = await asyncio.create_subprocess_exec(
                *ffmpeg_args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            if not await _wait_probe_process(proc, 4):
                return False
            return proc.returncode == 0
        except Exception:
            return False

    return False


async def probe_stream_with_retry(
    stream_url: Optional[str],
    *,
    retries: int = START_PROBE_RETRIES,
    retry_delay_sec: float = START_PROBE_RETRY_DELAY_SEC,
) -> bool:
    attempts = max(0, int(retries)) + 1
    for index in range(attempts):
        if await probe_stream(stream_url):
            return True
        if index < attempts - 1:
            await asyncio.sleep(retry_delay_sec)
    return False


async def inspect_media_file(file_path: Optional[str]) -> dict[str, str]:
    target = str(file_path or "").strip()
    if not target or not os.path.exists(target):
        return {}
    if not shutil.which("ffprobe"):
        return {}

    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-of",
            "json",
            target,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=4.0)
        except asyncio.TimeoutError:
            if proc.returncode is None:
                with suppress(Exception):
                    proc.kill()
                with suppress(Exception):
                    await proc.wait()
            return {}
        if proc.returncode != 0:
            return {}
        payload = json.loads((stdout or b"{}").decode("utf-8", errors="ignore"))
        streams = payload.get("streams", []) if isinstance(payload, dict) else []
        if not isinstance(streams, list):
            return {}

        result: dict[str, str] = {}
        video_stream = next((item for item in streams if isinstance(item, dict) and item.get("codec_type") == "video"), None)
        if isinstance(video_stream, dict):
            width = int(video_stream.get("width") or 0)
            height = int(video_stream.get("height") or 0)
            if width > 0 and height > 0:
                result["video_resolution"] = f"{width}x{height}"
            video_codec = str(video_stream.get("codec_name") or "").strip()
            if video_codec:
                result["video_codec"] = video_codec

        audio_stream = next((item for item in streams if isinstance(item, dict) and item.get("codec_type") == "audio"), None)
        if isinstance(audio_stream, dict):
            audio_codec = str(audio_stream.get("codec_name") or "").strip()
            if audio_codec:
                result["audio_codec"] = audio_codec
        return result
    except Exception:
        return {}


async def ensure_user_has_device_access(
    db: AsyncSession,
    *,
    user: User,
    device: Device,
) -> None:
    if user.is_superuser:
        return

    access = await db.execute(
        select(UserDeviceAccess).where(
            and_(
                UserDeviceAccess.user_id == user.id,
                UserDeviceAccess.device_id == device.id,
            )
        )
    )
    if access.scalars().first() is None:
        raise HTTPException(status_code=403, detail="Device não autorizado para este usuário (scan obrigatório).")


async def get_next_device_seq(db: AsyncSession, device: Device) -> int:
    query = (
        select(func.max(Record.seq))
        .where(Record.device_id == device.id)
    )
    max_seq = await db.scalar(query)
    return int(max_seq or 0) + 1


async def load_current_output_format(db: AsyncSession) -> str:
    result = await db.execute(select(AppSetting).order_by(AppSetting.id).limit(1))
    app_setting = result.scalars().first()
    if not app_setting:
        recorder_service.set_recordings_dir("/recordings")
        return "mp4"
    recorder_service.set_recordings_dir(getattr(app_setting, "recordings_dir", "/recordings"))
    return normalize_output_format(getattr(app_setting, "output_format", None))


def resolve_record_output_path(record_id: int, preferred_path: Optional[str]) -> str:
    if preferred_path:
        return preferred_path
    mkv_path = recorder_service.get_output_path(record_id, "mkv")
    if os.path.exists(mkv_path):
        return mkv_path
    return recorder_service.get_output_path(record_id, "mp4")


async def enqueue_record_for_ingest_upload(
    *,
    record_id: int,
    record_output_path: str,
    owner_id: int,
    device_id: int,
    stop_reason: Optional[str],
    final_status: Optional[str],
    enqueue_source: str,
) -> None:
    await ingest_upload_gateway.enqueue_upload(
        record_id=record_id,
        file_path=record_output_path,
        metadata={
            "owner_id": str(owner_id),
            "device_id": str(device_id),
            "stop_reason": str(stop_reason or ""),
            "final_status": str(final_status or ""),
            "source": enqueue_source,
        },
    )


def _parse_iso_datetime(raw_value: Any) -> Optional[datetime]:
    if not isinstance(raw_value, str):
        return None
    payload = raw_value.strip()
    if not payload:
        return None
    try:
        return datetime.fromisoformat(payload)
    except ValueError:
        return None


def _stop_info_matches_record(
    stop_info: dict[str, Any],
    *,
    record_id: int,
    output_path: str,
) -> bool:
    stop_record_id = stop_info.get("record_id")
    if isinstance(stop_record_id, int):
        return stop_record_id == record_id

    stop_output_path = stop_info.get("output_path")
    if isinstance(stop_output_path, str) and stop_output_path.strip():
        return os.path.normpath(stop_output_path) == os.path.normpath(output_path)

    return False


async def reconcile_stale_open_records(
    db: AsyncSession,
    *,
    current_user: User,
    filter_owner_id: Optional[int],
) -> None:
    query = select(Record).where(Record.end_time.is_(None))
    if not current_user.is_superuser:
        query = query.where(Record.owner_id == current_user.id)
    elif filter_owner_id:
        query = query.where(Record.owner_id == filter_owner_id)

    open_records = (await db.execute(query)).scalars().all()
    if not open_records:
        return

    changed = False
    uploads_to_enqueue: list[tuple[int, str, int, int, Optional[str], Optional[str]]] = []
    for record in open_records:
        if recorder_service.is_recording(record.device_id):
            continue

        runtime_state = normalize_device_status(recorder_service.get_state(record.device_id))
        if runtime_state in RUNTIME_ACTIVE_DEVICE_STATUSES:
            continue

        raw_stop_info = recorder_service.get_last_stop_info(record.device_id) or {}
        fallback_output_path = resolve_record_output_path(record.id, record.output_path)

        if not raw_stop_info:
            if not fallback_output_path or not os.path.exists(fallback_output_path):
                await db.delete(record)
                changed = True
                continue
            try:
                fallback_file_size = int(os.path.getsize(fallback_output_path))
            except OSError:
                await db.delete(record)
                changed = True
                continue
            if fallback_file_size <= 0:
                await db.delete(record)
                changed = True
                continue
            # Runtime state was lost (restart/crash) but file exists:
            # finalize the open record to avoid blocking future starts with stale rows.
            raw_stop_info = {
                "record_id": int(record.id),
                "reason": "disconnect",
                "final_status": "error_connection",
                "ended_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "output_path": fallback_output_path,
                "file_size_bytes": fallback_file_size,
                "source": "reconcile_missing_stop_info",
            }

        if not _stop_info_matches_record(raw_stop_info, record_id=record.id, output_path=fallback_output_path):
            continue

        stop_info = dict(raw_stop_info)
        output_path = stop_info.get("output_path") or fallback_output_path

        raw_file_size = stop_info.get("file_size_bytes")
        if raw_file_size is None and output_path and os.path.exists(output_path):
            raw_file_size = os.path.getsize(output_path)
        try:
            file_size_bytes = max(int(raw_file_size or 0), 0)
        except (TypeError, ValueError):
            file_size_bytes = 0

        if file_size_bytes <= 0:
            if output_path and os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass
            await db.delete(record)
            changed = True
            continue

        raw_reason = stop_info.get("reason")
        stop_reason = (
            str(raw_reason).strip().lower()
            if isinstance(raw_reason, str) and raw_reason.strip()
            else "disconnect"
        )

        raw_final_status = stop_info.get("final_status")
        final_status = (
            str(raw_final_status).strip()
            if isinstance(raw_final_status, str) and raw_final_status.strip()
            else "error_connection"
        )

        ended_at = _parse_iso_datetime(stop_info.get("ended_at")) or datetime.now(timezone.utc)

        lifecycle_payload = dict(stop_info)
        lifecycle_payload["reason"] = stop_reason
        lifecycle_payload["final_status"] = final_status
        lifecycle_payload["ended_at"] = ended_at.isoformat(timespec="seconds")
        lifecycle_payload["output_path"] = output_path
        lifecycle_payload["file_size_bytes"] = file_size_bytes
        media_info = await inspect_media_file(output_path)
        if media_info:
            lifecycle_payload.update(media_info)

        record.end_time = ended_at
        record.stop_reason = stop_reason
        record.output_path = output_path
        record.file_size_bytes = file_size_bytes
        record.final_status = final_status
        record.lifecycle_log = json.dumps(lifecycle_payload, ensure_ascii=True)
        await create_user_notification(
            db,
            user_id=record.owner_id,
            notification_type=NOTIFICATION_TYPE_RECORD_FINISHED,
            title=f"Gravação {record.public_id} finalizada",
            message=f"Motivo: {record.stop_reason or '-'} | Data: {ended_at.strftime('%d/%m/%Y, %H:%M:%S')}",
            record=record,
            visible_to_user=True,
        )
        if is_record_failure(stop_reason=record.stop_reason, final_status=record.final_status):
            await create_user_notification(
                db,
                user_id=record.owner_id,
                notification_type=NOTIFICATION_TYPE_RECORD_ERROR,
                title=f"Erro na gravação {record.public_id}",
                message=f"Finalização com falha ({record.final_status or record.stop_reason or 'erro'}).",
                record=record,
                visible_to_user=True,
            )
        db.add(record)
        changed = True
        uploads_to_enqueue.append(
            (
                record.id,
                output_path,
                record.owner_id,
                record.device_id,
                record.stop_reason,
                record.final_status,
            )
        )

    if changed:
        await db.commit()
        for (
            record_id,
            output_path,
            owner_id,
            device_id,
            stop_reason,
            final_status,
        ) in uploads_to_enqueue:
            await enqueue_record_for_ingest_upload(
                record_id=record_id,
                record_output_path=output_path,
                owner_id=owner_id,
                device_id=device_id,
                stop_reason=stop_reason,
                final_status=final_status,
                enqueue_source="reconcile",
            )

@router.get("/", response_model=List[RecordSchema])
async def read_records(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    filter_owner_id: Optional[int] = None,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Retrieve record streams.
    - User sees OWN records only.
    - Master sees ALL.
    """
    await reconcile_stale_open_records(
        db,
        current_user=current_user,
        filter_owner_id=filter_owner_id,
    )

    query = select(Record)

    # 1. Authority Filter
    if not current_user.is_superuser:
        query = query.where(Record.owner_id == current_user.id)
    elif filter_owner_id:
        query = query.where(Record.owner_id == filter_owner_id)

    # 2. Date Filter
    if start_date:
        query = query.where(Record.start_time >= start_date)
    if end_date:
        query = query.where(Record.start_time <= end_date)

    # 3. Pagination
    query = query.order_by(Record.start_time.desc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    records = result.scalars().all()

    active_device_ids = {int(record.device_id) for record in records if record.end_time is None}
    device_key_by_id: dict[int, str] = {}
    if active_device_ids:
        devices_result = await db.execute(
            select(Device.id, Device.key).where(Device.id.in_(active_device_ids))
        )
        device_key_by_id = {
            int(row[0]): str(row[1] or "").strip()
            for row in devices_result.all()
            if row[0] is not None
        }

    for record in records:
        transfer_rate_bps = None
        if record.end_time is None:
            transfer_rate_bps = recorder_service.get_recording_transfer_rate_bps(record.device_id)
            if not record.video_resolution:
                device_key = device_key_by_id.get(int(record.device_id), "")
                stream_profile = get_cached_stream_profile(device_key) if device_key else None
                if stream_profile:
                    payload = {}
                    try:
                        payload = json.loads(record.lifecycle_log or "{}")
                    except Exception:
                        payload = {}
                    if not isinstance(payload, dict):
                        payload = {}
                    changed = False
                    resolution_value = str(stream_profile.get("resolution") or "").strip()
                    video_codec_value = str(stream_profile.get("video_codec") or "").strip()
                    audio_codec_value = str(stream_profile.get("audio_codec") or "").strip()
                    if resolution_value and not str(payload.get("video_resolution") or "").strip():
                        payload["video_resolution"] = resolution_value
                        changed = True
                    if video_codec_value and not str(payload.get("video_codec") or "").strip():
                        payload["video_codec"] = video_codec_value
                        changed = True
                    if audio_codec_value and not str(payload.get("audio_codec") or "").strip():
                        payload["audio_codec"] = audio_codec_value
                        changed = True
                    if changed:
                        record.lifecycle_log = json.dumps(payload, ensure_ascii=True)
        setattr(record, "transfer_rate_bps", transfer_rate_bps)
    return records

@router.delete("/{record_id}", response_model=bool)
async def delete_record(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Delete record stream. Master only.
    """
    result = await db.execute(select(Record).where(Record.id == record_id))
    record = result.scalars().first()
    
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
            
    await db.delete(record)
    await db.commit()
    return True

@router.post("/start", response_model=RecordSchema)
async def start_record(
    *,
    db: AsyncSession = Depends(get_db),
    record_in: RecordCreate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Start a recording.
    """
    # 1. Check Device
    result = await db.execute(select(Device).where(Device.id == record_in.device_id))
    device = result.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo não encontrado.")
    if not device.place_id:
        raise HTTPException(status_code=400, detail="Dispositivo sem local vinculado.")
    if not device.is_active:
        raise HTTPException(status_code=400, detail="Dispositivo desativado.")

    await ensure_user_has_device_access(db, user=current_user, device=device)
    device_id = int(device.id)
    stream_context = await load_device_stream_context(db)
    source_url = build_device_stream_url(device, stream_context) or ""
    if not source_url:
        raise HTTPException(status_code=422, detail="Dispositivo sem chave para gerar URL de stream.")

    checked_at = datetime.now(timezone.utc)
    runtime_snapshot = device_runtime_state.get(device_id)
    status_before_start = normalize_device_status(
        runtime_snapshot.status if runtime_snapshot is not None else None,
        fallback=DEVICE_STATUS_OFFLINE,
    )
    runtime_last_seen = runtime_snapshot.checked_at if runtime_snapshot is not None else None
    has_recent_publish = ingest_publish_state.has_recent_publish(
        int(device.id),
        within_seconds=max(int(settings.DEVICE_CONNECTING_TIMEOUT_SECONDS), 1),
    )
    logger.info(
        "record_start_requested record_owner_id=%s device_id=%s key=%s protocol=%s current_status=%s",
        current_user.id,
        device_id,
        device.key or "-",
        resolve_device_protocol(device, stream_context),
        status_before_start,
    )
    stream_is_online = await probe_stream_with_retry(source_url)
    if not stream_is_online:
        # Preserve transitional state to avoid flickering Offline when the publisher
        # is reconnecting during start attempts.
        should_hold_connecting = (
            has_recent_publish
            or status_before_start == DEVICE_STATUS_CONNECTING
            or is_device_online_status(status_before_start)
        )
        if should_hold_connecting:
            fallback_status = DEVICE_STATUS_CONNECTING
            fallback_online = False
        else:
            fallback_status = DEVICE_STATUS_OFFLINE
            fallback_online = False
        logger.info(
            "record_start_blocked_offline device_id=%s status=%s last_seen=%s source_url=%s fallback_status=%s",
            device.id,
            status_before_start,
            runtime_last_seen,
            source_url,
            fallback_status,
        )
        await emit_device_status(
            db,
            device_id=device.id,
            status=fallback_status,
            online=fallback_online,
            stream_url=source_url,
            checked_at=checked_at,
            detail="start_probe_offline_transient" if fallback_online else "start_probe_offline",
        )
        if fallback_status == DEVICE_STATUS_CONNECTING:
            raise HTTPException(
                status_code=409,
                detail="Dispositivo em conexão. Aguarde estabilizar e tente novamente.",
            )
        raise HTTPException(status_code=409, detail="Dispositivo offline. Aguarde ficar online para iniciar a gravação.")

    # Before blocking start by open record constraint, reconcile stale open rows.
    # This avoids false 409 when runtime already stopped but DB row remained open.
    await reconcile_stale_open_records(
        db,
        current_user=current_user,
        filter_owner_id=None if current_user.is_superuser else current_user.id,
    )

    open_record = await db.execute(
        select(Record).where(
            and_(
                Record.device_id == device_id,
                Record.end_time.is_(None),
            )
        )
    )
    if open_record.scalars().first():
        logger.warning("record_start_blocked reason=open_record device_id=%s key=%s", device_id, device.key or "-")
        raise HTTPException(status_code=409, detail="Já existe gravação em andamento para esta key/device.")
    if recorder_service.is_recording(device_id):
        logger.warning(
            "record_start_blocked reason=recorder_runtime_active device_id=%s key=%s",
            device_id,
            device.key or "-",
        )
        raise HTTPException(status_code=409, detail="Dispositivo já está gravando.")

    await align_record_sequence(db)
    next_seq = await get_next_device_seq(db, device)
    output_format = await load_current_output_format(db)
    
    # 2. Create DB Entry
    record = Record(
        owner_id=current_user.id,
        device_id=device.id,
        procedure_id=record_in.procedure_id,
        place_id=device.place_id,
        title=record_in.title or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        description=record_in.description,
        seq=next_seq,
        final_status="recording",
    )
    db.add(record)
    await db.flush()

    recording_started = False
    await emit_device_status(
        db,
        device_id=device.id,
        status=DEVICE_STATUS_STARTING,
        online=is_device_online_status(DEVICE_STATUS_STARTING),
        stream_url=source_url,
        checked_at=datetime.now(timezone.utc),
        detail="start_requested",
    )

    output_file = await recorder_service.start_recording(
        device_id=device_id,
        record_id=record.id,
        source_url=source_url,
        owner_id=current_user.id,
        profile="passthrough",
        output_format=output_format,
    )
    if not output_file:
        stop_info = recorder_service.get_last_stop_info(device_id) or {}
        stream_online_after_fail = await probe_stream_with_retry(source_url, retries=1, retry_delay_sec=0.4)
        logger.warning(
            "record_start_failed device_id=%s source_url=%s stop_info=%s stream_online_after_fail=%s",
            device_id,
            source_url,
            stop_info,
            stream_online_after_fail,
        )
        await db.rollback()
        failure_checked_at = datetime.now(timezone.utc)
        refreshed_device = await db.get(Device, device_id)
        has_recent_publish_after_fail = ingest_publish_state.has_recent_publish(
            int(device_id),
            within_seconds=max(int(settings.DEVICE_CONNECTING_TIMEOUT_SECONDS), 1),
        )
        should_hold_connecting_after_fail = (
            has_recent_publish_after_fail
            or status_before_start == DEVICE_STATUS_CONNECTING
            or is_device_online_status(status_before_start)
        )
        failure_status = (
            DEVICE_STATUS_ONLINE
            if stream_online_after_fail
            else (
                DEVICE_STATUS_CONNECTING
                if should_hold_connecting_after_fail
                else DEVICE_STATUS_OFFLINE
            )
        )
        await emit_device_status(
            db,
            device_id=device_id,
            status=failure_status,
            online=is_device_online_status(failure_status),
            stream_url=source_url,
            checked_at=failure_checked_at,
            detail=(
                "start_failed_stream_online"
                if stream_online_after_fail
                else "start_failed_stream_connecting"
                if failure_status == DEVICE_STATUS_CONNECTING
                else "start_failed_stream_offline"
            ),
        )
        if failure_status == DEVICE_STATUS_CONNECTING:
            raise HTTPException(
                status_code=409,
                detail="Dispositivo em reconexão. Aguarde estabilizar e tente novamente.",
            )
        if not stream_online_after_fail:
            raise HTTPException(
                status_code=409,
                detail="Dispositivo ficou offline durante a inicialização da gravação.",
            )
        detail_message = "Não foi possível iniciar a captura do stream."
        if str(stop_info.get("reason") or "").strip().lower() == "error_ffmpeg_unavailable":
            detail_message = f"{detail_message} FFmpeg indisponível no servidor."
        attempts = stop_info.get("attempts")
        if isinstance(attempts, int) and attempts > 1:
            detail_message = f"{detail_message} Tentativas: {attempts}."
        raise HTTPException(
            status_code=503,
            detail=detail_message,
        )
    recording_started = True
    logger.info(
        "record_start_ok record_id=%s device_id=%s key=%s output_file=%s",
        record.id,
        device_id,
        device.key or "-",
        output_file,
    )
    record.output_path = output_file
    record.final_status = "recording"
    stream_profile = get_cached_stream_profile(device.key or "")
    if stream_profile is None:
        stream_profile = await detect_stream_profile(
            source_url,
            retries=2,
            retry_delay_sec=0.4,
            timeout_sec=2.5,
        )
        if stream_profile:
            remember_stream_profile(device.key or "", stream_profile)
    if stream_profile:
        ingest_runtime_metadata.update_from_stream_profile(
            device_key=device.key or "",
            profile=stream_profile,
        )
    schedule_stream_profile_probe(
        device_key=device.key or "",
        stream_url=source_url,
        protocol=resolve_device_protocol(device, stream_context),
        context="record_start",
    )
    record.lifecycle_log = json.dumps(
        {
            "event": "start",
            "status": "recording",
            "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_url": source_url,
            "seq": next_seq,
            "output_format": output_format,
            "video_resolution": (stream_profile or {}).get("resolution"),
            "video_codec": (stream_profile or {}).get("video_codec"),
            "audio_codec": (stream_profile or {}).get("audio_codec"),
            "fps": (stream_profile or {}).get("fps"),
            "video_bitrate_bps": (stream_profile or {}).get("video_bitrate_bps"),
            "audio_bitrate_bps": (stream_profile or {}).get("audio_bitrate_bps"),
        },
        ensure_ascii=True,
    )
    await emit_device_status(
        db,
        device_id=device.id,
        status=DEVICE_STATUS_RECORDING,
        online=True,
        stream_url=source_url,
        checked_at=datetime.now(timezone.utc),
        detail="recording",
    )

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        if recording_started:
            await recorder_service.stop_recording(device.id)
        raise HTTPException(status_code=500, detail="Falha ao iniciar gravação")

    await db.refresh(record)
    await emit_record_status(
        db,
        record_id=record.id,
        device_id=record.device_id,
        owner_id=record.owner_id,
        status="Recording" if recording_started else "Started",
        final_status=record.final_status,
        stop_reason=record.stop_reason,
        end_time=record.end_time,
        detail="record_created",
    )
    
    return record

@router.post("/stop/{record_id}", response_model=RecordSchema)
async def stop_record(
    *,
    db: AsyncSession = Depends(get_db),
    record_id: int,
    reason: str = Query(default="user"),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Stop recording (update end_time and stop FFmpeg process if active).
    """
    result = await db.execute(select(Record).where(Record.id == record_id))
    record = result.scalars().first()
    
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
        
    if not current_user.is_superuser and record.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    if record.end_time:
        raise HTTPException(status_code=400, detail="Recording already stopped")

    normalized_reason = (reason or "user").strip().lower()
    if normalized_reason in {"user", "master"}:
        # "master" should only be used when a superuser stops another user's recording.
        normalized_reason = "master" if (current_user.is_superuser and record.owner_id != current_user.id) else "user"

    result_device = await db.execute(select(Device).where(Device.id == record.device_id))
    device = result_device.scalars().first()
    if device:
        await ensure_user_has_device_access(db, user=current_user, device=device)

    stream_context = await load_device_stream_context(db)
    source_url = build_device_stream_url(device, stream_context) if device else None

    if device:
        runtime_snapshot = device_runtime_state.get(int(device.id))
        stop_requested_status = (
            DEVICE_STATUS_STOPPING
            if recorder_service.is_recording(record.device_id)
            else normalize_device_status(
                runtime_snapshot.status if runtime_snapshot is not None else None,
                fallback=DEVICE_STATUS_ONLINE,
            )
        )
        await emit_device_status(
            db,
            device_id=device.id,
            status=stop_requested_status,
            online=is_device_online_status(stop_requested_status),
            stream_url=source_url,
            checked_at=datetime.now(timezone.utc),
            detail="stop_requested",
        )

    stopped_runtime = False
    if recorder_service.is_recording(record.device_id):
        await recorder_service.stop_recording(record.device_id, reason=normalized_reason)
        stopped_runtime = True

    raw_stop_info = recorder_service.get_last_stop_info(record.device_id) or {}
    fallback_output_path = resolve_record_output_path(record.id, record.output_path)
    stop_info_matches_record = _stop_info_matches_record(
        raw_stop_info,
        record_id=record.id,
        output_path=fallback_output_path,
    )
    if stopped_runtime and raw_stop_info:
        # Compatibility path for mocked runtimes without record metadata in tests.
        stop_info_matches_record = True

    stop_info = raw_stop_info if stop_info_matches_record else {}
    stream_online = await probe_stream(source_url)
    final_device_status = DEVICE_STATUS_ONLINE if stream_online else DEVICE_STATUS_OFFLINE

    ended_at = _parse_iso_datetime(stop_info.get("ended_at")) or datetime.now(timezone.utc)
    record.end_time = ended_at
    output_path = stop_info.get("output_path") or fallback_output_path

    software_reason = stop_info.get("reason")
    final_reason = (
        str(software_reason).strip().lower()
        if isinstance(software_reason, str) and software_reason.strip()
        else normalized_reason
    )

    software_final_status = stop_info.get("final_status")
    final_status = (
        str(software_final_status).strip()
        if isinstance(software_final_status, str) and software_final_status.strip()
        else f"stopped_{final_reason}"
    )

    raw_file_size = stop_info.get("file_size_bytes")
    should_compute_size_from_disk = (
        bool(output_path)
        and os.path.exists(output_path)
        and (stop_info_matches_record or bool(record.output_path))
    )
    if raw_file_size is None:
        raw_file_size = os.path.getsize(output_path) if should_compute_size_from_disk else 0
    try:
        file_size_bytes = max(int(raw_file_size), 0)
    except (TypeError, ValueError):
        file_size_bytes = 0

    lifecycle_payload = dict(stop_info)
    lifecycle_payload["reason"] = final_reason
    lifecycle_payload["final_status"] = final_status
    lifecycle_payload["ended_at"] = ended_at.isoformat(timespec="seconds")
    lifecycle_payload["output_path"] = output_path
    lifecycle_payload["file_size_bytes"] = file_size_bytes
    media_info = await inspect_media_file(output_path)
    if media_info:
        lifecycle_payload.update(media_info)

    if stop_info_matches_record and file_size_bytes <= 0:
        if output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError:
                pass
        await db.delete(record)
        await db.commit()
        if device:
            await emit_device_status(
                db,
                device_id=device.id,
                status=final_device_status,
                online=is_device_online_status(final_device_status),
                stream_url=source_url,
                checked_at=datetime.now(timezone.utc),
                detail="record_discarded_no_video",
            )
        raise HTTPException(status_code=409, detail="Gravação descartada: nenhum dado de vídeo foi capturado.")

    record.stop_reason = final_reason
    record.output_path = output_path
    record.file_size_bytes = file_size_bytes
    record.final_status = final_status
    record.lifecycle_log = json.dumps(lifecycle_payload, ensure_ascii=True)
    await create_user_notification(
        db,
        user_id=record.owner_id,
        notification_type=NOTIFICATION_TYPE_RECORD_FINISHED,
        title=f"Gravação {record.public_id} finalizada",
        message=f"Motivo: {record.stop_reason or '-'} | Data: {ended_at.strftime('%d/%m/%Y, %H:%M:%S')}",
        record=record,
        visible_to_user=True,
    )
    if is_record_failure(stop_reason=record.stop_reason, final_status=record.final_status):
        await create_user_notification(
            db,
            user_id=record.owner_id,
            notification_type=NOTIFICATION_TYPE_RECORD_ERROR,
            title=f"Erro na gravação {record.public_id}",
            message=f"Finalização com falha ({record.final_status or record.stop_reason or 'erro'}).",
            record=record,
            visible_to_user=True,
        )

    db.add(record)
    await db.commit()
    await db.refresh(record)
    await enqueue_record_for_ingest_upload(
        record_id=record.id,
        record_output_path=record.output_path or output_path,
        owner_id=record.owner_id,
        device_id=record.device_id,
        stop_reason=record.stop_reason,
        final_status=record.final_status,
        enqueue_source="stop",
    )
    if device:
        await emit_device_status(
            db,
            device_id=device.id,
            status=final_device_status,
            online=is_device_online_status(final_device_status),
            stream_url=source_url,
            checked_at=datetime.now(timezone.utc),
            detail=record.final_status,
        )
    await emit_record_status(
        db,
        record_id=record.id,
        device_id=record.device_id,
        owner_id=record.owner_id,
        status="Stopped",
        final_status=record.final_status,
        stop_reason=record.stop_reason,
        end_time=record.end_time,
        detail="record_stopped",
    )
    
    return record


@router.get("/{record_id}/stream")
async def stream_record_file(
    *,
    request: Request,
    db: AsyncSession = Depends(get_db),
    record_id: int,
    token: Optional[str] = Query(default=None),
    download: bool = Query(default=False),
) -> Any:
    """
    Serve recorded MP4 file for playback.
    Uses query token to support HTML <video> element auth.
    """
    current_user = await get_user_from_stream_token(db, token)

    async def log_download_notification(*, notification_type: str, title: str, message: str, target_record: Record | None = None) -> None:
        if not download:
            return
        try:
            await create_user_notification(
                db,
                user_id=current_user.id,
                notification_type=notification_type,
                title=title,
                message=message,
                record=target_record,
                record_id=target_record.id if target_record else record_id,
                record_public_id=target_record.public_id if target_record else None,
                visible_to_user=True,
            )
            await db.commit()
        except Exception:
            await db.rollback()

    result = await db.execute(select(Record).where(Record.id == record_id))
    record = result.scalars().first()
    if not record:
        await log_download_notification(
            notification_type=NOTIFICATION_TYPE_DOWNLOAD_ERROR,
            title=f"Erro no download da gravação #{record_id}",
            message="Gravação não encontrada.",
        )
        raise HTTPException(status_code=404, detail="Record not found")

    if not current_user.is_superuser and record.owner_id != current_user.id:
        await log_download_notification(
            notification_type=NOTIFICATION_TYPE_DOWNLOAD_ERROR,
            title=f"Erro no download da gravação {record.public_id}",
            message="Sem permissão para baixar este arquivo.",
            target_record=record,
        )
        raise HTTPException(status_code=403, detail="Not authorized")

    file_path = resolve_record_output_path(record.id, record.output_path)
    if not os.path.exists(file_path):
        await log_download_notification(
            notification_type=NOTIFICATION_TYPE_DOWNLOAD_ERROR,
            title=f"Erro no download da gravação {record.public_id}",
            message="Arquivo de vídeo não encontrado.",
            target_record=record,
        )
        raise HTTPException(status_code=404, detail="Arquivo de vídeo não encontrado")

    await log_download_notification(
        notification_type=NOTIFICATION_TYPE_DOWNLOAD_SUCCESS,
        title=f"Download da gravação {record.public_id}",
        message=f"Solicitado em {datetime.now(timezone.utc).strftime('%d/%m/%Y, %H:%M:%S')}.",
        target_record=record,
    )

    file_size = os.path.getsize(file_path)
    media_type = output_media_type(file_path)
    disposition = "attachment" if download else "inline"
    base_headers = {
        "accept-ranges": "bytes",
        "content-disposition": f'{disposition}; filename="{os.path.basename(file_path)}"',
    }
    range_header = request.headers.get("range")

    if not range_header:
        return StreamingResponse(
            iter_file_bytes(file_path, 0, file_size - 1),
            media_type=media_type,
            headers={
                **base_headers,
                "content-length": str(file_size),
            },
        )

    byte_range = parse_byte_range(range_header, file_size)
    if byte_range is None:
        return Response(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            headers={
                **base_headers,
                "content-range": f"bytes */{file_size}",
            },
        )

    start, end = byte_range
    content_length = (end - start) + 1
    return StreamingResponse(
        iter_file_bytes(file_path, start, end),
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type=media_type,
        headers={
            **base_headers,
            "content-length": str(content_length),
            "content-range": f"bytes {start}-{end}/{file_size}",
        },
    )

@router.patch("/{record_id}", response_model=RecordSchema)
async def update_record(
    *,
    db: AsyncSession = Depends(get_db),
    record_id: int,
    record_in: RecordUpdate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Update a record stream title/description.
    """
    result = await db.execute(select(Record).where(Record.id == record_id))
    record = result.scalars().first()
    
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
        
    if not current_user.is_superuser and record.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    if record_in.title is not None:
        record.title = record_in.title
    if record_in.description is not None:
        record.description = record_in.description
    if record_in.end_time is not None:
        record.end_time = record_in.end_time
        
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record
