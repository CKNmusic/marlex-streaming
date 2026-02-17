import pytest
from sqlalchemy import func, select

from app import initial_data
from app.db.base import Base
from app.models.app_setting import AppSetting
from app.models.city import City
from app.models.device import Device
from app.models.place import Place
from app.models.procedure import Procedure
from app.models.protocol import Protocol
from app.models.record import Record
from app.models.user import User
from app.tests.conftest import TestingSessionLocal, engine


async def reset_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


@pytest.mark.asyncio
async def test_seed_empty_database_creates_expected_data(monkeypatch: pytest.MonkeyPatch):
    await reset_schema()
    monkeypatch.setattr(initial_data, "SessionLocal", TestingSessionLocal)

    await initial_data.init_db()

    async with TestingSessionLocal() as db:
        users_count = await db.scalar(select(func.count(User.id)))
        devices_count = await db.scalar(select(func.count(Device.id)))
        protocols_count = await db.scalar(select(func.count(Protocol.id)))
        procedures_count = await db.scalar(select(func.count(Procedure.id)))
        records_count = await db.scalar(select(func.count(Record.id)))
        cities_count = await db.scalar(select(func.count(City.id)))
        places_count = await db.scalar(select(func.count(Place.id)))
        app_settings_count = await db.scalar(select(func.count(AppSetting.id)))

        assert users_count == 5
        assert devices_count == 2
        assert protocols_count == 2
        assert procedures_count == 3
        assert records_count == 1
        assert cities_count == 4
        assert places_count == 4
        assert app_settings_count == 1

        devices = (await db.execute(select(Device))).scalars().all()
        assert all(device.key for device in devices)
        assert len({device.key for device in devices}) == len(devices)

        # Sequence must be aligned to avoid duplicate key on runtime insert.
        owner = (await db.execute(select(User).where(User.username == "admin"))).scalars().first()
        device = (await db.execute(select(Device).where(Device.sn == "29252"))).scalars().first()
        procedure = (await db.execute(select(Procedure).where(Procedure.name == "Bariatrica"))).scalars().first()
        assert owner is not None
        assert device is not None
        assert procedure is not None

        runtime_record = Record(
            device_id=device.id,
            procedure_id=procedure.id,
            owner_id=owner.id,
            place_id=device.place_id,
            title="Runtime Record",
        )
        db.add(runtime_record)
        await db.commit()
        await db.refresh(runtime_record)
        assert runtime_record.id >= 2


@pytest.mark.asyncio
async def test_seed_is_idempotent(monkeypatch: pytest.MonkeyPatch):
    await reset_schema()
    monkeypatch.setattr(initial_data, "SessionLocal", TestingSessionLocal)

    await initial_data.init_db()
    await initial_data.init_db()

    async with TestingSessionLocal() as db:
        users_count = await db.scalar(select(func.count(User.id)))
        devices_count = await db.scalar(select(func.count(Device.id)))
        protocols_count = await db.scalar(select(func.count(Protocol.id)))
        procedures_count = await db.scalar(select(func.count(Procedure.id)))
        records_count = await db.scalar(select(func.count(Record.id)))
        cities_count = await db.scalar(select(func.count(City.id)))
        places_count = await db.scalar(select(func.count(Place.id)))
        app_settings_count = await db.scalar(select(func.count(AppSetting.id)))

        assert users_count == 5
        assert devices_count == 2
        assert protocols_count == 2
        assert procedures_count == 3
        assert records_count == 1
        assert cities_count == 4
        assert places_count == 4
        assert app_settings_count == 1

        record_ids = (await db.execute(select(Record.id).order_by(Record.id))).scalars().all()
        assert record_ids == [1]
