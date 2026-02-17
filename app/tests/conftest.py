import asyncio
import os
import shutil
import pytest
from typing import AsyncGenerator
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.sql import text
import asyncpg

from app.main import app
from app.db.base import Base
import app.models.city as _city  # noqa: F401
import app.models.device as _device  # noqa: F401
import app.models.mark as _mark  # noqa: F401
import app.models.place as _place  # noqa: F401
import app.models.procedure as _procedure  # noqa: F401
import app.models.protocol as _protocol  # noqa: F401
import app.models.record as _record  # noqa: F401
import app.models.user_device_access as _user_device_access  # noqa: F401
import app.models.user as _user  # noqa: F401
import app.models.user_notification as _user_notification  # noqa: F401
import app.models.user_notification_viewer_state as _user_notification_viewer_state  # noqa: F401
import app.models.user_profile_photo as _user_profile_photo  # noqa: F401
import app.models.app_setting as _app_setting  # noqa: F401
from app.db.session import get_db
from app.core.config import settings
from app.services.recorder import recorder_service
from app.services.device_runtime_state import device_runtime_state
from app.services.ingest_publish_state import ingest_publish_state
from app.services.ingest_runtime_metadata import ingest_runtime_metadata
from app.services.realtime_events import reset_device_status_cache

# Use a test database
SQLALCHEMY_DATABASE_URL = settings.SQLALCHEMY_DATABASE_URI + "_test"
TEST_DB_NAME = f"{settings.POSTGRES_DB}_test"

engine = create_async_engine(SQLALCHEMY_DATABASE_URL, poolclass=NullPool, future=True)
TestingSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

# event_loop fixture removed - let pytest-asyncio handle it

@pytest.fixture(scope="session", autouse=True)
async def setup_test_db():
    previous_recordings_dir = recorder_service.recordings_dir
    test_recordings_dir = ".runtime/test_recordings"
    shutil.rmtree(test_recordings_dir, ignore_errors=True)
    os.makedirs(test_recordings_dir, exist_ok=True)
    recorder_service.set_recordings_dir(test_recordings_dir)

    # Ensure test database exists
    admin_dsn = (
        f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}/postgres"
    )
    conn = await asyncpg.connect(admin_dsn)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB_NAME)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    finally:
        await conn.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    shutil.rmtree(test_recordings_dir, ignore_errors=True)
    recorder_service.set_recordings_dir(previous_recordings_dir)

@pytest.fixture
async def db():
    async with TestingSessionLocal() as session:
        yield session

@pytest.fixture
async def client():
    async with TestingSessionLocal() as session:
        app.dependency_overrides[get_db] = lambda: session
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac
        app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def reset_runtime_state() -> None:
    ingest_publish_state.clear_all()
    ingest_runtime_metadata.clear_all()
    reset_device_status_cache()
    device_runtime_state.clear_all()
