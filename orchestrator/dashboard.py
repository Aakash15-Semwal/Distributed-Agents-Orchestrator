from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table
from rich.text import Text

from .event_bus import Event, EventBus, EventType

if TYPE_CHECKING:
    from .core import Orchestrator


class Dashboard:
    def __init__(self, orchestrator: Orchestrator, refresh_per_second: float = 4.0) -> None:
        self._orc = orchestrator
        self._bus = orchestrator.event_bus
        self._refresh_rate = refresh_per_second

        self._start_time = time.monotonic()
        self._logs: list[str] = []
        self._max_logs = 6

        self._counts = {
            "completed": 0,
            "failed": 0,
            "timeout": 0,
            "retrying": 0,
        }

        self._active_agents: dict[str, dict] = {}
        self._lock = threading.Lock()

        self._live: Live | None = None
        self._thread: threading.Thread | None = None
        self._running = False

        self._subscribe_events()

    def _subscribe_events(self) -> None:
        self._bus.subscribe(EventType.TASK_DISPATCHED, self._on_dispatched)
        self._bus.subscribe(EventType.TASK_COMPLETED, self._on_completed)
        self._bus.subscribe(EventType.TASK_FAILED, self._on_failed)
        self._bus.subscribe(EventType.TASK_TIMEOUT, self._on_timeout)
        self._bus.subscribe(EventType.TASK_RETRYING, self._on_retrying)
        self._bus.subscribe(EventType.TASK_PERMANENTLY_FAILED, self._on_permanently_failed)

    def _add_log(self, text: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self._logs.append(f"[{ts}] {text}")
        if len(self._logs) > self._max_logs:
            self._logs.pop(0)

    def _on_dispatched(self, event: Event) -> None:
        with self._lock:
            tid = event.data["task_id"]
            self._active_agents[tid] = {
                "name": event.data.get("task_name", tid),
                "agent": event.data.get("agent_type", "unknown"),
                "priority": event.data.get("priority", 5),
                "attempt": event.data.get("attempt", 1),
                "start": time.monotonic(),
            }
            self._add_log(f"[bold cyan]DISPATCH[/] {event.data.get('task_name')} -> {event.data.get('agent_type')}")

    def _on_completed(self, event: Event) -> None:
        with self._lock:
            tid = event.data["task_id"]
            self._active_agents.pop(tid, None)
            self._counts["completed"] += 1
            self._add_log(f"[bold green]COMPLETE[/] {event.data.get('task_name')} in {event.data.get('duration_s')}s")

    def _on_failed(self, event: Event) -> None:
        with self._lock:
            tid = event.data["task_id"]
            self._active_agents.pop(tid, None)
            self._counts["failed"] += 1
            self._add_log(f"[bold red]FAILED[/] {event.data.get('task_name')} (Attempt {event.data.get('attempt')})")

    def _on_timeout(self, event: Event) -> None:
        with self._lock:
            tid = event.data["task_id"]
            self._active_agents.pop(tid, None)
            self._counts["timeout"] += 1
            self._add_log(f"[bold yellow]TIMEOUT[/] {event.data.get('task_name')} after {event.data.get('timeout_seconds')}s")

    def _on_retrying(self, event: Event) -> None:
        with self._lock:
            self._counts["retrying"] += 1
            self._add_log(f"[bold magenta]RETRY[/] {event.data.get('task_name')} attempt {event.data.get('attempt')}")

    def _on_permanently_failed(self, event: Event) -> None:
        with self._lock:
            self._add_log(f"[bold red on black]PERM-FAIL[/] {event.data.get('task_name')} after {event.data.get('total_attempts')} attempts")

    def _render_layout(self) -> Layout:
        elapsed = round(time.monotonic() - self._start_time, 1)

        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=8),
        )
        layout["body"].split_row(
            Layout(name="resources", ratio=1),
            Layout(name="agents", ratio=2),
        )

        header_text = Text(
            f" DISTRIBUTED AGENTS ORCHESTRATOR | Runtime: {elapsed}s | Active Threads: {self._orc.active_agent_count()}/5 | Queue: {self._orc.queue_size()} ",
            style="bold white on blue",
            justify="center",
        )
        layout["header"].update(Panel(header_text, style="blue"))

        snap = self._orc.resource_snapshot()
        cpu_used = snap["cpu_total"] - snap["cpu_available"]
        gpu_used = snap["gpu_total"] - snap["gpu_available"]

        res_table = Table(box=None, expand=True)
        res_table.add_column("Resource", style="bold")
        res_table.add_column("Usage", justify="right")

        res_table.add_row("CPU Cores", f"{cpu_used:.1f} / {snap['cpu_total']:.1f}")
        res_table.add_row("GPU Memory", f"{gpu_used:.1f}GB / {snap['gpu_total']:.1f}GB")

        for k, v in snap.get("exclusive", {}).items():
            holder_str = f"[red]{v[:6]}[/]" if v else "[green]FREE[/]"
            res_table.add_row(f"Lock: {k}", holder_str)

        for k, v in snap.get("api_tokens", {}).items():
            res_table.add_row(f"API: {k}", f"{v} tokens")

        layout["resources"].update(Panel(res_table, title="[bold]Resource Pool[/]", border_style="cyan"))

        agent_table = Table(box=None, expand=True)
        agent_table.add_column("Task", style="bold")
        agent_table.add_column("Agent", style="dim")
        agent_table.add_column("Pri", justify="center")
        agent_table.add_column("Att", justify="center")
        agent_table.add_column("Elapsed", justify="right")

        with self._lock:
            for tid, info in list(self._active_agents.items()):
                live_dur = round(time.monotonic() - info["start"], 1)
                agent_table.add_row(
                    info["name"][:18],
                    info["agent"],
                    str(info["priority"]),
                    str(info["attempt"]),
                    f"{live_dur}s",
                )

        layout["agents"].update(Panel(agent_table, title="[bold]Active Dispatched Agents[/]", border_style="green"))

        with self._lock:
            stats = f"[green]Completed: {self._counts['completed']}[/]  |  [red]Failed: {self._counts['failed']}[/]  |  [yellow]Timeouts: {self._counts['timeout']}[/]  |  [magenta]Retries: {self._counts['retrying']}[/]"
            log_block = "\n".join(self._logs) if self._logs else "[dim]Waiting for tasks...[/]"

        footer_group = Group(
            Text.from_markup(stats),
            Text.from_markup(log_block),
        )
        layout["footer"].update(Panel(footer_group, title="[bold]Activity & Logs[/]", border_style="white"))

        return layout

    def start(self) -> None:
        self._running = True
        self._live = Live(self._render_layout(), refresh_per_second=self._refresh_rate, screen=False)
        self._live.start()

        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="Dashboard-Render")
        self._thread.start()

    def _run_loop(self) -> None:
        while self._running:
            if self._live:
                try:
                    self._live.update(self._render_layout())
                except Exception:
                    pass
            time.sleep(1.0 / self._refresh_rate)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        if self._live:
            self._live.stop()
            self._live = None
