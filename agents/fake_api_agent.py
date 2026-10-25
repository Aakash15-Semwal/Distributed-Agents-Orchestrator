from __future__ import annotations

import time


def fake_api_agent(task_id: str, payload: dict) -> dict:
    duration: float = float(payload.get("duration_seconds", 0.1))
    endpoint: str = str(payload.get("endpoint", "openai"))
    should_fail: bool = bool(payload.get("fail", False))

    if should_fail:
        raise ConnectionError(f"[fake_api_agent] Rate limit or connection error for task {task_id!r}")

    time.sleep(duration)

    return {
        "status": "done",
        "task_id": task_id,
        "agent": "fake_api_agent",
        "endpoint": endpoint,
        "response_code": 200,
    }
