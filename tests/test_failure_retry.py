from __future__ import annotations

from orchestrator import ResourceRequirements, Task
from tests.helpers import wait_for_event_type


def test_agent_crash_retry_success(full_orchestrator, full_log_reader):
    task = Task(
        name="flaky_task",
        agent_type="cpu_agent",
        resource_requirements=ResourceRequirements(cpu_cores=1.0),
        payload={"duration_seconds": 0.05, "fail": True},
        max_retries=2,
    )

    attempt_counts = {"count": 0}

    def flaky_agent(task_id: str, payload: dict) -> dict:
        attempt_counts["count"] += 1
        if attempt_counts["count"] == 1:
            raise RuntimeError("Temporary crash on first attempt")
        return {"status": "done", "recovered": True}

    full_orchestrator.register_agent("flaky_agent", flaky_agent)
    flaky_task = Task(
        name="flaky_run",
        agent_type="flaky_agent",
        resource_requirements=ResourceRequirements(cpu_cores=1.0),
        max_retries=2,
    )

    full_orchestrator.submit_task(flaky_task)
    assert full_orchestrator.wait_until_done(timeout=5.0)

    events = full_log_reader.events_for(flaky_task.task_id)
    event_names = [e["event"] for e in events]

    assert "TASK_FAILED" in event_names
    assert "TASK_RETRYING" in event_names
    assert "TASK_COMPLETED" in event_names
    assert attempt_counts["count"] == 2


def test_agent_crash_max_retries_exhausted(full_orchestrator, full_log_reader):
    def always_crash_agent(task_id: str, payload: dict) -> dict:
        raise ValueError("Permanent fatal bug")

    full_orchestrator.register_agent("failing_agent", always_crash_agent)

    task = Task(
        name="doomed_task",
        agent_type="failing_agent",
        resource_requirements=ResourceRequirements(cpu_cores=1.0),
        max_retries=2,
    )

    full_orchestrator.submit_task(task)
    assert full_orchestrator.wait_until_done(timeout=5.0)

    events = full_log_reader.events_for(task.task_id)
    event_names = [e["event"] for e in events]

    failed_count = event_names.count("TASK_FAILED")
    retrying_count = event_names.count("TASK_RETRYING")

    assert failed_count == 3
    assert retrying_count == 2
    assert "TASK_PERMANENTLY_FAILED" in event_names
    assert "TASK_COMPLETED" not in event_names

    perm_failed = next(e for e in events if e["event"] == "TASK_PERMANENTLY_FAILED")
    assert perm_failed["total_attempts"] == 3
