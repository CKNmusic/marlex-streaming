import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, unquote

from app.db.session import get_db
from app.models.device import Device
from app.models.user_device_access import UserDeviceAccess
from app.schemas.device_auth import (
    DeviceAuthRequest,
    DeviceAuthResponse,
    DeviceHeartbeatRequest,
    DeviceHeartbeatResponse,
    IngestAuthRequest,
)
from app.core import security
from app.core.config import settings
from app.services.device_stream_url import (
    build_device_stream_url,
    load_device_stream_context,
    resolve_device_protocol,
)
from app.services.realtime_events import emit_device_status
from app.services.realtime_hub import realtime_hub
from app.services.ingest_publish_state import ingest_publish_state
from app.services.ingest_runtime_metadata import ingest_runtime_metadata
from app.services.ingest_logging import log_ingest_info, log_ingest_warning
from app.services.device_runtime_state import device_runtime_state
from app.services.stream_protocols import (
    build_ingest_url_for_protocol,
    normalize_protocol_name,
    resolve_protocol_default_port,
)
from app.services.recorder import recorder_service
from app.services.device_status import (
    DEVICE_STATUS_CONNECTING,
    DEVICE_STATUS_OFFLINE,
    DEVICE_STATUS_ONLINE,
    DEVICE_STATUS_RECORDING,
    DEVICE_STATUS_STARTING,
    DEVICE_STATUS_STOPPING,
    is_device_online_status,
    normalize_device_status,
)
from app.models.record import Record

router = APIRouter()
logger = logging.getLogger(__name__)


def _extract_stream_key(path_name: str | None) -> str | None:
    """
    Expected path format: /<APP_NAME>/<APP_VERSION>/<device_key>/stream
    """
    if not path_name:
        return None
    clean_path = str(path_name).strip("/ ")
    segments = [segment for segment in clean_path.split("/") if segment]
    if len(segments) != 4:
        return None
    if segments[0] != settings.APP_NAME or segments[1] != settings.APP_VERSION:
        return None
    if segments[3] != "stream":
        return None
    stream_key = segments[2].strip()
    return stream_key or None


def _resolve_runtime_status_for_heartbeat(device_id: int) -> str:
    runtime_status = device_runtime_state.get_status(device_id, fallback=DEVICE_STATUS_OFFLINE)
    if recorder_service.is_recording(device_id):
        return DEVICE_STATUS_RECORDING
    if runtime_status in {DEVICE_STATUS_STARTING, DEVICE_STATUS_STOPPING, DEVICE_STATUS_RECORDING}:
        return runtime_status
    return DEVICE_STATUS_CONNECTING


async def _emit_device_status_snapshot(
    db: AsyncSession,
    *,
    device: Device,
    status: str,
    checked_at: Optional[datetime] = None,
    detail: str,
) -> None:
    stream_context = await load_device_stream_context(db)
    stream_url = build_device_stream_url(device, stream_context)
    normalized_status = normalize_device_status(status)
    metadata = ingest_runtime_metadata.get(device.key)
    logger.info(
        "device_status_snapshot key=%s device_id=%s status=%s detail=%s",
        device.key or "-",
        device.id,
        normalized_status,
        detail,
    )
    await emit_device_status(
        db,
        device_id=device.id,
        status=normalized_status,
        online=is_device_online_status(normalized_status),
        stream_url=stream_url,
        checked_at=checked_at or datetime.now(timezone.utc),
        detail=detail,
        metadata=metadata,
    )


def _extract_device_key_from_qr_token(qr_token: str) -> str | None:
    raw = str(qr_token or "").strip()
    if not raw:
        return None
    if "://" in raw:
        parsed = parse_qs(unquote(raw.split("?", 1)[1] if "?" in raw else ""))
        key = (parsed.get("key") or [None])[0]
        return str(key).strip() if key else None
    return raw


def _extract_stream_path_from_stream_id(stream_id: str | None) -> str | None:
    raw = unquote(str(stream_id or "").strip())
    if not raw:
        return None

    if raw.startswith("#!::"):
        payload = raw[4:]
        options: dict[str, str] = {}
        for entry in payload.split(","):
            if "=" not in entry:
                continue
            key, value = entry.split("=", 1)
            options[key.strip().lower()] = value.strip()
        path_value = options.get("r")
        if not path_value:
            return None
        return path_value.strip("/ ")

    prefix, separator, remainder = raw.partition(":")
    if separator and prefix.strip().lower() in {"publish", "read", "request"}:
        normalized = remainder.strip("/ ")
        return normalized or None

    normalized = raw.strip("/ ")
    return normalized or None


