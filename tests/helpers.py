from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tests.conftest import LogReader


def wait_for_event_type(
    reader: LogReader,
    event_type: str,
    task_id: str | None = None,
    timeout: float = 5.0,
    poll_interval: float = 0.05,
) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        events = reader.events_of_type(event_type)
        if task_id is not None:
            events = [e for e in events if e.get("task_id") == task_id]
        if events:
            return events[0]
        time.sleep(poll_interval)

    raise TimeoutError(
        f"Event {event_type!r} (task_id={task_id!r}) did not appear in log within {timeout}s"
    )
