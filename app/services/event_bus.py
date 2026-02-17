import asyncio
import json
import logging
import uuid
from typing import Any, Awaitable, Callable, Optional

from app.core.config import settings

RealtimeEventHandler = Callable[[dict[str, Any]], Awaitable[None]]
logger = logging.getLogger(__name__)


class BaseEventBus:
    def __init__(self) -> None:
        self._handler: Optional[RealtimeEventHandler] = None

    def set_handler(self, handler: RealtimeEventHandler) -> None:
        self._handler = handler

    async def _dispatch_local(self, payload: dict[str, Any]) -> None:
        if not self._handler:
            return
        try:
            await self._handler(payload)
        except Exception:
            logger.exception("Failed to dispatch realtime event to local handler.")

    async def start(self) -> None:
        return

    async def stop(self) -> None:
        return

    async def publish(self, payload: dict[str, Any]) -> None:
        raise NotImplementedError


class InMemoryEventBus(BaseEventBus):
    async def publish(self, payload: dict[str, Any]) -> None:
        await self._dispatch_local(payload)


class RedisEventBus(BaseEventBus):
    def __init__(self, redis_url: str, channel: str) -> None:
        super().__init__()
        self._redis_url = redis_url
        self._channel = channel
        self._instance_id = uuid.uuid4().hex
        self._publisher = None
        self._subscriber = None
        self._pubsub = None
        self._consume_task: Optional[asyncio.Task] = None

    @staticmethod
    async def _close_resource(resource: Any) -> None:
        close_async = getattr(resource, "aclose", None)
        if callable(close_async):
            await close_async()
            return

        close_method = getattr(resource, "close", None)
        if callable(close_method):
            result = close_method()
            if asyncio.iscoroutine(result):
                await result

    async def start(self) -> None:
        if self._consume_task and not self._consume_task.done():
            return
        try:
            from redis import asyncio as redis_async
        except Exception as exc:
            raise RuntimeError("Redis dependency is not available.") from exc

        self._publisher = redis_async.from_url(self._redis_url, decode_responses=True)
        self._subscriber = redis_async.from_url(self._redis_url, decode_responses=True)
        self._pubsub = self._subscriber.pubsub(ignore_subscribe_messages=True)
        await self._pubsub.subscribe(self._channel)
        self._consume_task = asyncio.create_task(self._consume_loop())

    async def stop(self) -> None:
        if self._consume_task:
            self._consume_task.cancel()
            try:
                await self._consume_task
            except asyncio.CancelledError:
                pass
            self._consume_task = None

        if self._pubsub is not None:
            try:
                await self._pubsub.unsubscribe(self._channel)
                await self._close_resource(self._pubsub)
            except Exception:
                logger.exception("Failed to close Redis pubsub cleanly.")
            self._pubsub = None

        if self._subscriber is not None:
            try:
                await self._close_resource(self._subscriber)
            except Exception:
                logger.exception("Failed to close Redis subscriber.")
            self._subscriber = None

        if self._publisher is not None:
            try:
                await self._close_resource(self._publisher)
            except Exception:
                logger.exception("Failed to close Redis publisher.")
            self._publisher = None

    async def publish(self, payload: dict[str, Any]) -> None:
        await self._dispatch_local(payload)
        if self._publisher is None:
            return

        envelope = {
            "origin": self._instance_id,
            "payload": payload,
        }
        serialized = json.dumps(envelope, ensure_ascii=True, separators=(",", ":"))
        try:
            await self._publisher.publish(self._channel, serialized)
        except Exception:
            logger.exception("Failed to publish realtime event to Redis channel.")

    async def _consume_loop(self) -> None:
        if self._pubsub is None:
            return

        while True:
            try:
                message = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Redis pub/sub consumer failed; retrying.")
                await asyncio.sleep(1.0)
                continue

            if not message:
                await asyncio.sleep(0.05)
                continue

            raw_data = message.get("data")
            if raw_data is None:
                continue

            if isinstance(raw_data, bytes):
                raw_text = raw_data.decode("utf-8", errors="ignore")
            else:
                raw_text = str(raw_data)

            try:
                envelope = json.loads(raw_text)
            except Exception:
                continue

            if not isinstance(envelope, dict):
                continue

            if str(envelope.get("origin") or "") == self._instance_id:
                continue

            payload = envelope.get("payload")
            if isinstance(payload, dict):
                await self._dispatch_local(payload)


class RealtimeEventBus(BaseEventBus):
    def __init__(self, mode: str, redis_url: str, channel: str) -> None:
        super().__init__()
        self._mode = mode.strip().lower()
        self._redis_url = redis_url
        self._channel = channel
        self._delegate: BaseEventBus = InMemoryEventBus()

    def set_handler(self, handler: RealtimeEventHandler) -> None:
        super().set_handler(handler)
        self._delegate.set_handler(handler)

    async def start(self) -> None:
        if self._mode != "redis":
            self._delegate = InMemoryEventBus()
            if self._handler:
                self._delegate.set_handler(self._handler)
            await self._delegate.start()
            return

        redis_bus = RedisEventBus(self._redis_url, self._channel)
        if self._handler:
            redis_bus.set_handler(self._handler)
        try:
            await redis_bus.start()
            self._delegate = redis_bus
            logger.info("Realtime event bus started in Redis mode.")
        except Exception:
            logger.exception(
                "Realtime event bus failed to start in Redis mode. Falling back to memory mode."
            )
            fallback_bus = InMemoryEventBus()
            if self._handler:
                fallback_bus.set_handler(self._handler)
            await fallback_bus.start()
            self._delegate = fallback_bus

    async def stop(self) -> None:
        await self._delegate.stop()

    async def publish(self, payload: dict[str, Any]) -> None:
        await self._delegate.publish(payload)


realtime_event_bus = RealtimeEventBus(
    mode=settings.REALTIME_EVENT_BUS,
    redis_url=settings.REDIS_URL,
    channel=settings.REDIS_EVENTS_CHANNEL,
)
