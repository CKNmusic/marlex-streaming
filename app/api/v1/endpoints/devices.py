import io
import qrcode
from typing import Any, List, Optional
import asyncio
import shutil
import ipaddress
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlparse, urlunparse
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.session import get_db
from app.models.user import User
from app.models.device import Device
from app.models.mark import Mark
from app.models.app_setting import AppSetting
from app.models.protocol import Protocol
from app.models.user_device_access import UserDeviceAccess
from app.models.place import Place
from app.models.record import Record
from app.schemas.device import DeviceCreate, DeviceUpdate, Device as DeviceSchema, DeviceBind, DeviceStatus
from app.services.recorder import recorder_service
from app.services.realtime_events import emit_device_status
from app.services.stream_protocols import (
    ffmpeg_input_args_for_url,
    ffprobe_input_args_for_url,
    is_known_protocol,
    normalize_protocol_name,
)
from app.services.ingest_presence import ingest_stream_url_is_online
from app.services.ingest_control import kick_mismatched_source_for_path
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
    RUNTIME_ACTIVE_DEVICE_STATUSES,
    is_device_online_status,
    normalize_device_status,
)
from app.services.ingest_publish_state import ingest_publish_state
from app.services.ingest_runtime_metadata import ingest_runtime_metadata
from app.services.device_runtime_state import device_runtime_state
from app.services.ingest_stream_profile import (
    get_cached_stream_profile,
    normalize_protocol_from_url,
    schedule_stream_profile_probe,
)
from app.api import deps
from app.core.config import settings

router = APIRouter()
ONLINE_STATUS_GRACE_SECONDS = max(int(settings.DEVICE_STATUS_OFFLINE_GRACE_SECONDS), 0)
CONNECTING_TIMEOUT_SECONDS = max(int(settings.DEVICE_CONNECTING_TIMEOUT_SECONDS), 1)
SNAPSHOT_STALE_AFTER = timedelta(
    seconds=max(
        int(settings.DEVICE_STATUS_OFFLINE_GRACE_SECONDS + (settings.DEVICE_PRESENCE_MONITOR_INTERVAL_SEC * 2)),
        8,
    )
)


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
    grace_seconds: int = ONLINE_STATUS_GRACE_SECONDS,
) -> bool:
    normalized_checked_at = _to_utc_naive(checked_at) or checked_at
    normalized_last_seen = _to_utc_naive(last_seen)
    if normalized_last_seen is None:
        return False
    return (normalized_checked_at - normalized_last_seen) <= timedelta(seconds=grace_seconds)


def _is_loopback_hostname(hostname: Optional[str]) -> bool:
    value = str(hostname or "").strip().lower()
    if not value:
        return False
    if value in {"localhost", "::1"}:
        return True
    return value.startswith("127.")


def _is_ip_hostname(hostname: Optional[str]) -> bool:
    value = str(hostname or "").strip()
    if not value:
        return False
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _build_device_scan_url(public_host: Optional[str], device_key: str) -> str:
    default_base = f"http://{settings.APP_HOST}:3000/{settings.APP_NAME}"
    raw_host = (public_host or "").strip() or default_base
    if not raw_host.startswith(("http://", "https://")):
        raw_host = f"http://{raw_host}"

    parsed = urlparse(raw_host)
    scheme = parsed.scheme if parsed.scheme in {"http", "https"} else "http"
    netloc = parsed.netloc or parsed.path
    path = parsed.path if parsed.netloc else ""
    if not netloc:
        netloc = settings.APP_HOST

    parsed_host = parsed.hostname
    parsed_port = parsed.port
    configured_host = str(settings.APP_HOST or "").strip()
    if _is_loopback_hostname(parsed_host) and configured_host and not _is_loopback_hostname(configured_host):
        parsed_host = configured_host

    effective_host = str(parsed_host or settings.APP_HOST or "").strip() or "127.0.0.1"
    effective_port = parsed_port
    if effective_port is None and _is_ip_hostname(effective_host):
        effective_port = 3000
    netloc = f"{effective_host}:{effective_port}" if effective_port is not None else effective_host

    base_path = path.rstrip("/")
    if not base_path:
        base_path = f"/{settings.APP_NAME}"

    scan_path = f"{base_path}/scan"
    query = f"key={quote(device_key, safe='')}"
    return urlunparse((scheme, netloc, scan_path, "", query, ""))


