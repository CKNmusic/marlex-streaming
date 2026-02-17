from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.services.output_format import output_media_type


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def file_sha256(file_path: str, *, chunk_size: int = 1024 * 1024) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as file_handle:
        while True:
            chunk = file_handle.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def calculate_upload_bitrate_mbps(file_size_bytes: int, elapsed_seconds: float) -> float:
    size_bytes = max(int(file_size_bytes or 0), 0)
    elapsed = max(float(elapsed_seconds or 0.0), 0.000001)
    bitrate_mbps = (size_bytes * 8.0) / elapsed / 1_000_000.0
    return round(max(bitrate_mbps, 0.0), 4)


def calculate_minimum_upload_mbps(
    upload_count: int,
    bitrate_mbps: float,
    *,
    overhead_factor: float = 1.2,
    link_utilization_target: float = 0.7,
) -> float:
    uploads = max(int(upload_count or 0), 0)
    bitrate = max(float(bitrate_mbps or 0.0), 0.0)
    overhead = max(float(overhead_factor or 0.0), 0.01)
    utilization = min(max(float(link_utilization_target or 0.0), 0.01), 1.0)
    minimum = (uploads * bitrate * overhead) / utilization
    return round(max(minimum, 0.0), 4)


@dataclass
class UploadJob:
    record_id: int
    file_path: str
    queued_at: str
    metadata: dict[str, str] = field(default_factory=dict)


