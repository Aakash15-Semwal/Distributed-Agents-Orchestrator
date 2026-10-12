from __future__ import annotations

import pytest

from orchestrator import (
    AgentNotFoundError,
    ResourceRequirements,
    Task,
)
from tests.helpers import wait_for_event_type


def test_single_task_success(orchestrator, log_reader):
    task = Task(
        name="test_task_1",
        agent_type="cpu_agent",
        resource_requirements=ResourceRequirements(cpu_cores=1.0),
        payload={"duration_seconds": 0.1, "result_value": "hello_world"},
    )

    orchestrator.submit_task(task)

    done = orchestrator.wait_until_done(timeout=5.0)
    assert done, "Orchestrator did not complete task within timeout"

    completed_event = wait_for_event_type(log_reader, "TASK_COMPLETED", task_id=task.task_id)
    assert completed_event["result"]["result_value"] == "hello_world"
    assert completed_event["result"]["status"] == "done"


def test_task_lifecycle_events(orchestrator, log_reader):
    task = Task(
        name="test_lifecycle",
        agent_type="cpu_agent",
        resource_requirements=ResourceRequirements(cpu_cores=1.0),
        payload={"duration_seconds": 0.05},
    )

    orchestrator.submit_task(task)
    assert orchestrator.wait_until_done(timeout=5.0)

    task_events = log_reader.events_for(task.task_id)
    event_names = [e["event"] for e in task_events]

    assert "TASK_SUBMITTED" in event_names
    assert "TASK_DISPATCHED" in event_names
    assert "AGENT_STARTED" in event_names
    assert "TASK_COMPLETED" in event_names

    idx_sub = event_names.index("TASK_SUBMITTED")
    idx_disp = event_names.index("TASK_DISPATCHED")
    idx_start = event_names.index("AGENT_STARTED")
    idx_comp = event_names.index("TASK_COMPLETED")

    assert idx_sub < idx_disp <= idx_start < idx_comp


def test_unregistered_agent_raises(orchestrator):
    task = Task(
        name="invalid_agent_task",
        agent_type="unknown_agent",
    )

    with pytest.raises(AgentNotFoundError):
        orchestrator.submit_task(task)
