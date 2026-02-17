from datetime import datetime, timezone

import pytest

from app.models.city import City
from app.models.device import Device
from app.models.place import Place
from app.services.device_status import DEVICE_STATUS_OFFLINE, DEVICE_STATUS_ONLINE
from app.services.startup_runtime_reset import reset_devices_runtime_state


@pytest.mark.asyncio
async def test_startup_reset_sets_devices_offline_and_clears_last_seen(db) -> None:
    city = City(name="Cidade Reset", uf="RS")
    db.add(city)
    await db.flush()

    place = Place(name="Local Reset", description="Sala", city_id=city.id)
    db.add(place)
    await db.flush()

    device = Device(
        model="Device Reset",
        sn="SN-RESET-0001",
        place_id=place.id,
        is_active=True,
        status=DEVICE_STATUS_ONLINE,
        last_seen=datetime.now(timezone.utc),
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)

    assert device.status == DEVICE_STATUS_ONLINE
    assert device.last_seen is not None

    updated = await reset_devices_runtime_state(db)
    await db.commit()
    await db.refresh(device)

    assert updated >= 1
    assert device.status == DEVICE_STATUS_OFFLINE
    assert device.last_seen is None
