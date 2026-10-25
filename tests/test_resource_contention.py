from __future__ import annotations

import time

from orchestrator import ResourceRequirements, Task


def test_exclusive_resource_mutual_exclusion(full_orchestrator, full_log_reader):
    task_duration = 0.25
    exclusive_name = "output.csv"

    task_a = Task(
        name="io_task_a",
        agent_type="io_agent",
        resource_requirements=ResourceRequirements(exclusive_resources=[exclusive_name]),
        payload={"duration_seconds": task_duration, "file_path": exclusive_name},
    )
    task_b = Task(
        name="io_task_b",
        agent_type="io_agent",
        resource_requirements=ResourceRequirements(exclusive_resources=[exclusive_name]),
        payload={"duration_seconds": task_duration, "file_path": exclusive_name},
    )

    start_time = time.monotonic()
    full_orchestrator.submit_task(task_a)
    full_orchestrator.submit_task(task_b)

    assert full_orchestrator.wait_until_done(timeout=5.0)
    elapsed = time.monotonic() - start_time

    assert elapsed >= (task_duration * 1.8)

    events_a = full_log_reader.events_for(task_a.task_id)
    events_b = full_log_reader.events_for(task_b.task_id)

    comp_a = next(e for e in events_a if e["event"] == "TASK_COMPLETED")
    disp_b = next(e for e in events_b if e["event"] == "TASK_DISPATCHED")

    comp_b = next(e for e in events_b if e["event"] == "TASK_COMPLETED")
    disp_a = next(e for e in events_a if e["event"] == "TASK_DISPATCHED")

    a_then_b = disp_b["ts"] >= comp_a["ts"]
    b_then_a = disp_a["ts"] >= comp_b["ts"]
    assert a_then_b or b_then_a


def test_gpu_memory_pool_limits(full_orchestrator):
    task_1 = Task(
        name="gpu_big_1",
        agent_type="gpu_agent",
        resource_requirements=ResourceRequirements(gpu_memory_gb=10.0),
        payload={"duration_seconds": 0.3},
    )
    task_2 = Task(
        name="gpu_big_2",
        agent_type="gpu_agent",
        resource_requirements=ResourceRequirements(gpu_memory_gb=10.0),
        payload={"duration_seconds": 0.3},
    )

    full_orchestrator.submit_task(task_1)
    full_orchestrator.submit_task(task_2)

    time.sleep(0.08)
    snapshot = full_orchestrator.resource_snapshot()
    assert snapshot["gpu_available"] >= 0.0

    assert full_orchestrator.wait_until_done(timeout=5.0)


def test_api_rate_limit_token_consumption(full_orchestrator):
    task_api_1 = Task(
        name="api_req_1",
        agent_type="api_agent",
        resource_requirements=ResourceRequirements(api_rate_tokens={"openai": 2}),
        payload={"duration_seconds": 0.1, "endpoint": "openai"},
    )
    task_api_2 = Task(
        name="api_req_2",
        agent_type="api_agent",
        resource_requirements=ResourceRequirements(api_rate_tokens={"openai": 2}),
        payload={"duration_seconds": 0.1, "endpoint": "openai"},
    )

    start = time.monotonic()
    full_orchestrator.submit_task(task_api_1)
    full_orchestrator.submit_task(task_api_2)

    assert full_orchestrator.wait_until_done(timeout=5.0)
    elapsed = time.monotonic() - start

    assert elapsed >= 0.8
