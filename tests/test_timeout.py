from __future__ import annotations

import time

from orchestrator import ResourceRequirements, Task


def test_agent_watchdog_timeout_and_retry_success(full_orchestrator, full_log_reader):
    attempt_tracker = {"count": 0}

    def slow_then_fast_agent(task_id: str, payload: dict) -> dict:
        attempt_tracker["count"] += 1
        if attempt_tracker["count"] == 1:
            time.sleep(0.4)
            return {"status": "too_late"}
        time.sleep(0.05)
        return {"status": "done", "attempt": attempt_tracker["count"]}

    full_orchestrator.register_agent("slow_agent", slow_then_fast_agent)

    task = Task(
        name="timeout_retry_task",
        agent_type="slow_agent",
        resource_requirements=ResourceRequirements(cpu_cores=1.0),
        timeout_seconds=0.15,
        max_retries=1,
    )

    full_orchestrator.submit_task(task)
    assert full_orchestrator.wait_until_done(timeout=5.0)

    events = full_log_reader.events_for(task.task_id)
    event_names = [e["event"] for e in events]

    assert "TASK_TIMEOUT" in event_names
    assert "TASK_RETRYING" in event_names
    assert "TASK_COMPLETED" in event_names


def test_agent_watchdog_timeout_exhausted(full_orchestrator, full_log_reader):
    def hanging_agent(task_id: str, payload: dict) -> dict:
        time.sleep(0.4)
        return {"status": "never_reached"}

    full_orchestrator.register_agent("hanging_agent", hanging_agent)

    task = Task(
        name="perpetual_hang",
        agent_type="hanging_agent",
        resource_requirements=ResourceRequirements(cpu_cores=1.0),
        timeout_seconds=0.1,
        max_retries=1,
    )

    full_orchestrator.submit_task(task)
    assert full_orchestrator.wait_until_done(timeout=5.0)

    events = full_log_reader.events_for(task.task_id)
    event_names = [e["event"] for e in events]

    timeout_count = event_names.count("TASK_TIMEOUT")
    assert timeout_count == 2
    assert "TASK_PERMANENTLY_FAILED" in event_names
    assert "TASK_COMPLETED" not in event_names
