from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResourceRequirements:
    cpu_cores: float = 0.0
    gpu_memory_gb: float = 0.0
    exclusive_resources: list[str] = field(default_factory=list)
    api_rate_tokens: dict[str, int] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return (
            self.cpu_cores == 0.0
            and self.gpu_memory_gb == 0.0
            and not self.exclusive_resources
            and not self.api_rate_tokens
        )

    def __repr__(self) -> str:
        parts = []
        if self.cpu_cores:
            parts.append(f"cpu={self.cpu_cores}")
        if self.gpu_memory_gb:
            parts.append(f"gpu={self.gpu_memory_gb}GB")
        if self.exclusive_resources:
            parts.append(f"exclusive={self.exclusive_resources}")
        if self.api_rate_tokens:
            parts.append(f"api={self.api_rate_tokens}")
        return f"ResourceRequirements({', '.join(parts) or 'none'})"


@dataclass
class ResourcePool:
    total_cpu_cores: float = 4.0
    total_gpu_memory_gb: float = 8.0
    exclusive_resources: list[str] = field(default_factory=list)
    api_rate_limits: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Task:
    name: str
    agent_type: str
    resource_requirements: ResourceRequirements = field(default_factory=ResourceRequirements)
    payload: dict[str, Any] = field(default_factory=dict)
    priority: int = 5
    max_retries: int = 2
    timeout_seconds: float = 30.0
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def __post_init__(self) -> None:
        if not (1 <= self.priority <= 10):
            raise ValueError(f"priority must be 1-10, got {self.priority}")
        if self.timeout_seconds <= 0:
            raise ValueError(f"timeout_seconds must be positive, got {self.timeout_seconds}")
        if self.max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {self.max_retries}")

    def __repr__(self) -> str:
        return (
            f"Task(id={self.task_id!r}, name={self.name!r}, "
            f"agent={self.agent_type!r}, priority={self.priority})"
        )

    def __lt__(self, other: Task) -> bool:
        return self.priority > other.priority


# @dataclass
# class TaskAttempt:
#     task: Task
#     attempt_number: int = 1

#     @property
#     def task_id(self) -> str:
#         return self.task.task_id

#     @property
#     def has_retries_remaining(self) -> bool:
#         return self.attempt_number <= self.task.max_retries

#     def next_attempt(self) -> "TaskAttempt":
#         return TaskAttempt(task=self.task, attempt_number=self.attempt_number + 1)

#     def __repr__(self) -> str:
#         return (
#             f"TaskAttempt(id={self.task_id!r}, attempt={self.attempt_number}/"
#             f"{self.task.max_retries + 1})"
#         )
@dataclass
class TaskAttempt:
    task: Task
    attempt_number: int = 1

    @property
    def task_id(self) -> str:
        return self.task.task_id

    @property
    def has_retries_remaining(self) -> bool:
        """
        Return True if another execution attempt is allowed.

        max_retries represents the number of retries after
        the initial attempt.

        Therefore:
            max_retries = 0 -> 1 total attempt
            max_retries = 1 -> 2 total attempts
            max_retries = 2 -> 3 total attempts
        """
        return self.attempt_number <= self.task.max_retries + 1

    def next_attempt(self) -> "TaskAttempt":
        return TaskAttempt(
            task=self.task,
            attempt_number=self.attempt_number + 1,
        )

    def __repr__(self) -> str:
        return (
            f"TaskAttempt(id={self.task_id!r}, "
            f"attempt={self.attempt_number}/"
            f"{self.task.max_retries + 1})"
        )
