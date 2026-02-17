import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints import manager_runtime as manager_runtime_endpoint
from app.core import security
from app.core.config import settings
from app.models.user import User
from app.services.ingest_upload_gateway import (
    IngestUploadGateway,
    UploadJob,
    calculate_minimum_upload_mbps,
    file_sha256,
)


def test_calculate_minimum_upload_mbps_formula() -> None:
    # Formula: N uploads x bitrate x 1.2 / 0.7
    result = calculate_minimum_upload_mbps(
        3,
        8.0,
        overhead_factor=1.2,
        link_utilization_target=0.7,
    )
    assert result == pytest.approx(41.1429, rel=0, abs=0.0001)


@pytest.mark.asyncio
async def test_ingest_gateway_retries_checksum_and_measured_bitrate(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"x" * (256 * 1024)
    video_file = tmp_path / "record_99.mp4"
    video_file.write_bytes(payload)
    expected_checksum = file_sha256(str(video_file))

    gateway = IngestUploadGateway()
    gateway.enabled = True
    gateway.upload_url = "http://gateway.example/upload"
    gateway.max_retries = 2
    gateway.retry_backoff_sec = 0.01
    gateway.history_file = tmp_path / "upload_history.jsonl"

    attempts: list[tuple[int, str]] = []

    async def fake_upload_once(
        *,
        job: UploadJob,
        file_size_bytes: int,
        checksum_sha256: str,
    ) -> int:
        attempts.append((file_size_bytes, checksum_sha256))
        if len(attempts) < 3:
            raise RuntimeError("temporary_upload_error")
        return 201

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(gateway, "_upload_once", fake_upload_once)
    monkeypatch.setattr("app.services.ingest_upload_gateway.asyncio.sleep", no_sleep)

    await gateway._process_job(
        UploadJob(
            record_id=99,
            file_path=str(video_file),
            queued_at="2026-02-09T12:00:00",
        ),
        worker_id=1,
    )

    assert len(attempts) == 3
    assert all(item[0] == len(payload) for item in attempts)
    assert all(item[1] == expected_checksum for item in attempts)

    status_payload = gateway.status()
    assert status_payload["successful_uploads"] == 1
    assert status_payload["failed_uploads"] == 0
    assert status_payload["measured_bitrate_avg_mbps"] is not None
    assert status_payload["measured_bitrate_avg_mbps"] > 0.0
    assert status_payload["recent_uploads"][-1]["success"] is True
    assert status_payload["recent_uploads"][-1]["attempt"] == 3

    history_lines = gateway.history_file.read_text(encoding="utf-8").splitlines()
    assert len(history_lines) == 3


@pytest.mark.asyncio
async def test_manager_runtime_ingest_gateway_endpoints_admin_only(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = User(
        username="admin_ingest_gateway_metrics",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    user = User(
        username="user_ingest_gateway_metrics",
        password=security.get_password_hash("123"),
        is_superuser=False,
        is_active=True,
    )
    db.add_all([admin, user])
    await db.commit()
    await db.refresh(admin)
    await db.refresh(user)

    admin_token = security.create_access_token(admin.id)
    user_token = security.create_access_token(user.id)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    user_headers = {"Authorization": f"Bearer {user_token}"}

    fake_status = {
        "enabled": True,
        "upload_url": "http://gateway.example/upload",
        "queue_size": 1,
        "in_flight": 1,
        "workers": 2,
        "retry_max_attempts": 4,
        "retry_backoff_sec": 1.0,
        "checksum_algorithm": "sha256",
        "successful_uploads": 3,
        "failed_uploads": 1,
        "measured_bitrate_last_mbps": 12.5,
        "measured_bitrate_avg_mbps": 11.7,
        "video_profile": {
            "resolution": "1080p",
            "codec": "h264",
            "configured_bitrate_mbps": 8.0,
        },
        "recent_uploads": [],
    }

    def fake_bandwidth(*, upload_count: int) -> dict:
        return {
            "upload_count": upload_count,
            "bitrate_mbps": 11.7,
            "bitrate_source": "measured",
            "overhead_factor": 1.2,
            "link_utilization_target": 0.7,
            "minimum_upload_mbps": round((upload_count * 11.7 * 1.2) / 0.7, 4),
            "video_profile": {
                "resolution": "1080p",
                "codec": "h264",
                "configured_bitrate_mbps": 8.0,
            },
        }

    monkeypatch.setattr(manager_runtime_endpoint.ingest_upload_gateway, "status", lambda: fake_status)
    monkeypatch.setattr(
        manager_runtime_endpoint.ingest_upload_gateway,
        "bandwidth_recommendation",
        fake_bandwidth,
    )

    forbidden_status = await client.get(
        f"{settings.API_V1_STR}/manager-runtime/ingest-gateway/status",
        headers=user_headers,
    )
    assert forbidden_status.status_code == 400

    status_response = await client.get(
        f"{settings.API_V1_STR}/manager-runtime/ingest-gateway/status",
        headers=admin_headers,
    )
    assert status_response.status_code == 200
    assert status_response.json()["checksum_algorithm"] == "sha256"

    bandwidth_response = await client.get(
        f"{settings.API_V1_STR}/manager-runtime/ingest-gateway/bandwidth?upload_count=4",
        headers=admin_headers,
    )
    assert bandwidth_response.status_code == 200
    assert bandwidth_response.json()["upload_count"] == 4
    assert bandwidth_response.json()["minimum_upload_mbps"] == pytest.approx(80.2286, rel=0, abs=0.0001)
