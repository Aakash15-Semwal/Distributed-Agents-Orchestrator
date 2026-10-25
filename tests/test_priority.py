from __future__ import annotations

import time

from orchestrator import ResourceRequirements, Task


def test_priority_dispatch_ordering(full_orchestrator, full_log_reader):
    blocking_task = Task(
        name="blocking_task",
        agent_type="cpu_agent",
        resource_requirements=ResourceRequirements(cpu_cores=8.0),
        payload={"duration_seconds": 0.3},
        priority=5,
    )
    full_orchestrator.submit_task(blocking_task)
    time.sleep(0.05)

    low_prio = Task(
        name="low_prio_task",
        agent_type="cpu_agent",
        resource_requirements=ResourceRequirements(cpu_cores=4.0),
        payload={"duration_seconds": 0.1},
        priority=1,
    )
    high_prio = Task(
        name="high_prio_task",
        agent_type="cpu_agent",
        resource_requirements=ResourceRequirements(cpu_cores=4.0),
        payload={"duration_seconds": 0.1},
        priority=10,
    )

    full_orchestrator.submit_task(low_prio)
    full_orchestrator.submit_task(high_prio)

    assert full_orchestrator.wait_until_done(timeout=5.0)

    events = full_log_reader.events_of_type("TASK_DISPATCHED")
    dispatched_ids = [e["task_id"] for e in events]

    assert blocking_task.task_id in dispatched_ids
    assert high_prio.task_id in dispatched_ids
    assert low_prio.task_id in dispatched_ids

    idx_high = dispatched_ids.index(high_prio.task_id)
    idx_low = dispatched_ids.index(low_prio.task_id)
    assert idx_high < idx_low


def test_fifo_ordering_for_equal_priority(full_orchestrator, full_log_reader):
    blocking = Task(
        name="blocking",
        agent_type="cpu_agent",
        resource_requirements=ResourceRequirements(cpu_cores=8.0),
        payload={"duration_seconds": 0.25},
        priority=5,
    )
    full_orchestrator.submit_task(blocking)
    time.sleep(0.05)

    t1 = Task(
        name="equal_1",
        agent_type="cpu_agent",
        resource_requirements=ResourceRequirements(cpu_cores=4.0),
        payload={"duration_seconds": 0.05},
        priority=6,
    )
    t2 = Task(
        name="equal_2",
        agent_type="cpu_agent",
        resource_requirements=ResourceRequirements(cpu_cores=4.0),
        payload={"duration_seconds": 0.05},
        priority=6,
    )

    full_orchestrator.submit_task(t1)
    full_orchestrator.submit_task(t2)

    assert full_orchestrator.wait_until_done(timeout=5.0)

    events = full_log_reader.events_of_type("TASK_DISPATCHED")
    dispatched_ids = [e["task_id"] for e in events]

    idx_t1 = dispatched_ids.index(t1.task_id)
    idx_t2 = dispatched_ids.index(t2.task_id)
    assert idx_t1 < idx_t2
