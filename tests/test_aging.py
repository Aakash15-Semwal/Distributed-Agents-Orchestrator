from __future__ import annotations

import time

from orchestrator import ResourceRequirements, Task


def test_priority_aging_prevents_starvation(full_orchestrator, full_log_reader, monkeypatch):
    import orchestrator.scheduler as sched_module
    monkeypatch.setattr(sched_module, "AGING_INTERVAL_SECONDS", 0.1)

    low_prio = Task(
        name="low_prio_aged",
        agent_type="cpu_agent",
        resource_requirements=ResourceRequirements(cpu_cores=4.0),
        payload={"duration_seconds": 0.05},
        priority=1,
    )
    full_orchestrator.submit_task(low_prio)

    time.sleep(0.35)

    high_prio = Task(
        name="fresh_high_prio",
        agent_type="cpu_agent",
        resource_requirements=ResourceRequirements(cpu_cores=4.0),
        payload={"duration_seconds": 0.05},
        priority=2,
    )
    full_orchestrator.submit_task(high_prio)

    assert full_orchestrator.wait_until_done(timeout=5.0)

    events = full_log_reader.events_of_type("TASK_DISPATCHED")
    dispatched_ids = [e["task_id"] for e in events]

    idx_low = dispatched_ids.index(low_prio.task_id)
    idx_high = dispatched_ids.index(high_prio.task_id)

    assert idx_low < idx_high
