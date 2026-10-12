from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from agents.fake_cpu_agent import fake_cpu_agent
from orchestrator import Orchestrator, ResourcePool


@pytest.fixture
def cpu_pool() -> ResourcePool:
    return ResourcePool(
        total_cpu_cores=4.0,
        total_gpu_memory_gb=0.0,
        exclusive_resources=[],
        api_rate_limits={},
    )


@pytest.fixture
def orchestrator(cpu_pool, tmp_path) -> Orchestrator:
    orc = Orchestrator(pool=cpu_pool, log_dir=tmp_path / "logs")
    orc.register_agent("cpu_agent", fake_cpu_agent)
    orc.start()

    yield orc

    orc.stop()


class LogReader:
    def __init__(self, log_file: Path) -> None:
        self._log_file = log_file

    def _wait_for_file(self, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while not self._log_file.exists():
            if time.monotonic() > deadline:
                raise FileNotFoundError(f"Log file not created within {timeout}s: {self._log_file}")
            time.sleep(0.05)

    def events(self) -> list[dict]:
        self._wait_for_file()
        entries = []
        with open(self._log_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return entries

    def events_for(self, task_id: str) -> list[dict]:
        return [e for e in self.events() if e.get("task_id") == task_id]

    def events_of_type(self, event_type: str) -> list[dict]:
        return [e for e in self.events() if e.get("event") == event_type]

    def has_event(self, event_type: str, task_id: str | None = None) -> bool:
        events = self.events_of_type(event_type)
        if task_id is not None:
            events = [e for e in events if e.get("task_id") == task_id]
        return len(events) > 0


@pytest.fixture
def log_reader(orchestrator) -> LogReader:
    deadline = time.monotonic() + 5.0
    while orchestrator.log_file is None:
        if time.monotonic() > deadline:
            raise RuntimeError("Orchestrator log file was not created within 5s")
        time.sleep(0.05)

    return LogReader(orchestrator.log_file)
