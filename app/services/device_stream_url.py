from dataclasses import dataclass
from typing import Dict, Optional
from urllib.parse import quote, urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.app_setting import AppSetting
from app.models.device import Device
from app.models.protocol import Protocol
from app.services.stream_protocols import (
    normalize_protocol_name,
    resolve_protocol_default_port,
)


@dataclass(frozen=True)
class DeviceStreamContext:
    host: str
    default_protocol: str
    default_protocol_id: Optional[int]
    ports_by_protocol: Dict[str, int]
    protocol_id_by_name: Dict[str, int]
    protocol_name_by_id: Dict[int, str]


def _extract_host(raw_host: Optional[str]) -> str:
    value = (raw_host or "").strip()
    if not value:
        return settings.APP_HOST
    if "://" not in value:
        value = f"http://{value}"
    parsed = urlparse(value)
    return parsed.hostname or settings.APP_HOST


async def load_device_stream_context(db: AsyncSession) -> DeviceStreamContext:
    app_host_result = await db.execute(select(AppSetting.host).order_by(AppSetting.id).limit(1))
    host = _extract_host(app_host_result.scalar_one_or_none())

    protocol_result = await db.execute(select(Protocol).where(Protocol.is_active.is_(True)).order_by(Protocol.id))
    protocols = protocol_result.scalars().all()

    ports_by_protocol: Dict[str, int] = {}
    protocol_id_by_name: Dict[str, int] = {}
    protocol_name_by_id: Dict[int, str] = {}
    default_protocol = "srt"

    for protocol in protocols:
        name = normalize_protocol_name(protocol.protocol)
        if not name:
            continue
        ports_by_protocol[name] = int(protocol.port)
        protocol_id_by_name[name] = int(protocol.id)
        protocol_name_by_id[int(protocol.id)] = name

    if default_protocol not in ports_by_protocol:
        if "rtmp" in ports_by_protocol:
            default_protocol = "rtmp"
        elif ports_by_protocol:
            default_protocol = next(iter(ports_by_protocol))

    return DeviceStreamContext(
        host=host,
        default_protocol=default_protocol,
        default_protocol_id=protocol_id_by_name.get(default_protocol),
        ports_by_protocol=ports_by_protocol,
        protocol_id_by_name=protocol_id_by_name,
        protocol_name_by_id=protocol_name_by_id,
    )


def resolve_device_protocol(device: Device, context: DeviceStreamContext) -> str:
    preferred_id = getattr(device, "protocol_id", None)
    if preferred_id is not None:
        preferred_name = context.protocol_name_by_id.get(int(preferred_id))
        if preferred_name and (not context.ports_by_protocol or preferred_name in context.ports_by_protocol):
            return preferred_name

    preferred = normalize_protocol_name(getattr(device, "protocol", None))
    if preferred and (not context.ports_by_protocol or preferred in context.ports_by_protocol):
        return preferred
    return context.default_protocol


def build_device_stream_url(device: Device, context: DeviceStreamContext) -> Optional[str]:
    device_key = (device.key or "").strip()
    if not device_key:
        return None

    protocol = resolve_device_protocol(device, context)
    port = context.ports_by_protocol.get(
        protocol,
        resolve_protocol_default_port(protocol, fallback=8554),
    )
    key_path = quote(device_key, safe="")
    stream_path = f"{settings.APP_NAME}/{settings.APP_VERSION}/{key_path}/stream"
    if protocol == "srt":
        # For SRT, consume stream as reader via streamid instead of path-style publish URL.
        query_parts = [f"streamid=read:{stream_path}"]
        passphrase = str(settings.SRT_PASSPHRASE or "").strip()
        if passphrase:
            pbkeylen = int(settings.SRT_PBKEYLEN or 32)
            if pbkeylen not in {16, 24, 32}:
                pbkeylen = 32
            query_parts.append(f"passphrase={quote(passphrase, safe='')}")
            query_parts.append(f"pbkeylen={pbkeylen}")
        return f"srt://{context.host}:{port}?{'&'.join(query_parts)}"
    return f"{protocol}://{context.host}:{port}/{stream_path}"
