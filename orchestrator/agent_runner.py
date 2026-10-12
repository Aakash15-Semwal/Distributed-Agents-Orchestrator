from __future__ import annotations

import threading
import time
import traceback
from typing import Callable, TYPE_CHECKING

from .event_bus import Event, EventBus, EventType
from .task import TaskAttempt

if TYPE_CHECKING:
    from .agent_registry import AgentFn
    from .resource_manager import ResourceManager


class AgentThread(threading.Thread):
    def __init__(
        self,
        attempt: TaskAttempt,
        agent_fn: AgentFn,
        resource_manager: ResourceManager,
        event_bus: EventBus,
        thread_semaphore: threading.Semaphore,
        on_finished: Callable[["AgentThread"], None],
    ) -> None:
        super().__init__(
            name=f"Agent-{attempt.task_id}-attempt{attempt.attempt_number}",
            daemon=True,
        )
        self._attempt = attempt
        self._agent_fn = agent_fn
        self._rm = resource_manager
        self._bus = event_bus
        self._semaphore = thread_semaphore
        self._on_finished = on_finished

        self._watchdog: threading.Timer | None = None
        self._stop_event = threading.Event()
        self._timed_out = False

        self._start_time: float = 0.0
        self._end_time: float = 0.0

    def run(self) -> None:
        task = self._attempt.task
        self._start_time = time.monotonic()

        self._bus.publish(Event(
            EventType.AGENT_STARTED,
            data={
                "task_id": task.task_id,
                "task_name": task.name,
                "agent_type": task.agent_type,
                "attempt": self._attempt.attempt_number,
                "thread_name": self.name,
            },
        ))

        self._start_watchdog(task.timeout_seconds)

        result: dict | None = None
        error: Exception | None = None

        try:
            result = self._agent_fn(task.task_id, task.payload)
        except Exception as exc:  # noqa: BLE001
            error = exc
        finally:
            self._cancel_watchdog()
            self._end_time = time.monotonic()
            duration = self._end_time - self._start_time

            if self._timed_out:
                self._bus.publish(Event(
                    EventType.TASK_TIMEOUT,
                    data={
                        "task_id": task.task_id,
                        "task_name": task.name,
                        "attempt": self._attempt.attempt_number,
                        "timeout_seconds": task.timeout_seconds,
                        "duration_s": round(duration, 3),
                    },
                ))
            elif error is not None:
                self._bus.publish(Event(
                    EventType.TASK_FAILED,
                    data={
                        "task_id": task.task_id,
                        "task_name": task.name,
                        "attempt": self._attempt.attempt_number,
                        "error": repr(error),
                        "traceback": traceback.format_exc(),
                        "duration_s": round(duration, 3),
                    },
                ))
            else:
                self._bus.publish(Event(
                    EventType.TASK_COMPLETED,
                    data={
                        "task_id": task.task_id,
                        "task_name": task.name,
                        "attempt": self._attempt.attempt_number,
                        "agent_type": task.agent_type,
                        "duration_s": round(duration, 3),
                        "result": result,
                    },
                ))

            self._rm.release(task.resource_requirements, task.task_id)
            self._semaphore.release()

            try:
                self._on_finished(self)
            except Exception as exc:  # noqa: BLE001
                print(f"[AgentThread] on_finished error: {exc}")

    def _start_watchdog(self, timeout_seconds: float) -> None:
        self._watchdog = threading.Timer(
            interval=timeout_seconds,
            function=self._on_timeout,
        )
        self._watchdog.daemon = True
        self._watchdog.name = f"Watchdog-{self._attempt.task_id}"
        self._watchdog.start()

    def _cancel_watchdog(self) -> None:
        if self._watchdog:
            self._watchdog.cancel()
            self._watchdog = None

    def _on_timeout(self) -> None:
        self._timed_out = True
        self._stop_event.set()

    @property
    def attempt(self) -> TaskAttempt:
        return self._attempt

    @property
    def stop_event(self) -> threading.Event:
        return self._stop_event

    @property
    def elapsed_seconds(self) -> float:
        if self._start_time == 0.0:
            return 0.0
        end = self._end_time if self._end_time else time.monotonic()
        return end - self._start_time
