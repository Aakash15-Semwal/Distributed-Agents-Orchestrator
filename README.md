# Distributed Agents Orchestrator

A lightweight, concurrent multi-agent orchestration engine in Python. Built to coordinate fleets of agents, enforce hard concurrency limits, manage multi-dimensional resource pools (CPU, GPU VRAM, exclusive file locks, token-bucket rate limits), and handle agent crashes with watchdog timeouts and retry logic.

---

## Key Features

- **Multi-Resource Management**: Atomic all-or-nothing allocation of CPU cores, GPU VRAM, named exclusive locks (`output.csv`, `db_writer`), and token-bucket API rate limits (`tokens/sec`).
- **Two-Gate Scheduler**:
  - Hard concurrency limit (max 5 active agent threads).
  - Resource gate ensuring tasks never dispatch without all required resources.
- **Priority Queues & Starvation Prevention**: Higher-priority tasks dispatch first; waiting tasks automatically age over time so low-priority tasks never starve.
- **Fault Tolerance & Watchdog Timers**: Automatically detects unhandled exceptions and hangs using timer-based watchdogs; re-routes failed tasks according to configurable retry policies.
- **Decoupled Asynchronous Event Bus**: Non-blocking pub/sub system isolating task execution from logging and UI renders.
- **Live Terminal Dashboard**: Interactive TUI powered by `rich` with live resource bars, dispatched agent tables, statistics, and log feeds.
- **Structured JSONL Logging**: Append-only session logs (`logs/session_*.jsonl`) capturing every lifecycle milestone.

---

## Architecture Overview

```
                                 [ Orchestrator ]
                                        │
                 ┌──────────────────────┼──────────────────────┐
                 ▼                      ▼                      ▼
           [ Task Queue ]       [ Scheduler ]         [ Resource Manager ]
                 │                ▲         │          (CPU / GPU / Locks / Tokens)
                 │                │         │
                 ▼                │         ▼
         [ Priority Queue ] ──────┘   [ Agent Threads ] (max 5)
                                            │
                                            ▼
                                     [ Event Bus ]
                                     (Async Pub/Sub)
                                            │
                             ┌──────────────┴──────────────┐
                             ▼                             ▼
                      [ Dashboard ]                  [ JSONL Logger ]
                       (Rich TUI)                     (Disk storage)
```

---

## Project Structure

```
Distributed Agents Orchestrator/
├── orchestrator/
│   ├── __init__.py           # Public exports
│   ├── core.py               # Orchestrator facade & lifecycle
│   ├── scheduler.py          # Priority queue, 2-gate dispatch, priority aging
│   ├── resource_manager.py   # RLock pools, exclusive locks, token bucket
│   ├── agent_runner.py       # AgentThread, watchdog timer, safe cleanup
│   ├── agent_registry.py     # Agent function registry
│   ├── event_bus.py          # Async pub/sub EventBus
│   ├── dashboard.py          # Rich terminal dashboard
│   ├── logger.py             # JSONL structured logger
│   ├── task.py               # Task, ResourceRequirements, ResourcePool
│   └── exceptions.py         # Custom exception hierarchy
├── agents/
│   ├── __init__.py           # Agent exports
│   ├── base_agent.py         # AgentProtocol structural type
│   ├── fake_cpu_agent.py     # CPU-bound simulation
│   ├── fake_gpu_agent.py     # GPU VRAM simulation
│   ├── fake_io_agent.py      # Exclusive file write simulation
│   └── fake_api_agent.py     # Rate-limited API simulation
├── tests/
│   ├── conftest.py           # Pytest fixtures & LogReader
│   ├── test_basic.py         # Single task & lifecycle events
│   ├── test_concurrency.py   # Parallel speedup & 5-thread cap
│   ├── test_resource_contention.py # Exclusive locks & token bucket
│   ├── test_priority.py      # Priority order & FIFO tie-breaking
│   ├── test_aging.py         # Starvation prevention & priority aging
│   ├── test_failure_retry.py # Crash recovery & retry exhaustion
│   └── test_timeout.py       # Watchdog timeout & retry handling
├── main.py                   # Live showcase with rich TUI
├── manual_test.py            # Headless manual test script
├── requirements.txt          # Dependencies (rich, pytest, pytest-timeout)
└── README.md
```

---

## Installation & Setup

1. **Clone the repository:**
   ```powershell
   git clone https://github.com/Aakash15-Semwal/Distributed-Agents-Orchestrator.git
   cd "Distributed Agents Orchestrator"
   ```

2. **Create and activate a virtual environment:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. **Install dependencies:**
   ```powershell
   pip install -r requirements.txt
   ```

---

## Usage

### 1. Run the Live Terminal Dashboard Demo (`main.py`)
Launches the full interactive showcase:
```powershell
python main.py
```

### 2. Run the Headless Manual Test (`manual_test.py`)
Submits a mix of GPU, CPU, exclusive I/O, and API tasks:
```powershell
python manual_test.py
```

### 3. Run the Automated Test Suite
Run all 15 tests across all four phases:
```powershell
pytest tests/ -v
```

---

## Example Usage in Code

```python
from orchestrator import Orchestrator, Task, ResourcePool, ResourceRequirements
from agents import fake_cpu_agent, fake_gpu_agent

# 1. Define available resources
pool = ResourcePool(
    total_cpu_cores=4.0,
    total_gpu_memory_gb=8.0,
    exclusive_resources=["output.csv"],
    api_rate_limits={"openai": 2},
)

# 2. Instantiate and register agents
orc = Orchestrator(pool=pool)
orc.register_agent("cpu_agent", fake_cpu_agent)
orc.register_agent("gpu_agent", fake_gpu_agent)
orc.start()

# 3. Submit a high-priority GPU task
orc.submit_task(Task(
    name="model_inference",
    agent_type="gpu_agent",
    resource_requirements=ResourceRequirements(gpu_memory_gb=4.0),
    priority=10,
    timeout_seconds=5.0,
    max_retries=2,
))

# 4. Wait for all tasks to complete and shutdown
orc.wait_until_done()
orc.stop()
```
