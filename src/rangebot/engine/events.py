"""Bounded in-process publisher for sanitized localhost frontend events."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from uuid import uuid4

from rangebot.domain.events import (
    EngineEvent,
    EngineEventCategory,
    EngineEventStreamStatus,
)


@dataclass(frozen=True, slots=True)
class _Subscriber:
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[EngineEvent]


class EngineEventPublisher:
    """Publish non-blocking events without letting slow UI clients affect the engine."""

    def __init__(self, *, queue_size: int = 100) -> None:
        if queue_size < 1:
            raise ValueError("Event subscriber queue size must be positive.")
        self._queue_size = queue_size
        self._lock = RLock()
        self._sequence = 0
        self._subscribers: dict[str, _Subscriber] = {}

    def status(self) -> EngineEventStreamStatus:
        with self._lock:
            return EngineEventStreamStatus(
                sequence=self._sequence,
                subscriber_count=len(self._subscribers),
            )

    def publish(
        self,
        *,
        category: EngineEventCategory,
        action: str,
        resource: str,
    ) -> EngineEvent:
        """Publish synchronously; queue delivery is scheduled on each subscriber loop."""
        with self._lock:
            self._sequence += 1
            event = EngineEvent(
                event_id=uuid4().hex,
                sequence=self._sequence,
                category=category,
                action=action,
                resource=resource,
                occurred_at=datetime.now(UTC),
            )
            subscribers = tuple(self._subscribers.values())

        for subscriber in subscribers:
            try:
                subscriber.loop.call_soon_threadsafe(
                    self._enqueue_latest,
                    subscriber.queue,
                    event,
                )
            except RuntimeError:
                # A closing browser/test loop is removed by the subscription finalizer.
                continue
        return event

    async def subscribe(self) -> AsyncIterator[EngineEvent]:
        """Yield events for one client, dropping oldest events if that client is slow."""
        subscriber_id = uuid4().hex
        subscriber = _Subscriber(
            loop=asyncio.get_running_loop(),
            queue=asyncio.Queue(maxsize=self._queue_size),
        )
        with self._lock:
            self._subscribers[subscriber_id] = subscriber
        try:
            while True:
                yield await subscriber.queue.get()
        finally:
            with self._lock:
                self._subscribers.pop(subscriber_id, None)

    @staticmethod
    def _enqueue_latest(queue: asyncio.Queue[EngineEvent], event: EngineEvent) -> None:
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            # Another scheduled delivery filled the queue; the next event will recover.
            pass
