import pytest

from app.services.event_bus import InMemoryEventBus
from app.services.realtime_hub import RealtimeClient, RealtimeHub


@pytest.mark.asyncio
async def test_in_memory_event_bus_dispatches_to_handler() -> None:
    bus = InMemoryEventBus()
    captured: dict[str, object] = {}

    async def handler(payload: dict[str, object]) -> None:
        captured.update(payload)

    bus.set_handler(handler)
    await bus.publish({"type": "device_status", "device_id": 10, "status": "Online"})

    assert captured["type"] == "device_status"
    assert captured["device_id"] == 10


@pytest.mark.asyncio
async def test_realtime_hub_dispatch_event_respects_internal_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hub = RealtimeHub()
    captured: dict[str, object] = {}

    async def fake_broadcast(  # type: ignore[no-untyped-def]
        payload,
        *,
        target_device_id=None,
        target_user_ids=None,
        managers_only=False,
    ):
        captured["payload"] = payload
        captured["target_device_id"] = target_device_id
        captured["target_user_ids"] = target_user_ids
        captured["managers_only"] = managers_only

    monkeypatch.setattr(hub, "_broadcast", fake_broadcast)

    await hub.dispatch_event(
        {
            "type": "record_status",
            "record_id": 55,
            "_target_device_id": 7,
            "_target_user_ids": [1, 2, 2],
            "_managers_only": True,
        }
    )

    assert captured["payload"] == {"type": "record_status", "record_id": 55}
    assert captured["target_device_id"] == 7
    assert captured["target_user_ids"] == {1, 2}
    assert captured["managers_only"] is True


@pytest.mark.asyncio
async def test_realtime_hub_user_targeting_precedes_stale_device_scope() -> None:
    class DummyWebSocket:
        def __init__(self) -> None:
            self.payloads: list[dict[str, object]] = []

        async def send_json(self, payload: dict[str, object]) -> None:
            self.payloads.append(payload)

    hub = RealtimeHub()
    ws_target = DummyWebSocket()
    ws_other = DummyWebSocket()

    hub._clients[1] = RealtimeClient(  # type: ignore[attr-defined]
        client_id=1,
        websocket=ws_target,  # type: ignore[arg-type]
        user_id=10,
        is_superuser=False,
        allowed_device_ids=set(),
        wants_manager_metrics=False,
    )
    hub._clients[2] = RealtimeClient(  # type: ignore[attr-defined]
        client_id=2,
        websocket=ws_other,  # type: ignore[arg-type]
        user_id=20,
        is_superuser=False,
        allowed_device_ids={99},
        wants_manager_metrics=False,
    )

    await hub._broadcast(  # type: ignore[attr-defined]
        {"type": "device_status", "device_id": 99},
        target_device_id=99,
        target_user_ids={10},
        managers_only=False,
    )

    assert len(ws_target.payloads) == 1
    assert ws_target.payloads[0]["type"] == "device_status"
    assert ws_target.payloads[0]["device_id"] == 99
    assert ws_other.payloads == []
