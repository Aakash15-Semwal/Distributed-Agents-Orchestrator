from __future__ import annotations

import time


def fake_cpu_agent(task_id: str, payload: dict) -> dict:
    duration: float = float(payload.get("duration_seconds", 1.0))
    should_fail: bool = bool(payload.get("fail", False))

    if should_fail:
        raise RuntimeError(f"[fake_cpu_agent] Simulated crash for task {task_id!r}")

    time.sleep(duration)

    return {
        "status": "done",
        "task_id": task_id,
        "agent": "fake_cpu_agent",
        "simulated_duration_s": duration,
        "result_value": payload.get("result_value", 42),
    }
