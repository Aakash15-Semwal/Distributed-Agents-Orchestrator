from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from .agent_runner import AgentThread
from .event_bus import Event, EventBus, EventType
from .task import TaskAttempt

if TYPE_CHECKING:
    from .agent_registry import AgentRegistry
    from .resource_manager import ResourceManager

MAX_CONCURRENT_AGENTS = 5
AGING_INTERVAL_SECONDS = 10.0


class Scheduler:
    def __init__(
        self,
        resource_manager: ResourceManager,
        agent_registry: AgentRegistry,
        event_bus: EventBus,
    ) -> None:
        self._rm = resource_manager
        self._registry = agent_registry
        self._bus = event_bus

        self._queue: list[TaskAttempt] = []
        self._queue_lock = threading.Lock()
        self._submission_order: dict[str, int] = {}
        self._counter = 0
        self._enqueue_times: dict[str, float] = {}

        self._tasks: dict[str, TaskAttempt] = {}
        self._tasks_lock = threading.Lock()

        self._thread_semaphore = threading.Semaphore(MAX_CONCURRENT_AGENTS)
        self._active_threads: dict[str, AgentThread] = {}
        self._threads_lock = threading.Lock()

        self._wake_lock = threading.Lock()
        self._wake_cond = threading.Condition(self._wake_lock)
        self._rm.register_release_callback(self._wake_up)

        self._pending_task_ids: set[str] = set()
        self._done_condition = threading.Condition()

        self._thread: threading.Thread | None = None
        self._running = False

        self._bus.subscribe(EventType.TASK_FAILED, self._on_task_failed_or_timeout)
        self._bus.subscribe(EventType.TASK_TIMEOUT, self._on_task_failed_or_timeout)

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(
            target=self._dispatch_loop,
            name="Scheduler",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._running = False
        self._wake_up()
        if self._thread:
            self._thread.join(timeout=timeout)

    def _wake_up(self) -> None:
        with self._wake_cond:
            self._wake_cond.notify_all()

    def submit(self, attempt: TaskAttempt) -> None:
        task_id = attempt.task_id

        with self._tasks_lock:
            self._tasks[task_id] = attempt

        with self._done_condition:
            self._pending_task_ids.add(task_id)

        self._enqueue(attempt)
        self._wake_up()

    def wait_until_done(self, timeout: float | None = None) -> bool:
        deadline = time.monotonic() + timeout if timeout else None
        with self._done_condition:
            while self._pending_task_ids:
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return False
                    self._done_condition.wait(timeout=remaining)
                else:
                    self._done_condition.wait()
        return True

    def _dispatch_loop(self) -> None:
        while self._running:
            self._try_dispatch_all()

            with self._wake_cond:
                if not self._running:
                    break
                self._wake_cond.wait(timeout=0.5)

    def _try_dispatch_all(self) -> None:
        while self._running:
            dispatched = self._try_dispatch_one()
            if not dispatched:
                break

    def _try_dispatch_one(self) -> bool:
        with self._queue_lock:
            if not self._queue:
                return False

            self._sort_queue_locked()

            target_idx = -1
            target_attempt: TaskAttempt | None = None

            for i, attempt in enumerate(self._queue):
                if not self._thread_semaphore.acquire(blocking=False):
                    return False

                if self._rm.acquire(attempt.task.resource_requirements, attempt.task_id):
                    target_idx = i
                    target_attempt = attempt
                    break
                else:
                    self._thread_semaphore.release()

            if target_idx == -1 or target_attempt is None:
                return False

            self._queue.pop(target_idx)

        self._dispatch(target_attempt)
        return True

    def _dispatch(self, attempt: TaskAttempt) -> None:
        agent_fn = self._registry.get(attempt.task.agent_type)

        thread = AgentThread(
            attempt=attempt,
            agent_fn=agent_fn,
            resource_manager=self._rm,
            event_bus=self._bus,
            thread_semaphore=self._thread_semaphore,
            on_finished=self._on_agent_finished,
        )

        with self._threads_lock:
            self._active_threads[attempt.task_id] = thread

        self._bus.publish(Event(
            EventType.TASK_DISPATCHED,
            data={
                "task_id": attempt.task_id,
                "task_name": attempt.task.name,
                "agent_type": attempt.task.agent_type,
                "attempt": attempt.attempt_number,
                "thread_name": thread.name,
                "priority": attempt.task.priority,
            },
        ))

        thread.start()

    def _on_agent_finished(self, thread: AgentThread) -> None:
        with self._threads_lock:
            self._active_threads.pop(thread.attempt.task_id, None)
        self._wake_up()

    def _on_task_failed_or_timeout(self, event: Event) -> None:
        task_id = event.data["task_id"]
        attempt_num = event.data["attempt"]

        with self._tasks_lock:
            current_attempt = self._tasks.get(task_id)
            if current_attempt is None:
                return

        next_attempt = current_attempt.next_attempt()

        if not next_attempt.has_retries_remaining:
            self._bus.publish(Event(
                EventType.TASK_PERMANENTLY_FAILED,
                data={
                    "task_id": task_id,
                    "task_name": current_attempt.task.name,
                    "total_attempts": attempt_num,
                    "reason": event.data.get("error") or "timeout",
                },
            ))
            self._mark_done(task_id)
            return

        with self._tasks_lock:
            self._tasks[task_id] = next_attempt

        self._bus.publish(Event(
            EventType.TASK_RETRYING,
            data={
                "task_id": task_id,
                "task_name": current_attempt.task.name,
                "attempt": next_attempt.attempt_number,
                "max_attempts": current_attempt.task.max_retries + 1,
            },
        ))

        self._enqueue(next_attempt)
        self._wake_up()

    def _enqueue(self, attempt: TaskAttempt) -> None:
        with self._queue_lock:
            self._counter += 1
            task_id = attempt.task_id
            self._submission_order[task_id] = self._counter
            if task_id not in self._enqueue_times:
                self._enqueue_times[task_id] = time.monotonic()
            self._queue.append(attempt)
            self._sort_queue_locked()

    def _sort_queue_locked(self) -> None:
        now = time.monotonic()

        def sort_key(attempt: TaskAttempt) -> tuple[int, int]:
            task_id = attempt.task_id
            enqueue_time = self._enqueue_times.get(task_id, now)
            wait_seconds = max(0.0, now - enqueue_time)
            bumps = int(wait_seconds // AGING_INTERVAL_SECONDS)
            effective_priority = min(attempt.task.priority + bumps, 10)
            order = self._submission_order.get(task_id, 0)
            return (-effective_priority, order)

        self._queue.sort(key=sort_key)

    def _mark_done(self, task_id: str) -> None:
        with self._tasks_lock:
            self._tasks.pop(task_id, None)

        with self._queue_lock:
            self._enqueue_times.pop(task_id, None)
            self._submission_order.pop(task_id, None)

        with self._done_condition:
            self._pending_task_ids.discard(task_id)
            if not self._pending_task_ids:
                self._done_condition.notify_all()

    def _on_task_completed(self, event: Event) -> None:
        self._mark_done(event.data["task_id"])

    def _on_permanently_failed(self, event: Event) -> None:
        self._mark_done(event.data["task_id"])

    def wire_completion_events(self) -> None:
        self._bus.subscribe(EventType.TASK_COMPLETED, self._on_task_completed)
        self._bus.subscribe(EventType.TASK_PERMANENTLY_FAILED, self._on_permanently_failed)

    def active_count(self) -> int:
        with self._threads_lock:
            return len(self._active_threads)

    def queue_size(self) -> int:
        with self._queue_lock:
            return len(self._queue)