def _extract_stream_key_from_ingest_request(auth_in: IngestAuthRequest) -> str | None:
    stream_key = _extract_stream_key(auth_in.path)
    if stream_key:
        return stream_key

    raw_query = str(auth_in.query or "").strip()
    if raw_query.startswith("?"):
        raw_query = raw_query[1:]
    query_values = parse_qs(raw_query, keep_blank_values=True)
    stream_id = (query_values.get("streamid") or [None])[0]
    stream_path = _extract_stream_path_from_stream_id(stream_id)
    stream_key = _extract_stream_key(stream_path)
    if stream_key:
        return stream_key

    stream_path_from_id = _extract_stream_path_from_stream_id(auth_in.id)
    return _extract_stream_key(stream_path_from_id)

@router.post("/auth", response_model=DeviceAuthResponse)
async def device_authenticate(
    *,
    db: AsyncSession = Depends(get_db),
    device_auth: DeviceAuthRequest
):
    """
    Device authenticates using QR code token.
    Returns a session token for the device to use in heartbeats.
    """
    device_key = _extract_device_key_from_qr_token(device_auth.qr_token)
    if not device_key:
        raise HTTPException(status_code=422, detail="QR token inválido.")

    # Find device by canonical key encoded in QR payload.
    result = await db.execute(select(Device).where(Device.key == device_key))
    device = result.scalars().first()
    
    if not device:
        raise HTTPException(status_code=404, detail="Invalid QR token")
    
    if not device.is_active:
        raise HTTPException(status_code=403, detail="Device is not active")
    
    # Generate session token
    device_session_token = security.create_access_token(
        subject=str(device.id),
        expires_delta=timedelta(days=1)
    )
    
    if not device.key:
        device.generate_key()
    
    await db.commit()
    await db.refresh(device)
    
    stream_context = await load_device_stream_context(db)
    protocol = resolve_device_protocol(device, stream_context)
    port = stream_context.ports_by_protocol.get(
        protocol,
        resolve_protocol_default_port(protocol, fallback=8554),
    )
    ingest_url = build_ingest_url_for_protocol(
        protocol,
        host=stream_context.host or settings.APP_HOST,
        port=port,
        stream_name=f"{settings.APP_NAME}/{settings.APP_VERSION}/{device.key}/stream",
        srt_passphrase=settings.SRT_PASSPHRASE,
        srt_pbkeylen=settings.SRT_PBKEYLEN,
    ) or f"{protocol}://{settings.APP_HOST}:{port}/live"
    
    return DeviceAuthResponse(
        device_session_token=device_session_token,
        device_id=str(device.id),
        expires_in=86400,
        ingest_url=ingest_url,
        protocol=protocol,
        stream_key=device.key or "",
        auth_user=None,
        auth_password=None,
    )


@router.post("/heartbeat", response_model=DeviceHeartbeatResponse)
async def device_heartbeat(
    *,
    db: AsyncSession = Depends(get_db),
    heartbeat: DeviceHeartbeatRequest,
    current_device_id: str = Depends(security.get_current_device_id)
):
    """
    Device sends periodic heartbeat to maintain connection status.
    Must be called every 30 seconds.
    """
    # Verify device ID matches token
    try:
        heartbeat_device_id = int(str(heartbeat.device_id))
        token_device_id = int(str(current_device_id))
    except (TypeError, ValueError):
        raise HTTPException(status_code=403, detail="Device ID mismatch")

    if heartbeat_device_id != token_device_id:
        raise HTTPException(status_code=403, detail="Device ID mismatch")
    
    # Find device
    result = await db.execute(
        select(Device).where(Device.id == heartbeat_device_id)
    )
    device = result.scalars().first()
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    access_rows = await db.execute(
        select(UserDeviceAccess.user_id).where(UserDeviceAccess.device_id == device.id)
    )
    authorized_user_ids = {int(row[0]) for row in access_rows.all()}
    has_online_user = await realtime_hub.any_user_online(authorized_user_ids)
    has_online_master = await realtime_hub.any_superuser_online()
    has_active_recording_state = recorder_service.is_recording(device.id)

    # Cost gate: no active viewer/admin and no active recording => ignore media heartbeat.
    # Always return OK to keep device connected (Always On policy)
    # The previous logic (ignored_user_offline) caused devices to disconnect/reconnect loop.

    # Update heartbeat timestamp and online status
    checked_at = datetime.now(timezone.utc)
    status_to_emit = _resolve_runtime_status_for_heartbeat(device.id)
    logger.info(
        "device_heartbeat_ok key=%s device_id=%s status=%s",
        device.key or "-",
        device.id,
        status_to_emit,
    )
    stream_context = await load_device_stream_context(db)
    stream_url = build_device_stream_url(device, stream_context)
    metadata = ingest_runtime_metadata.get(device.key)
    await emit_device_status(
        db,
        device_id=device.id,
        status=status_to_emit,
        online=is_device_online_status(status_to_emit),
        stream_url=stream_url,
        checked_at=checked_at,
        detail="heartbeat",
        metadata=metadata,
    )
    
    return DeviceHeartbeatResponse(
        status="ok",
        next_heartbeat_in=30  # seconds
    )