def resolve_device_integrity_error_detail(error: IntegrityError) -> str:
    raw = str(getattr(error, "orig", error)).lower()
    if "uq_devices_sn_mark" in raw or ("unique" in raw and "sn" in raw and "mark" in raw):
        return "Já existe um dispositivo com esse SN para esta marca."
    if "devices_sn_key" in raw or ("unique" in raw and "sn" in raw):
        return "Já existe um dispositivo com esse SN."
    if "devices_key_key" in raw or ("unique" in raw and "key" in raw):
        return "Conflito de chave do dispositivo. Tente novamente."
    return "Conflito de dados ao salvar dispositivo."


def _normalize_text(value: Optional[str]) -> str:
    return str(value or "").strip()


def _split_mark_and_model(raw_name: str) -> tuple[str, str]:
    normalized = " ".join(raw_name.split()).strip()
    if not normalized:
        return "", ""
    pieces = normalized.split(" ", 1)
    if len(pieces) == 1:
        return pieces[0], pieces[0]
    return pieces[0], pieces[1].strip() or pieces[0]


def _resolve_device_identity_parts(
    *,
    raw_model: Optional[str],
    raw_name: Optional[str],
    raw_mark_name: Optional[str],
) -> tuple[str, Optional[str]]:
    model = _normalize_text(raw_model)
    legacy_name = _normalize_text(raw_name)
    mark_name = _normalize_text(raw_mark_name)

    if not model and legacy_name:
        split_mark, split_model = _split_mark_and_model(legacy_name)
        model = split_model or legacy_name
        if not mark_name and split_mark:
            mark_name = split_mark
    if not model:
        raise HTTPException(status_code=422, detail="Modelo do dispositivo é obrigatório.")

    return model, (mark_name or None)


async def _find_or_create_mark_id(
    db: AsyncSession,
    *,
    mark_id: Optional[int] = None,
    mark_name: Optional[str] = None,
) -> int:
    if mark_id is not None:
        result = await db.execute(select(Mark).where(Mark.id == int(mark_id)))
        mark = result.scalars().first()
        if not mark:
            raise HTTPException(status_code=404, detail="Marca não encontrada.")
        return int(mark.id)

    normalized_name = _normalize_text(mark_name)
    if normalized_name:
        result = await db.execute(
            select(Mark).where(func.lower(Mark.name) == normalized_name.lower())
        )
        mark = result.scalars().first()
        if mark:
            return int(mark.id)
        new_mark = Mark(name=normalized_name, is_active=True)
        db.add(new_mark)
        await db.flush()
        return int(new_mark.id)

    result = await db.execute(select(Mark).where(func.lower(Mark.name) == "generic").limit(1))
    mark = result.scalars().first()
    if mark:
        return int(mark.id)
    generic = Mark(name="Generic", is_active=True)
    db.add(generic)
    await db.flush()
    return int(generic.id)


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

    # Fallback when ffprobe binary is unavailable but ffmpeg exists.
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


async def get_open_record_owner_id(db: AsyncSession, device_id: int) -> Optional[int]:
    result = await db.execute(
        select(Record.owner_id)
        .where(
            and_(
                Record.device_id == device_id,
                Record.end_time.is_(None),
            )
        )
        .order_by(Record.start_time.desc())
        .limit(1)
    )
    owner_id = result.scalar()
    return int(owner_id) if owner_id is not None else None


async def resolve_writable_device_protocol_id(
    db: AsyncSession,
    raw_protocol: Optional[str],
) -> int:
    context = await load_device_stream_context(db)
    if not context.protocol_id_by_name:
        db.add(Protocol(protocol="srt", port=9000, is_active=True))
        db.add(Protocol(protocol="rtmp", port=8554, is_active=True))
        await db.flush()
        context = await load_device_stream_context(db)
        if not context.protocol_id_by_name:
            raise HTTPException(status_code=422, detail="Nenhum protocol ativo disponível.")

    normalized = normalize_protocol_name(raw_protocol)
    if not normalized:
        if context.default_protocol_id is None:
            raise HTTPException(status_code=422, detail="Protocol padrão não configurado.")
        return int(context.default_protocol_id)
    if not is_known_protocol(normalized):
        raise HTTPException(status_code=422, detail="Protocol não suportado.")
    protocol_id = context.protocol_id_by_name.get(normalized)
    if context.ports_by_protocol and protocol_id is None:
        active_protocols = ", ".join(sorted(context.ports_by_protocol.keys()))
        detail = "Protocol não encontrado entre os protocolos ativos."
        if active_protocols:
            detail = f"{detail} Ativos: {active_protocols}."
        raise HTTPException(status_code=422, detail=detail)
    if protocol_id is None:
        raise HTTPException(status_code=422, detail="Protocol inválido para o contexto atual.")
    return int(protocol_id)


