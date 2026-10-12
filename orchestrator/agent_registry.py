from __future__ import annotations

from typing import Callable

from .exceptions import AgentNotFoundError

AgentFn = Callable[[str, dict], dict]


class AgentRegistry:
    def __init__(self) -> None:
        self._registry: dict[str, AgentFn] = {}

    def register(self, agent_type: str, fn: AgentFn) -> None:
        if not callable(fn):
            raise TypeError(f"Agent function for {agent_type!r} must be callable.")
        self._registry[agent_type] = fn

    def get(self, agent_type: str) -> AgentFn:
        fn = self._registry.get(agent_type)
        if fn is None:
            raise AgentNotFoundError(agent_type)
        return fn

    def is_registered(self, agent_type: str) -> bool:
        return agent_type in self._registry

    def registered_types(self) -> list[str]:
        return sorted(self._registry.keys())

    def __repr__(self) -> str:
        return f"AgentRegistry(types={self.registered_types()})"