@router.post("/disconnect")
async def device_disconnect(
    *,
    db: AsyncSession = Depends(get_db),
    current_device_id: str = Depends(security.get_current_device_id)
):
    """
    Device explicitly disconnects (graceful shutdown).
    """
    try:
        token_device_id = int(str(current_device_id))
    except (TypeError, ValueError):
        raise HTTPException(status_code=403, detail="Invalid device token")

    result = await db.execute(
        select(Device).where(Device.id == token_device_id)
    )
    device = result.scalars().first()
    
    if device:
        previous_status = str(device.status or "Unknown")
        ingest_publish_state.clear(device.id)
        logger.info(
            "device_disconnect key=%s device_id=%s from=%s to=Offline",
            device.key or "-",
            device.id,
            previous_status,
        )
        await _emit_device_status_snapshot(
            db,
            device=device,
            status=DEVICE_STATUS_OFFLINE,
            checked_at=datetime.now(timezone.utc),
            detail="device_disconnect",
        )
    
    return {"status": "disconnected"}


@router.post("/ingest-auth")
async def ingest_auth_gate(
    *,
    db: AsyncSession = Depends(get_db),
    auth_in: IngestAuthRequest,
):
    """
    Media ingress gate called by MediaMTX (authMethod=http).
    Blocks useless publish traffic when there is no online user and no active recording.
    """
    action = str(auth_in.action or "").strip().lower()
    if action in {"api", "metrics", "pprof", "read", "playback"}:
        return {"status": "ok", "detail": f"allow_{action}"}

    if action != "publish":
        log_ingest_warning(
            None,
            f"auth_blocked invalid_action action={action} path={auth_in.path or '-'}",
        )
        logger.warning(
            "ingest_auth_blocked reason=invalid_action action=%s path=%s",
            action,
            auth_in.path or "-",
        )
        raise HTTPException(status_code=403, detail=f"Action not allowed: {action}")

    stream_key = _extract_stream_key_from_ingest_request(auth_in)
    if not stream_key:
        log_ingest_warning(
            None,
            (
                "auth_blocked invalid_stream_path "
                f"protocol={normalize_protocol_name(auth_in.protocol) or '-'} "
                f"path={auth_in.path or '-'} id={auth_in.id or '-'}"
            ),
        )
        logger.warning(
            "ingest_auth_blocked reason=invalid_stream_path protocol=%s path=%s id=%s query=%s",
            normalize_protocol_name(auth_in.protocol) or "-",
            auth_in.path or "-",
            auth_in.id or "-",
            auth_in.query or "-",
        )
        raise HTTPException(status_code=403, detail="Invalid stream path or streamid.")

    res_device = await db.execute(select(Device).where(Device.key == stream_key))
    device = res_device.scalars().first()
    if not device:
        log_ingest_warning(stream_key, "auth_blocked unknown_device")
        logger.warning("ingest_auth_blocked reason=unknown_device key=%s", stream_key)
        raise HTTPException(status_code=403, detail="Unknown device key.")
    if not device.is_active:
        log_ingest_warning(device.key or stream_key, f"auth_blocked device_inactive device_id={device.id}")
        logger.warning("ingest_auth_blocked reason=device_inactive key=%s device_id=%s", stream_key, device.id)
        raise HTTPException(status_code=403, detail="Device inactive.")

    stream_context = await load_device_stream_context(db)
    expected_protocol = normalize_protocol_name(resolve_device_protocol(device, stream_context))
    incoming_protocol = normalize_protocol_name(auth_in.protocol)
    ingest_runtime_metadata.update_from_ingest_auth(
        device_key=device.key or stream_key,
        ip=auth_in.ip,
        protocol=incoming_protocol or expected_protocol,
    )
    log_ingest_info(
        device.key or stream_key,
        (
            "auth_received "
            f"device_id={device.id} protocol_in={incoming_protocol or '-'} "
            f"protocol_expected={expected_protocol or '-'} ip={auth_in.ip or '-'}"
        ),
    )
    logger.info(
        "ingest_auth_received key=%s device_id=%s protocol_in=%s protocol_expected=%s path=%s",
        device.key or stream_key,
        device.id,
        incoming_protocol or "-",
        expected_protocol or "-",
        auth_in.path or "-",
    )
    if expected_protocol and incoming_protocol and incoming_protocol != expected_protocol:
        log_ingest_warning(
            device.key or stream_key,
            f"auth_blocked protocol_mismatch expected={expected_protocol} received={incoming_protocol}",
        )
        logger.warning(
            "ingest_auth_blocked reason=protocol_mismatch key=%s device_id=%s expected=%s received=%s",
            device.key or stream_key,
            device.id,
            expected_protocol,
            incoming_protocol,
        )
        raise HTTPException(
            status_code=403,
            detail=f"Protocol mismatch for device: expected {expected_protocol}, received {incoming_protocol}.",
        )

    checked_at = datetime.now(timezone.utc)
    allow_detail: str | None = None
    allow_status: str | None = None

    if recorder_service.is_recording(device.id):
        allow_detail = "allow_recording_runtime"
        allow_status = DEVICE_STATUS_RECORDING

    open_record = await db.execute(
        select(Record.id).where(
            Record.device_id == device.id,
            Record.end_time.is_(None),
        ).limit(1)
    )
    if open_record.scalar() is not None and allow_detail is None:
        allow_detail = "allow_open_record"
        allow_status = DEVICE_STATUS_RECORDING

    access_rows = await db.execute(
        select(UserDeviceAccess.user_id).where(UserDeviceAccess.device_id == device.id)
    )
    authorized_user_ids = {int(row[0]) for row in access_rows.all()}
    has_online_owner = await realtime_hub.any_user_online(authorized_user_ids)
    has_online_master = await realtime_hub.any_superuser_online()
    if (has_online_owner or has_online_master) and allow_detail is None:
        allow_detail = "allow_viewer_online"
        allow_status = DEVICE_STATUS_CONNECTING

    if allow_detail is None:
        allow_detail = "allow_publish_authenticated"
        allow_status = DEVICE_STATUS_CONNECTING

    if allow_detail is not None and allow_status is not None:
        ingest_publish_state.mark_publish(device.id, checked_at=checked_at)
        metadata = ingest_runtime_metadata.get(device.key or stream_key)
        metadata_suffix = ""
        if metadata:
            metadata_suffix = (
                f" ip={metadata.get('ip') or '-'} protocol={metadata.get('protocol') or '-'}"
            )
        log_ingest_info(
            device.key or stream_key,
            (
                f"auth_allowed device_id={device.id} status={allow_status} detail={allow_detail}"
                f"{metadata_suffix}"
            ),
        )
        logger.info(
            "ingest_auth_allowed key=%s device_id=%s status=%s detail=%s owner_online=%s admin_online=%s",
            device.key or stream_key,
            device.id,
            allow_status,
            allow_detail,
            has_online_owner,
            has_online_master,
        )
        stream_url = build_device_stream_url(device, stream_context)
        await _emit_device_status_snapshot(
            db,
            device=device,
            status=allow_status,
            checked_at=checked_at,
            detail=f"ingest_publish_allowed:{allow_detail}",
        )
        return {"status": "ok", "detail": allow_detail}

    # Should not reach this branch, but preserve backward behavior if future logic changes.
    raise HTTPException(status_code=403, detail="Publish blocked.")
