from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class AgentProtocol(Protocol):
    def __call__(self, task_id: str, payload: dict) -> dict:
        ...
