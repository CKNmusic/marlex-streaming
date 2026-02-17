import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Set

from fastapi import WebSocket

META_TARGET_DEVICE_ID = "_target_device_id"
META_TARGET_USER_IDS = "_target_user_ids"
META_MANAGERS_ONLY = "_managers_only"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class RealtimeClient:
    client_id: int
    websocket: WebSocket
    user_id: int
    is_superuser: bool
    allowed_device_ids: Set[int] = field(default_factory=set)
    wants_manager_metrics: bool = False


class RealtimeHub:
    def __init__(self) -> None:
        self._clients: dict[int, RealtimeClient] = {}
        self._next_client_id = 1
        self._lock = asyncio.Lock()

    async def register(
        self,
        *,
        websocket: WebSocket,
        user_id: int,
        is_superuser: bool,
        allowed_device_ids: Set[int],
        wants_manager_metrics: bool,
    ) -> int:
        await websocket.accept()
        async with self._lock:
            client_id = self._next_client_id
            self._next_client_id += 1
            self._clients[client_id] = RealtimeClient(
                client_id=client_id,
                websocket=websocket,
                user_id=user_id,
                is_superuser=is_superuser,
                allowed_device_ids=allowed_device_ids,
                wants_manager_metrics=wants_manager_metrics,
            )
            return client_id

    async def unregister(self, client_id: int) -> None:
        async with self._lock:
            self._clients.pop(client_id, None)

    async def manager_subscribers(self) -> int:
        async with self._lock:
            return sum(1 for client in self._clients.values() if client.is_superuser and client.wants_manager_metrics)

    async def online_users_count(self) -> int:
        async with self._lock:
            return len({client.user_id for client in self._clients.values()})

    async def any_superuser_online(self) -> bool:
        async with self._lock:
            return any(client.is_superuser for client in self._clients.values())

    async def is_user_online(self, user_id: int) -> bool:
        async with self._lock:
            return any(client.user_id == user_id for client in self._clients.values())

    async def any_user_online(self, user_ids: Set[int]) -> bool:
        if not user_ids:
            return False
        async with self._lock:
            return any(client.user_id in user_ids for client in self._clients.values())

    async def _snapshot_clients(self) -> list[RealtimeClient]:
        async with self._lock:
            return list(self._clients.values())

    async def _broadcast(
        self,
        payload: dict[str, Any],
        *,
        target_device_id: Optional[int] = None,
        target_user_ids: Optional[Set[int]] = None,
        managers_only: bool = False,
    ) -> None:
        stale_clients: list[int] = []
        clients = await self._snapshot_clients()
        for client in clients:
            if managers_only and not client.is_superuser:
                continue

            # Explicit user targeting must take precedence over cached allowed_device_ids.
            # This avoids stale WS scopes after a fresh bind in the same login session.
            if target_user_ids and not client.is_superuser:
                if client.user_id not in target_user_ids:
                    continue
            elif target_device_id is not None and not client.is_superuser:
                # Manager can see all devices.
                if target_device_id not in client.allowed_device_ids:
                    continue

            try:
                await client.websocket.send_json(payload)
            except Exception:
                stale_clients.append(client.client_id)

        if stale_clients:
            async with self._lock:
                for stale_id in stale_clients:
                    self._clients.pop(stale_id, None)

    @staticmethod
    def _parse_int(value: Any) -> Optional[int]:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _parse_user_ids(value: Any) -> Optional[Set[int]]:
        if not isinstance(value, list):
            return None
        parsed_ids: Set[int] = set()
        for item in value:
            parsed = RealtimeHub._parse_int(item)
            if parsed is not None:
                parsed_ids.add(parsed)
        return parsed_ids or None

    @staticmethod
    def _without_metadata(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in payload.items()
            if not str(key).startswith("_")
        }

    async def dispatch_event(self, payload: dict[str, Any]) -> None:
        target_device_id = self._parse_int(payload.get(META_TARGET_DEVICE_ID))
        target_user_ids = self._parse_user_ids(payload.get(META_TARGET_USER_IDS))
        managers_only = bool(payload.get(META_MANAGERS_ONLY))
        await self._broadcast(
            self._without_metadata(payload),
            target_device_id=target_device_id,
            target_user_ids=target_user_ids,
            managers_only=managers_only,
        )

    async def publish_device_status(
        self,
        *,
        device_id: int,
        status: str,
        online: bool,
        stream_url: Optional[str],
        checked_at: Optional[str] = None,
        detail: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        target_user_ids: Optional[Set[int]] = None,
    ) -> None:
        payload = {
            "type": "device_status",
            "timestamp": now_iso(),
            "device_id": device_id,
            "status": status,
            "online": online,
            "stream_url": stream_url,
            "checked_at": checked_at or now_iso(),
            "detail": detail,
            "metadata": metadata or None,
            META_TARGET_DEVICE_ID: device_id,
            META_TARGET_USER_IDS: sorted(target_user_ids) if target_user_ids else None,
        }
        await self.dispatch_event(payload)

    async def publish_record_status(
        self,
        *,
        record_id: int,
        device_id: int,
        owner_id: int,
        status: str,
        final_status: Optional[str] = None,
        stop_reason: Optional[str] = None,
        end_time: Optional[str] = None,
        detail: Optional[str] = None,
        target_user_ids: Optional[Set[int]] = None,
    ) -> None:
        payload = {
            "type": "record_status",
            "timestamp": now_iso(),
            "record_id": record_id,
            "device_id": device_id,
            "owner_id": owner_id,
            "status": status,
            "final_status": final_status,
            "stop_reason": stop_reason,
            "end_time": end_time,
            "detail": detail,
            META_TARGET_DEVICE_ID: device_id,
            META_TARGET_USER_IDS: sorted(target_user_ids) if target_user_ids else None,
        }
        await self.dispatch_event(payload)

    async def publish_manager_metrics(self, payload: dict[str, Any]) -> None:
        event_payload = {
            "type": "manager_metrics",
            "timestamp": now_iso(),
            "metrics": payload,
            META_MANAGERS_ONLY: True,
        }
        await self.dispatch_event(event_payload)


realtime_hub = RealtimeHub()
