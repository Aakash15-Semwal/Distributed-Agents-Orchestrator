from __future__ import annotations

import time


def fake_io_agent(task_id: str, payload: dict) -> dict:
    duration: float = float(payload.get("duration_seconds", 0.2))
    file_path: str = str(payload.get("file_path", "output.csv"))
    should_fail: bool = bool(payload.get("fail", False))

    if should_fail:
        raise IOError(f"[fake_io_agent] I/O write error on {file_path!r} for task {task_id!r}")

    time.sleep(duration)

    return {
        "status": "done",
        "task_id": task_id,
        "agent": "fake_io_agent",
        "file_path": file_path,
        "bytes_written": payload.get("bytes_written", 1024),
    }
