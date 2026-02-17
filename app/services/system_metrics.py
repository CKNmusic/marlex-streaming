import asyncio
import base64
import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.core.config import settings
from app.services.realtime_events import emit_manager_metrics
from app.services.realtime_hub import realtime_hub
from app.services.recorder import recorder_service


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


class SystemMetricsCollector:
    def __init__(self) -> None:
        self.interval_sec = max(float(settings.METRICS_INTERVAL_SEC), 0.5)
        self.always_on = bool(settings.METRICS_ALWAYS_ON)
        self.history_file = Path(settings.METRICS_HISTORY_FILE)
        self.ingest_status_file = Path(settings.INGEST_STATUS_FILE)
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._manager_clients = 0
        self._lock = asyncio.Lock()
        self._last_cpu_total: Optional[int] = None
        self._last_cpu_idle: Optional[int] = None
        self._last_net_bytes: Optional[tuple[int, int]] = None
        self._last_net_ts: Optional[float] = None
        self._current: dict[str, Any] = {}
        self._app_users_online = 0

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if not self._task:
            return
        self._stop_event.set()
        try:
            await self._task
        except Exception:
            pass
        self._task = None

    async def set_manager_clients(self, count: int) -> None:
        async with self._lock:
            self._manager_clients = max(count, 0)

    async def _manager_clients_count(self) -> int:
        async with self._lock:
            return self._manager_clients

    def _cpu_percent(self) -> float:
        try:
            with open("/proc/stat", "r", encoding="utf-8") as file_handle:
                line = file_handle.readline().strip()
            if not line.startswith("cpu "):
                return 0.0
            values = [int(value) for value in line.split()[1:]]
            total = sum(values)
            idle = values[3] + (values[4] if len(values) > 4 else 0)
            if self._last_cpu_total is None or self._last_cpu_idle is None:
                self._last_cpu_total = total
                self._last_cpu_idle = idle
                return 0.0
            total_delta = total - self._last_cpu_total
            idle_delta = idle - self._last_cpu_idle
            self._last_cpu_total = total
            self._last_cpu_idle = idle
            if total_delta <= 0:
                return 0.0
            return max(0.0, min(100.0, (1.0 - (idle_delta / total_delta)) * 100.0))
        except Exception:
            return 0.0

    def _memory_percent(self) -> float:
        try:
            mem_total = 0
            mem_available = 0
            with open("/proc/meminfo", "r", encoding="utf-8") as file_handle:
                for line in file_handle:
                    if line.startswith("MemTotal:"):
                        mem_total = int(line.split()[1])
                    elif line.startswith("MemAvailable:"):
                        mem_available = int(line.split()[1])
            if mem_total <= 0:
                return 0.0
            used = mem_total - mem_available
            return max(0.0, min(100.0, (used / mem_total) * 100.0))
        except Exception:
            return 0.0

    def _network_bytes(self) -> tuple[int, int]:
        rx_total = 0
        tx_total = 0
        base_path = Path("/sys/class/net")
        try:
            for iface in base_path.iterdir():
                if iface.name == "lo":
                    continue
                rx_file = iface / "statistics" / "rx_bytes"
                tx_file = iface / "statistics" / "tx_bytes"
                if rx_file.exists():
                    rx_total += int(rx_file.read_text(encoding="utf-8").strip() or "0")
                if tx_file.exists():
                    tx_total += int(tx_file.read_text(encoding="utf-8").strip() or "0")
        except Exception:
            return 0, 0
        return rx_total, tx_total

    def _network_bps(self) -> tuple[int, int]:
        now_ts = time.monotonic()
        rx_bytes, tx_bytes = self._network_bytes()
        if self._last_net_bytes is None or self._last_net_ts is None:
            self._last_net_bytes = (rx_bytes, tx_bytes)
            self._last_net_ts = now_ts
            return 0, 0

        prev_rx, prev_tx = self._last_net_bytes
        elapsed = max(now_ts - self._last_net_ts, 0.001)
        self._last_net_bytes = (rx_bytes, tx_bytes)
        self._last_net_ts = now_ts
        rx_bps = int(max((rx_bytes - prev_rx) / elapsed, 0))
        tx_bps = int(max((tx_bytes - prev_tx) / elapsed, 0))
        return rx_bps, tx_bps

    def _ingest_api_online_counts(self) -> tuple[int, int]:
        if not settings.INGEST_API_ENABLED:
            return 0, 0

        endpoint = (
            f"{settings.INGEST_API_SCHEME}://"
            f"{settings.INGEST_API_HOST}:{settings.INGEST_API_PORT}/v3/paths/list"
        )
        credentials = f"{settings.INGEST_API_USER}:{settings.INGEST_API_PASS}"
        token = base64.b64encode(credentials.encode("utf-8")).decode("ascii")

        try:
            request = urllib.request.Request(endpoint)
            request.add_header("Authorization", f"Basic {token}")
            with urllib.request.urlopen(request, timeout=float(settings.INGEST_API_TIMEOUT_SEC)) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return 0, 0

        items = payload.get("items", [])
        publishers = 0
        for item in items:
            is_online = bool(item.get("online") or item.get("ready") or item.get("available"))
            if not is_online:
                continue
            publishers += 1

        # Path list does not provide a reliable "recording active" signal.
        # Keep recordings at 0 here and rely on recorder runtime/status file.
        return publishers, 0

    def _ingest_status_file_counts(self) -> tuple[int, int]:
        if not self.ingest_status_file.exists():
            return 0, 0
        try:
            payload = json.loads(self.ingest_status_file.read_text(encoding="utf-8"))
            manager = payload.get("manager") or {}
            status = str(manager.get("status") or "").strip().lower()
            updated_at_raw = str(manager.get("updated_at") or "").strip()

            # Ignore stale/offline snapshots; these values should represent live ingest only.
            if status != "online":
                return 0, 0
            if updated_at_raw:
                updated_at = datetime.fromisoformat(updated_at_raw)
                age_sec = (datetime.now() - updated_at).total_seconds()
                if age_sec > 30:
                    return 0, 0

            publishers = int(manager.get("publishers_online") or 0)
            recordings = int(manager.get("recordings_active") or 0)
            return max(publishers, 0), max(recordings, 0)
        except Exception:
            return 0, 0

    def _ingest_online_counts(self) -> tuple[int, int]:
        api_publishers, api_recordings = self._ingest_api_online_counts()
        file_publishers, file_recordings = self._ingest_status_file_counts()
        return (
            max(api_publishers, file_publishers),
            max(api_recordings, file_recordings),
        )

    def _record_local_metric(self, metric: dict[str, Any]) -> None:
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(metric, ensure_ascii=True)
        with self.history_file.open("a", encoding="utf-8") as file_handle:
            file_handle.write(line + "\n")

    def _sample(self) -> dict[str, Any]:
        publishers_online, ingest_recordings = self._ingest_online_counts()
        rx_bps, tx_bps = self._network_bps()
        metric = {
            "timestamp": now_iso(),
            "cpu_percent": round(self._cpu_percent(), 2),
            "memory_percent": round(self._memory_percent(), 2),
            "network": {
                "download_bps": rx_bps,
                "upload_bps": tx_bps,
            },
            "recordings_active": max(recorder_service.active_count(), ingest_recordings),
            "publishers_online": publishers_online,
            "manager_clients": self._manager_clients,
            "app_users_online": self._app_users_online,
        }
        self._current = metric
        return metric

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            manager_clients = await realtime_hub.manager_subscribers()
            self._app_users_online = await realtime_hub.online_users_count()
            await self.set_manager_clients(manager_clients)
            should_collect = self.always_on or manager_clients > 0
            if should_collect:
                metric = self._sample()
                self._record_local_metric(metric)
                await emit_manager_metrics(metric)
            await asyncio.sleep(self.interval_sec)

    def current(self) -> dict[str, Any]:
        if self._current:
            return self._current
        return self._sample()

    def history(self, limit: int = 120) -> list[dict[str, Any]]:
        if not self.history_file.exists():
            return []
        try:
            lines = self.history_file.read_text(encoding="utf-8").splitlines()
            items: list[dict[str, Any]] = []
            for line in lines[-max(limit, 1):]:
                line = line.strip()
                if not line:
                    continue
                items.append(json.loads(line))
            return items
        except Exception:
            return []


metrics_collector = SystemMetricsCollector()
