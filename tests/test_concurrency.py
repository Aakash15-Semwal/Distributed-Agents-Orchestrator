from __future__ import annotations

import time

from orchestrator import ResourceRequirements, Task


def test_concurrent_tasks_parallel_speedup(full_orchestrator, full_log_reader):
    task_duration = 0.3
    num_tasks = 4

    tasks = [
        Task(
            name=f"concurrent_cpu_{i}",
            agent_type="cpu_agent",
            resource_requirements=ResourceRequirements(cpu_cores=1.0),
            payload={"duration_seconds": task_duration},
        )
        for i in range(num_tasks)
    ]

    start_time = time.monotonic()
    for t in tasks:
        full_orchestrator.submit_task(t)

    assert full_orchestrator.wait_until_done(timeout=5.0)
    total_elapsed = time.monotonic() - start_time

    assert total_elapsed < (task_duration * num_tasks * 0.8)

    completed_events = full_log_reader.events_of_type("TASK_COMPLETED")
    assert len(completed_events) == num_tasks


def test_thread_cap_enforcement(full_orchestrator):
    task_duration = 0.4
    num_tasks = 8

    tasks = [
        Task(
            name=f"cap_task_{i}",
            agent_type="cpu_agent",
            resource_requirements=ResourceRequirements(cpu_cores=0.5),
            payload={"duration_seconds": task_duration},
        )
        for i in range(num_tasks)
    ]

    for t in tasks:
        full_orchestrator.submit_task(t)

    time.sleep(0.08)
    active_count = full_orchestrator.active_agent_count()
    assert active_count <= 5

    assert full_orchestrator.wait_until_done(timeout=6.0)
