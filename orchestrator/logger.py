from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from .event_bus import Event, EventBus, EventType


class Logger:
    def __init__(self, event_bus: EventBus, log_dir: str | Path = "logs") -> None:
        self._bus = event_bus
        self._log_dir = Path(log_dir)
        self._log_file: Path | None = None
        self._file_handle = None
        self._write_lock = threading.Lock()

    def start(self) -> None:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        self._log_file = self._log_dir / f"session_{ts}.jsonl"
        self._file_handle = open(self._log_file, "a", encoding="utf-8")  # noqa: WPS515

        for event_type in EventType:
            self._bus.subscribe(event_type, self._handle_event)

        self._write({
            "event": "LOGGER_STARTED",
            "log_file": str(self._log_file),
        })

    def stop(self) -> None:
        if self._file_handle:
            self._write({"event": "LOGGER_STOPPED"})
            with self._write_lock:
                self._file_handle.flush()
                self._file_handle.close()
                self._file_handle = None

    @property
    def log_file(self) -> Path | None:
        return self._log_file

    def _handle_event(self, event: Event) -> None:
        entry = {
            "ts": datetime.fromtimestamp(event.timestamp, tz=timezone.utc).isoformat(),
            "event": event.type.name,
            **event.data,
        }
        self._write(entry)

    def _write(self, entry: dict) -> None:
        if self._file_handle is None:
            return
        line = json.dumps(entry, default=str) + "\n"
        with self._write_lock:
            self._file_handle.write(line)
            self._file_handle.flush()