class IngestUploadGateway:
    def __init__(self) -> None:
        self.enabled = bool(settings.INGEST_GATEWAY_ENABLED)
        self.upload_url = str(settings.INGEST_GATEWAY_UPLOAD_URL or "").strip()
        self.auth_token = str(settings.INGEST_GATEWAY_AUTH_TOKEN or "").strip()
        self.timeout_sec = max(float(settings.INGEST_GATEWAY_TIMEOUT_SEC), 1.0)
        self.max_retries = max(int(settings.INGEST_GATEWAY_MAX_RETRIES), 0)
        self.retry_backoff_sec = max(float(settings.INGEST_GATEWAY_RETRY_BACKOFF_SEC), 0.1)
        self.max_workers = max(int(settings.INGEST_GATEWAY_WORKERS), 1)
        self.history_file = Path(settings.INGEST_GATEWAY_HISTORY_FILE)

        self.overhead_factor = max(float(settings.INGEST_GATEWAY_OVERHEAD_FACTOR), 0.01)
        self.link_utilization_target = min(
            max(float(settings.INGEST_GATEWAY_LINK_UTILIZATION_TARGET), 0.01),
            1.0,
        )
        self.configured_resolution = (
            str(settings.INGEST_GATEWAY_VIDEO_RESOLUTION or "").strip() or "1080p"
        )
        self.configured_codec = str(settings.INGEST_GATEWAY_VIDEO_CODEC or "").strip() or "h264"
        self.configured_target_bitrate_mbps = max(
            float(settings.INGEST_GATEWAY_VIDEO_TARGET_BITRATE_MBPS),
            0.1,
        )

        self._queue: asyncio.Queue[UploadJob] = asyncio.Queue()
        self._queued_record_ids: set[int] = set()
        self._inflight_record_ids: set[int] = set()
        self._workers_tasks: list[asyncio.Task] = []
        self._stop_event = asyncio.Event()
        self._state_lock = asyncio.Lock()

        self._successful_bitrates: deque[float] = deque(maxlen=200)
        self._last_success_bitrate_mbps: Optional[float] = None
        self._recent_uploads: deque[dict[str, Any]] = deque(maxlen=50)
        self._success_count = 0
        self._failure_count = 0

    async def start(self) -> None:
        if not self.enabled or not self.upload_url:
            return
        if self._workers_tasks and any(not task.done() for task in self._workers_tasks):
            return

        self._stop_event.clear()
        self._workers_tasks = [
            asyncio.create_task(self._worker_loop(worker_id=index + 1))
            for index in range(self.max_workers)
        ]

    async def stop(self) -> None:
        if not self._workers_tasks:
            return

        self._stop_event.set()
        for task in self._workers_tasks:
            task.cancel()
        await asyncio.gather(*self._workers_tasks, return_exceptions=True)
        self._workers_tasks = []

        async with self._state_lock:
            self._queued_record_ids.clear()
            self._inflight_record_ids.clear()

        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except Exception:
                break

    async def enqueue_upload(
        self,
        *,
        record_id: int,
        file_path: str,
        metadata: Optional[dict[str, str]] = None,
    ) -> bool:
        if not self.enabled or not self.upload_url:
            return False

        normalized_path = os.path.normpath(file_path or "")
        if not normalized_path or not os.path.exists(normalized_path):
            return False

        async with self._state_lock:
            if record_id in self._queued_record_ids or record_id in self._inflight_record_ids:
                return False
            self._queued_record_ids.add(record_id)

        await self._queue.put(
            UploadJob(
                record_id=record_id,
                file_path=normalized_path,
                queued_at=now_iso(),
                metadata=dict(metadata or {}),
            )
        )
        return True

    async def _worker_loop(self, *, worker_id: int) -> None:
        while not self._stop_event.is_set():
            try:
                job = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                return

            async with self._state_lock:
                self._queued_record_ids.discard(job.record_id)
                self._inflight_record_ids.add(job.record_id)

            try:
                await self._process_job(job, worker_id=worker_id)
            finally:
                async with self._state_lock:
                    self._inflight_record_ids.discard(job.record_id)
                self._queue.task_done()

    async def _process_job(self, job: UploadJob, *, worker_id: int = 0) -> None:
        if not os.path.exists(job.file_path):
            self._failure_count += 1
            self._record_upload_attempt(
                {
                    "timestamp": now_iso(),
                    "record_id": job.record_id,
                    "worker_id": worker_id,
                    "attempt": 1,
                    "success": False,
                    "final": True,
                    "status_code": None,
                    "error": "file_not_found",
                    "elapsed_sec": 0.0,
                    "bitrate_mbps": 0.0,
                    "file_size_bytes": 0,
                    "checksum_sha256": "",
                    "file_path": job.file_path,
                }
            )
            return

        file_size_bytes = os.path.getsize(job.file_path)
        checksum_sha256 = file_sha256(job.file_path)
        max_attempts = self.max_retries + 1

        for attempt in range(1, max_attempts + 1):
            started_at = time.monotonic()
            status_code: Optional[int] = None
            error_message: Optional[str] = None
            success = False

            try:
                status_code = await self._upload_once(
                    job=job,
                    file_size_bytes=file_size_bytes,
                    checksum_sha256=checksum_sha256,
                )
                success = 200 <= int(status_code) < 300
                if not success:
                    error_message = f"http_{status_code}"
            except Exception as exc:
                error_message = str(exc).strip() or exc.__class__.__name__

            elapsed_sec = max(time.monotonic() - started_at, 0.000001)
            bitrate_mbps = calculate_upload_bitrate_mbps(file_size_bytes, elapsed_sec)
            is_final = success or attempt >= max_attempts
            self._record_upload_attempt(
                {
                    "timestamp": now_iso(),
                    "record_id": job.record_id,
                    "worker_id": worker_id,
                    "attempt": attempt,
                    "success": success,
                    "final": is_final,
                    "status_code": status_code,
                    "error": error_message,
                    "elapsed_sec": round(elapsed_sec, 4),
                    "bitrate_mbps": bitrate_mbps,
                    "file_size_bytes": file_size_bytes,
                    "checksum_sha256": checksum_sha256,
                    "file_path": job.file_path,
                }
            )

            if success:
                self._success_count += 1
                self._last_success_bitrate_mbps = bitrate_mbps
                self._successful_bitrates.append(bitrate_mbps)
                return

            if attempt < max_attempts:
                delay = self.retry_backoff_sec * (2 ** (attempt - 1))
                await asyncio.sleep(delay)

        self._failure_count += 1

    async def _upload_once(
        self,
        *,
        job: UploadJob,
        file_size_bytes: int,
        checksum_sha256: str,
    ) -> int:
        headers = {
            "x-record-id": str(job.record_id),
            "x-checksum-sha256": checksum_sha256,
            "x-checksum-algo": "sha256",
            "x-video-resolution": self.configured_resolution,
            "x-video-codec": self.configured_codec,
            "x-configured-bitrate-mbps": f"{self.configured_target_bitrate_mbps:.4f}",
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        payload = {
            "record_id": str(job.record_id),
            "checksum_sha256": checksum_sha256,
            "checksum_algo": "sha256",
            "file_size_bytes": str(file_size_bytes),
            "video_resolution": self.configured_resolution,
            "video_codec": self.configured_codec,
            "configured_bitrate_mbps": f"{self.configured_target_bitrate_mbps:.4f}",
        }
        for key, value in (job.metadata or {}).items():
            payload[str(key)] = str(value)

        timeout = httpx.Timeout(self.timeout_sec)
        file_name = Path(job.file_path).name
        media_type = output_media_type(job.file_path)

        with open(job.file_path, "rb") as file_handle:
            files = {"file": (file_name, file_handle, media_type)}
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    self.upload_url,
                    data=payload,
                    files=files,
                    headers=headers,
                )

        if 200 <= response.status_code < 300:
            remote_checksum = self._extract_response_checksum(response)
            if remote_checksum and remote_checksum.lower() != checksum_sha256.lower():
                raise RuntimeError("checksum_mismatch")

        return int(response.status_code)

    def _extract_response_checksum(self, response: httpx.Response) -> Optional[str]:
        header_value = str(response.headers.get("x-checksum-sha256") or "").strip()
        if header_value:
            return header_value

        content_type = str(response.headers.get("content-type") or "").lower()
        if "application/json" not in content_type:
            return None

        try:
            payload = response.json()
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        value = payload.get("checksum_sha256")
        if value is None:
            return None
        text_value = str(value).strip()
        return text_value or None

    def _record_upload_attempt(self, payload: dict[str, Any]) -> None:
        self._recent_uploads.append(payload)
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        with self.history_file.open("a", encoding="utf-8") as file_handle:
            file_handle.write(json.dumps(payload, ensure_ascii=True) + "\n")

    def _average_success_bitrate_mbps(self) -> Optional[float]:
        if not self._successful_bitrates:
            return None
        average = sum(self._successful_bitrates) / len(self._successful_bitrates)
        return round(max(average, 0.0), 4)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.enabled and self.upload_url),
            "upload_url": self.upload_url,
            "queue_size": self._queue.qsize(),
            "in_flight": len(self._inflight_record_ids),
            "workers": self.max_workers,
            "retry_max_attempts": self.max_retries + 1,
            "retry_backoff_sec": round(self.retry_backoff_sec, 4),
            "checksum_algorithm": "sha256",
            "successful_uploads": self._success_count,
            "failed_uploads": self._failure_count,
            "measured_bitrate_last_mbps": self._last_success_bitrate_mbps,
            "measured_bitrate_avg_mbps": self._average_success_bitrate_mbps(),
            "video_profile": {
                "resolution": self.configured_resolution,
                "codec": self.configured_codec,
                "configured_bitrate_mbps": round(self.configured_target_bitrate_mbps, 4),
            },
            "recent_uploads": list(self._recent_uploads),
        }

    def bandwidth_recommendation(self, *, upload_count: int) -> dict[str, Any]:
        desired_uploads = max(int(upload_count or 0), 1)
        measured_bitrate = self._average_success_bitrate_mbps()
        if measured_bitrate is None:
            base_bitrate = round(self.configured_target_bitrate_mbps, 4)
            bitrate_source = "configured"
        else:
            base_bitrate = round(measured_bitrate, 4)
            bitrate_source = "measured"

        minimum_upload_mbps = calculate_minimum_upload_mbps(
            desired_uploads,
            base_bitrate,
            overhead_factor=self.overhead_factor,
            link_utilization_target=self.link_utilization_target,
        )
        return {
            "upload_count": desired_uploads,
            "bitrate_mbps": base_bitrate,
            "bitrate_source": bitrate_source,
            "overhead_factor": round(self.overhead_factor, 4),
            "link_utilization_target": round(self.link_utilization_target, 4),
            "minimum_upload_mbps": minimum_upload_mbps,
            "video_profile": {
                "resolution": self.configured_resolution,
                "codec": self.configured_codec,
                "configured_bitrate_mbps": round(self.configured_target_bitrate_mbps, 4),
            },
        }


ingest_upload_gateway = IngestUploadGateway()