async def refresh_device_runtime_status(
    db: AsyncSession,
    *,
    device: Device,
    detail: str,
    use_grace: bool = True,
) -> DeviceStatus:
    stream_context = await load_device_stream_context(db)
    stream_url = build_device_stream_url(device, stream_context)
    checked_at = datetime.now(timezone.utc)
    runtime_snapshot = device_runtime_state.get(int(device.id))
    runtime_state = normalize_device_status(recorder_service.get_state(device.id))
    persisted_status = normalize_device_status(
        runtime_snapshot.status if runtime_snapshot is not None else None,
        fallback=DEVICE_STATUS_OFFLINE,
    )
    persisted_online = bool(runtime_snapshot.online) if runtime_snapshot is not None else False
    persisted_checked_at = runtime_snapshot.checked_at if runtime_snapshot is not None else None
    persisted_metadata = runtime_snapshot.metadata if runtime_snapshot is not None else None
    is_recording = recorder_service.is_recording(device.id)
    has_recent_publish = ingest_publish_state.has_recent_publish(
        int(device.id),
        within_seconds=CONNECTING_TIMEOUT_SECONDS,
    )

    should_refresh_last_seen = False

    if runtime_state in RUNTIME_ACTIVE_DEVICE_STATUSES:
        status_value = runtime_state
        online = is_device_online_status(runtime_state)
        should_refresh_last_seen = True
    elif is_recording:
        status_value = DEVICE_STATUS_RECORDING
        online = True
        should_refresh_last_seen = True
    else:
        stream_online = await probe_stream(stream_url)
        if stream_online:
            metadata = ingest_runtime_metadata.update_protocol_hint(
                device_key=device.key,
                protocol=normalize_protocol_from_url(stream_url or ""),
            )
            cached_profile = get_cached_stream_profile(device.key or "")
            if cached_profile:
                metadata = ingest_runtime_metadata.update_from_stream_profile(
                    device_key=device.key,
                    profile=cached_profile,
                )
            metadata = ingest_runtime_metadata.sanitize(metadata)
            if ingest_runtime_metadata.is_complete(metadata):
                online = True
                status_value = DEVICE_STATUS_ONLINE
                should_refresh_last_seen = True
            else:
                online = False
                status_value = DEVICE_STATUS_CONNECTING
                should_refresh_last_seen = False
                schedule_stream_profile_probe(
                    device_key=device.key or "",
                    stream_url=stream_url,
                    protocol=metadata.get("protocol") if isinstance(metadata, dict) else None,
                    context="devices_refresh:metadata_pending",
                )
        elif has_recent_publish:
            online = False
            status_value = DEVICE_STATUS_CONNECTING
            should_refresh_last_seen = False
        else:
            online = False
            can_keep_online_in_grace = (
                persisted_online
                or is_device_online_status(persisted_status)
            )
            if (
                use_grace
                and _is_within_online_grace(
                    checked_at=checked_at,
                    last_seen=persisted_checked_at,
                    grace_seconds=ONLINE_STATUS_GRACE_SECONDS,
                )
                and can_keep_online_in_grace
            ):
                online = True
                status_value = (
                    persisted_status
                    if is_device_online_status(persisted_status)
                    else DEVICE_STATUS_ONLINE
                )
                should_refresh_last_seen = False
            else:
                status_value = DEVICE_STATUS_OFFLINE
                should_refresh_last_seen = False
                ingest_runtime_metadata.clear(device.key)

    next_metadata = ingest_runtime_metadata.sanitize(ingest_runtime_metadata.get(device.key))
    status_changed = (persisted_status != status_value) or (persisted_online != online)
    metadata_changed = (persisted_metadata or None) != (next_metadata or None)
    effective_checked_at = checked_at if should_refresh_last_seen else (persisted_checked_at or checked_at)

    if status_changed or metadata_changed:
        await emit_device_status(
            db,
            device_id=device.id,
            status=status_value,
            online=online,
            stream_url=stream_url,
            checked_at=effective_checked_at,
            detail=detail,
            metadata=next_metadata,
        )
    else:
        device_runtime_state.upsert(
            device_id=int(device.id),
            status=status_value,
            online=online,
            stream_url=stream_url,
            checked_at=effective_checked_at,
            metadata=next_metadata,
        )

    return DeviceStatus(
        device_id=device.id,
        online=online,
        status=status_value,
        stream_url=stream_url,
        checked_at=effective_checked_at,
        metadata=next_metadata,
    )


