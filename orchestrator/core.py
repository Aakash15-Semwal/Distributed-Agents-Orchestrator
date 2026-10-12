from __future__ import annotations

from pathlib import Path

from .agent_registry import AgentFn, AgentRegistry
from .event_bus import Event, EventBus, EventType
from .exceptions import AgentNotFoundError, OrchestratorNotRunningError
from .logger import Logger
from .resource_manager import ResourceManager
from .scheduler import MAX_CONCURRENT_AGENTS, Scheduler
from .task import ResourcePool, Task, TaskAttempt


class Orchestrator:
    def __init__(
        self,
        pool: ResourcePool | None = None,
        max_agents: int = MAX_CONCURRENT_AGENTS,
        log_dir: str | Path = "logs",
    ) -> None:
        self._pool = pool or ResourcePool()
        self._max_agents = max_agents
        self._running = False

        self._bus = EventBus()
        self._rm = ResourceManager(pool=self._pool, event_bus=self._bus)
        self._registry = AgentRegistry()
        self._scheduler = Scheduler(
            resource_manager=self._rm,
            agent_registry=self._registry,
            event_bus=self._bus,
        )
        self._logger = Logger(event_bus=self._bus, log_dir=log_dir)
        self._scheduler.wire_completion_events()

    def register_agent(self, agent_type: str, fn: AgentFn) -> "Orchestrator":
        self._registry.register(agent_type, fn)
        return self

    def define_resources(self, pool: ResourcePool) -> "Orchestrator":
        if self._running:
            raise RuntimeError("Cannot change resource pool while orchestrator is running.")
        self._pool = pool
        self._rm = ResourceManager(pool=pool, event_bus=self._bus)
        self._scheduler = Scheduler(
            resource_manager=self._rm,
            agent_registry=self._registry,
            event_bus=self._bus,
        )
        self._scheduler.wire_completion_events()
        return self

    def start(self) -> "Orchestrator":
        if self._running:
            return self

        self._bus.start()
        self._logger.start()
        self._rm.start()
        self._scheduler.start()
        self._running = True

        self._bus.publish(Event(
            EventType.ORCHESTRATOR_STARTED,
            data={
                "pool": {
                    "cpu_cores": self._pool.total_cpu_cores,
                    "gpu_gb": self._pool.total_gpu_memory_gb,
                    "exclusive_resources": self._pool.exclusive_resources,
                    "api_rate_limits": self._pool.api_rate_limits,
                },
                "max_agents": self._max_agents,
                "registered_agents": self._registry.registered_types(),
            },
        ))
        return self

    def stop(self, timeout: float = 10.0) -> None:
        if not self._running:
            return

        self._running = False
        self._bus.publish(Event(EventType.ORCHESTRATOR_STOPPED))

        self._scheduler.stop(timeout=timeout)
        self._rm.stop()
        self._logger.stop()
        self._bus.stop(timeout=timeout)

    def __enter__(self) -> "Orchestrator":
        return self.start()

    def __exit__(self, *_) -> None:
        self.stop()

    def submit_task(self, task: Task) -> None:
        if not self._running:
            raise OrchestratorNotRunningError()

        if not self._registry.is_registered(task.agent_type):
            raise AgentNotFoundError(task.agent_type)

        self._rm.validate_requirements(task.resource_requirements, task.task_id)

        self._bus.publish(Event(
            EventType.TASK_SUBMITTED,
            data={
                "task_id": task.task_id,
                "task_name": task.name,
                "agent_type": task.agent_type,
                "priority": task.priority,
                "requirements": repr(task.resource_requirements),
            },
        ))

        self._scheduler.submit(TaskAttempt(task=task))

    def wait_until_done(self, timeout: float | None = None) -> bool:
        return self._scheduler.wait_until_done(timeout=timeout)

    @property
    def log_file(self) -> Path | None:
        return self._logger.log_file

    @property
    def event_bus(self) -> EventBus:
        return self._bus

    def resource_snapshot(self) -> dict:
        return self._rm.snapshot()

    def active_agent_count(self) -> int:
        return self._scheduler.active_count()

    def queue_size(self) -> int:
        return self._scheduler.queue_size()

    def __repr__(self) -> str:
        status = "running" if self._running else "stopped"
        return (
            f"Orchestrator({status}, active={self.active_agent_count()}, queued={self.queue_size()})"
        )
