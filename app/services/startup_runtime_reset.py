import logging

from sqlalchemy import or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.services.device_status import DEVICE_STATUS_OFFLINE

logger = logging.getLogger(__name__)


async def reset_devices_runtime_state(db: AsyncSession) -> int:
    """
    On API boot, runtime state must start from offline and be rebuilt from
    fresh probes/heartbeats.
    """
    stmt = (
        update(Device)
        .where(
            or_(
                Device.status != DEVICE_STATUS_OFFLINE,
                Device.last_seen.is_not(None),
            )
        )
        .values(
            status=DEVICE_STATUS_OFFLINE,
            last_seen=None,
        )
    )
    result = await db.execute(stmt)
    updated = int(result.rowcount or 0)
    if updated > 0:
        logger.info("startup_runtime_reset devices_offline=%s", updated)
    return updated