def _resolve_runtime_status_snapshot(
    *,
    device: Device,
    stream_url: str,
) -> DeviceStatus:
    now = datetime.now(timezone.utc)
    runtime_state = normalize_device_status(recorder_service.get_state(device.id))
    runtime_snapshot = device_runtime_state.get(int(device.id))

    if runtime_state in RUNTIME_ACTIVE_DEVICE_STATUSES:
        checked_at = now
        metadata = runtime_snapshot.metadata if runtime_snapshot and runtime_snapshot.metadata else None
        return DeviceStatus(
            device_id=device.id,
            online=True,
            status=runtime_state,
            stream_url=stream_url,
            checked_at=checked_at,
            metadata=metadata,
        )

    if runtime_snapshot is None:
        return DeviceStatus(
            device_id=device.id,
            online=False,
            status=DEVICE_STATUS_OFFLINE,
            stream_url=stream_url,
            checked_at=now,
            metadata=None,
        )

    checked_at = runtime_snapshot.checked_at
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)

    status_value = normalize_device_status(runtime_snapshot.status, fallback=DEVICE_STATUS_OFFLINE)
    is_stale = (now - checked_at) > SNAPSHOT_STALE_AFTER
    if is_stale and status_value not in RUNTIME_ACTIVE_DEVICE_STATUSES:
        status_value = DEVICE_STATUS_OFFLINE
        online = False
    else:
        online = bool(runtime_snapshot.online) or is_device_online_status(status_value)

    return DeviceStatus(
        device_id=device.id,
        online=online,
        status=status_value,
        stream_url=runtime_snapshot.stream_url or stream_url,
        checked_at=checked_at,
        metadata=runtime_snapshot.metadata if runtime_snapshot.metadata else None,
    )


@router.get("/{device_id}/qrcode", responses={200: {"content": {"image/png": {}}}})
async def generate_device_qrcode(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
):
    """
    Generate QR Code PNG with canonical scan URL for a device key. Admin only.
    """
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
        
    if not device.key:
        # If key is not generated, generate it.
        device.generate_key()
        db.add(device)
        await db.commit()
        await db.refresh(device)
    if not device.key:
        raise HTTPException(status_code=409, detail="Device key indisponível para geração de QR Code.")

    app_setting_result = await db.execute(select(AppSetting).order_by(AppSetting.id).limit(1))
    app_setting = app_setting_result.scalars().first()
    qr_data = _build_device_scan_url(app_setting.host if app_setting else None, device.key)

    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    
    return Response(content=buf.getvalue(), media_type="image/png")

