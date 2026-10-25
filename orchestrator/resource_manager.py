from __future__ import annotations

import threading
import time
from typing import Callable

from .event_bus import Event, EventBus, EventType
from .exceptions import InsufficientResourcesError, ResourceNotDeclaredError
from .task import ResourcePool, ResourceRequirements


class ResourceManager:
    def __init__(self, pool: ResourcePool, event_bus: EventBus) -> None:
        self._pool = pool
        self._bus = event_bus
        self._lock = threading.RLock()

        self._cpu_available: float = pool.total_cpu_cores
        self._gpu_available: float = pool.total_gpu_memory_gb
        self._exclusive_holders: dict[str, str | None] = {
            name: None for name in pool.exclusive_resources
        }
        self._api_tokens: dict[str, int] = dict(pool.api_rate_limits)
        self._release_callbacks: list[Callable[[], None]] = []

        self._replenish_thread: threading.Thread | None = None
        self._replenish_running = False

    def start(self) -> None:
        if self._pool.api_rate_limits:
            self._replenish_running = True
            self._replenish_thread = threading.Thread(
                target=self._replenish_loop,
                name="ResourceManager-Replenisher",
                daemon=True,
            )
            self._replenish_thread.start()

    def stop(self) -> None:
        self._replenish_running = False
        if self._replenish_thread:
            self._replenish_thread.join(timeout=2.0)

    def register_release_callback(self, callback: Callable[[], None]) -> None:
        with self._lock:
            self._release_callbacks.append(callback)

    def can_satisfy(self, req: ResourceRequirements) -> bool:
        with self._lock:
            return self._check(req)

    def acquire(self, req: ResourceRequirements, task_id: str) -> bool:
        with self._lock:
            if not self._check(req):
                return False

            self._cpu_available -= req.cpu_cores
            self._gpu_available -= req.gpu_memory_gb

            for name in req.exclusive_resources:
                self._exclusive_holders[name] = task_id

            for api, tokens in req.api_rate_tokens.items():
                self._api_tokens[api] -= tokens

        self._bus.publish(Event(
            EventType.RESOURCE_ACQUIRED,
            data={"task_id": task_id, "requirements": repr(req)},
        ))
        return True

    def release(self, req: ResourceRequirements, task_id: str) -> None:
        with self._lock:
            self._cpu_available += req.cpu_cores
            self._gpu_available += req.gpu_memory_gb

            for name in req.exclusive_resources:
                self._exclusive_holders[name] = None

            callbacks = list(self._release_callbacks)

        self._bus.publish(Event(
            EventType.RESOURCE_RELEASED,
            data={"task_id": task_id, "requirements": repr(req)},
        ))

        for cb in callbacks:
            try:
                cb()
            except Exception as exc:  # noqa: BLE001
                print(f"[ResourceManager] Release callback error: {exc}")

    def validate_requirements(self, req: ResourceRequirements, task_id: str) -> None:
        if req.cpu_cores > self._pool.total_cpu_cores:
            raise InsufficientResourcesError(
                task_id,
                f"needs {req.cpu_cores} CPU cores but pool has {self._pool.total_cpu_cores}",
            )
        if req.gpu_memory_gb > self._pool.total_gpu_memory_gb:
            raise InsufficientResourcesError(
                task_id,
                f"needs {req.gpu_memory_gb}GB GPU but pool has {self._pool.total_gpu_memory_gb}GB",
            )
        for name in req.exclusive_resources:
            if name not in self._exclusive_holders:
                raise ResourceNotDeclaredError(name)
        for api in req.api_rate_tokens:
            if api not in self._pool.api_rate_limits:
                raise InsufficientResourcesError(
                    task_id,
                    f"API {api!r} not declared in pool.",
                )

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cpu_available": self._cpu_available,
                "cpu_total": self._pool.total_cpu_cores,
                "gpu_available": self._gpu_available,
                "gpu_total": self._pool.total_gpu_memory_gb,
                "exclusive": dict(self._exclusive_holders),
                "api_tokens": dict(self._api_tokens),
            }

    def _check(self, req: ResourceRequirements) -> bool:
        if self._cpu_available < req.cpu_cores:
            return False
        if self._gpu_available < req.gpu_memory_gb:
            return False
        for name in req.exclusive_resources:
            if self._exclusive_holders.get(name) is not None:
                return False
        for api, tokens in req.api_rate_tokens.items():
            if self._api_tokens.get(api, 0) < tokens:
                return False
        return True

    def _replenish_loop(self) -> None:
        while self._replenish_running:
            time.sleep(1.0)
            with self._lock:
                for api, rate in self._pool.api_rate_limits.items():
                    current = self._api_tokens.get(api, 0)
                    self._api_tokens[api] = min(current + rate, rate)
                callbacks = list(self._release_callbacks)

            for cb in callbacks:
                try:
                    cb()
                except Exception:
                    pass
