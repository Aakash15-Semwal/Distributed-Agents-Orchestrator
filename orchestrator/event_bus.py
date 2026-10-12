from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable


class EventType(Enum):
    TASK_SUBMITTED          = auto()
    TASK_QUEUED             = auto()
    TASK_DISPATCHED         = auto()
    TASK_COMPLETED          = auto()
    TASK_FAILED             = auto()
    TASK_TIMEOUT            = auto()
    TASK_RETRYING           = auto()
    TASK_PERMANENTLY_FAILED = auto()
    AGENT_STARTED           = auto()
    RESOURCE_ACQUIRED       = auto()
    RESOURCE_RELEASED       = auto()
    ORCHESTRATOR_STARTED    = auto()
    ORCHESTRATOR_STOPPED    = auto()


@dataclass
class Event:
    type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def __repr__(self) -> str:
        return f"Event({self.type.name}, data={self.data})"


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[Callable[[Event], None]]] = {
            et: [] for et in EventType
        }
        self._queue: queue.Queue[Event | None] = queue.Queue()
        self._dispatch_thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._dispatch_thread = threading.Thread(
                target=self._dispatch_loop,
                name="EventBus-Dispatcher",
                daemon=True,
            )
            self._dispatch_thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False

        self._queue.put(None)
        if self._dispatch_thread:
            self._dispatch_thread.join(timeout=timeout)

    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        with self._lock:
            self._subscribers[event_type].append(handler)

    def publish(self, event: Event) -> None:
        self._queue.put(event)

    def _dispatch_loop(self) -> None:
        while True:
            try:
                event = self._queue.get(timeout=0.1)
            except queue.Empty:
                if not self._running:
                    break
                continue

            if event is None:
                break

            self._dispatch(event)

    def _dispatch(self, event: Event) -> None:
        with self._lock:
            handlers = list(self._subscribers.get(event.type, []))

        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:  # noqa: BLE001
                print(f"[EventBus] Handler {handler!r} raised: {exc}")