@router.get("/", response_model=List[DeviceSchema])
async def read_devices(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Retrieve devices.
    - Master: all devices
    - User: only scanned/bound devices
    """
    if current_user.is_superuser:
        query = select(Device).order_by(Device.id).offset(skip).limit(limit)
        result = await db.execute(query)
        devices = result.scalars().all()
    else:
        query = (
            select(Device)
            .join(UserDeviceAccess, UserDeviceAccess.device_id == Device.id)
            .where(UserDeviceAccess.user_id == current_user.id)
            .order_by(Device.id)
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(query)
        devices = result.scalars().all()

    stream_context = await load_device_stream_context(db)
    for device in devices:
        status_snapshot = _resolve_runtime_status_snapshot(
            device=device,
            stream_url=build_device_stream_url(device, stream_context),
        )
        device.status = status_snapshot.status
        device.last_seen = status_snapshot.checked_at
    return devices

@router.get("/status", response_model=List[DeviceStatus])
async def read_devices_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Runtime status snapshot with refresh from ingest/runtime probes.
    No runtime status is persisted to DB; memory overlay is authoritative.
    """
    result = await db.execute(select(Device))
    devices = result.scalars().all()
    payload: List[DeviceStatus] = []
    stream_context = await load_device_stream_context(db)
    for device in devices:
        payload.append(
            _resolve_runtime_status_snapshot(
                device=device,
                stream_url=build_device_stream_url(device, stream_context),
            )
        )
    return payload

@router.post("/bind", response_model=DeviceSchema)
async def bind_device(
    *,
    db: AsyncSession = Depends(get_db),
    bind_in: DeviceBind,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Bind a device key to current user (scan authorization).
    """
    result = await db.execute(select(Device).where(Device.key == bind_in.key))
    device = result.scalars().first()
    
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo não encontrado")
    if not device.is_active:
        raise HTTPException(status_code=403, detail="Dispositivo inativo")
    open_record_owner_id = await get_open_record_owner_id(db, device.id)
    if (
        open_record_owner_id is not None
        and open_record_owner_id != current_user.id
        and not current_user.is_superuser
    ):
        raise HTTPException(status_code=409, detail="Dispositivo em uso por outra gravação ativa.")

    await db.execute(
        pg_insert(UserDeviceAccess)
        .values(user_id=current_user.id, device_id=device.id)
        .on_conflict_do_nothing(
            index_elements=[UserDeviceAccess.user_id, UserDeviceAccess.device_id]
        )
    )
    await db.commit()

    await refresh_device_runtime_status(db, device=device, detail="bind", use_grace=False)

    return device


@router.get("/{device_id}/bind-status", response_model=DeviceStatus)
async def read_device_bind_status(
    *,
    db: AsyncSession = Depends(get_db),
    device_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Resolve current bind/connection status for one device.
    """
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalars().first()

    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo não encontrado")
    if not device.is_active:
        raise HTTPException(status_code=403, detail="Dispositivo inativo")

    if not current_user.is_superuser:
        access_result = await db.execute(
            select(UserDeviceAccess.id).where(
                and_(
                    UserDeviceAccess.user_id == current_user.id,
                    UserDeviceAccess.device_id == device.id,
                )
            )
        )
        if access_result.scalar() is None:
            raise HTTPException(status_code=403, detail="Dispositivo não autorizado para este usuário.")

    return await refresh_device_runtime_status(db, device=device, detail="bind_status", use_grace=False)

@router.post("/", response_model=DeviceSchema)
async def create_device(
    *,
    db: AsyncSession = Depends(get_db),
    device_in: DeviceCreate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Create new device. Admin only.
    """
    res_place = await db.execute(select(Place).where(Place.id == device_in.place_id))
    if not res_place.scalars().first():
        raise HTTPException(status_code=404, detail="Place não encontrado")
    model_value, mark_name_value = _resolve_device_identity_parts(
        raw_model=device_in.model,
        raw_name=device_in.name,
        raw_mark_name=device_in.mark_name,
    )
    mark_id = await _find_or_create_mark_id(
        db,
        mark_id=device_in.mark_id,
        mark_name=mark_name_value,
    )
    protocol_id = await resolve_writable_device_protocol_id(db, device_in.protocol)
    next_sn = _normalize_text(device_in.sn)
    if not next_sn:
        raise HTTPException(status_code=422, detail="SN obrigatório")
    duplicate_sn = await db.execute(
        select(Device.id)
        .where(and_(Device.sn == next_sn, Device.mark_id == mark_id))
        .limit(1)
    )
    if duplicate_sn.scalar() is not None:
        raise HTTPException(status_code=409, detail="Já existe um dispositivo com esse SN para esta marca.")

    device = Device(
        model=model_value,
        sn=next_sn,
        mark_id=mark_id,
        protocol_id=protocol_id,
        place_id=device_in.place_id,
        is_active=device_in.is_active
    )
    try:
        db.add(device)
        await db.flush()  # Get ID for key generation
        device.generate_key()
        await db.commit()
        await db.refresh(device)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=resolve_device_integrity_error_detail(exc))
    return device

@router.patch("/{device_id}", response_model=DeviceSchema)
async def update_device(
    *,
    db: AsyncSession = Depends(get_db),
    device_id: int,
    device_in: DeviceUpdate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Update a device. Admin only.
    """
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    stream_context = await load_device_stream_context(db)
    previous_protocol = resolve_device_protocol(device, stream_context)
    update_data = device_in.model_dump(exclude_unset=True)
    if update_data.get("is_active") is False and device.is_active:
        record_ref = await db.execute(
            select(Record.id).where(Record.device_id == device_id).limit(1)
        )
        if record_ref.scalar() is not None:
            raise HTTPException(status_code=400, detail="Dispositivo em uso, não pode desativar.")

    if "place_id" in update_data and update_data["place_id"] is None:
        raise HTTPException(status_code=422, detail="Place obrigatório")
    if "place_id" in update_data:
        res_place = await db.execute(select(Place).where(Place.id == update_data["place_id"]))
        if not res_place.scalars().first():
            raise HTTPException(status_code=404, detail="Place não encontrado")

    if any(field in update_data for field in ("model", "name")):
        model_value, _ = _resolve_device_identity_parts(
            raw_model=update_data.get("model"),
            raw_name=update_data.get("name"),
            raw_mark_name=update_data.get("mark_name"),
        )
        update_data["model"] = model_value
        update_data.pop("name", None)

    if "mark_id" in update_data or "mark_name" in update_data:
        mark_name_value = _normalize_text(update_data.get("mark_name"))
        update_data["mark_id"] = await _find_or_create_mark_id(
            db,
            mark_id=update_data.get("mark_id"),
            mark_name=mark_name_value,
        )
        update_data.pop("mark_name", None)

    if "protocol" in update_data:
        update_data["protocol_id"] = await resolve_writable_device_protocol_id(
            db,
            update_data.get("protocol"),
        )
        update_data.pop("protocol", None)
    if "sn" in update_data:
        next_sn = str(update_data.get("sn") or "").strip()
        if not next_sn:
            raise HTTPException(status_code=422, detail="SN obrigatório")
        target_mark_id = int(update_data.get("mark_id") or device.mark_id)
        duplicate_sn = await db.execute(
            select(Device.id)
            .where(
                and_(
                    Device.sn == next_sn,
                    Device.mark_id == target_mark_id,
                    Device.id != device_id,
                )
            )
            .limit(1)
        )
        if duplicate_sn.scalar() is not None:
            raise HTTPException(status_code=409, detail="Já existe um dispositivo com esse SN para esta marca.")
        update_data["sn"] = next_sn
    elif "mark_id" in update_data:
        duplicate_sn = await db.execute(
            select(Device.id)
            .where(
                and_(
                    Device.sn == device.sn,
                    Device.mark_id == int(update_data["mark_id"]),
                    Device.id != device_id,
                )
            )
            .limit(1)
        )
        if duplicate_sn.scalar() is not None:
            raise HTTPException(status_code=409, detail="Já existe um dispositivo com esse SN para esta marca.")
    next_protocol = normalize_protocol_name(previous_protocol)
    if "protocol_id" in update_data:
        next_protocol = stream_context.protocol_name_by_id.get(int(update_data["protocol_id"]), previous_protocol)
    protocol_changed = bool(next_protocol and normalize_protocol_name(next_protocol) != normalize_protocol_name(previous_protocol))

    for field, value in update_data.items():
        setattr(device, field, value)

    try:
        db.add(device)
        await db.commit()
        await db.refresh(device)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=resolve_device_integrity_error_detail(exc))

    if protocol_changed and device.key:
        stream_path = f"{settings.APP_NAME}/{settings.APP_VERSION}/{device.key}/stream"
        stream_context = await load_device_stream_context(db)
        expected_protocol = resolve_device_protocol(device, stream_context)
        kicked = await kick_mismatched_source_for_path(
            path_name=stream_path,
            expected_protocol=expected_protocol,
        )
        if kicked:
            await refresh_device_runtime_status(
                db,
                device=device,
                detail="protocol_mismatch_kicked",
            )
    return device

@router.delete("/{device_id}", response_model=DeviceSchema)
async def delete_device(
    *,
    db: AsyncSession = Depends(get_db),
    device_id: int,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Delete a device. Admin only.
    """
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    record_ref = await db.execute(
        select(Record.id).where(Record.device_id == device_id).limit(1)
    )
    if record_ref.scalar() is not None:
        raise HTTPException(status_code=400, detail="Dispositivo em uso, desative.")

    await db.delete(device)
    await db.commit()
    return device
