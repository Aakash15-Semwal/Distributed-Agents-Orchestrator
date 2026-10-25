from __future__ import annotations

import time

from agents import fake_api_agent, fake_cpu_agent, fake_gpu_agent, fake_io_agent
from orchestrator import Orchestrator, ResourcePool, ResourceRequirements, Task


def main() -> None:
    pool = ResourcePool(
        total_cpu_cores=4.0,
        total_gpu_memory_gb=8.0,
        exclusive_resources=["output.csv"],
        api_rate_limits={"openai": 2},
    )

    print("=" * 60)
    print("DISTRIBUTED AGENTS ORCHESTRATOR - MANUAL TEST RUN")
    print("=" * 60)
    print(f"Resource Pool: {pool.total_cpu_cores} CPUs | {pool.total_gpu_memory_gb}GB GPU | Exclusives: {pool.exclusive_resources}")

    orc = Orchestrator(pool=pool)
    orc.register_agent("cpu_agent", fake_cpu_agent)
    orc.register_agent("gpu_agent", fake_gpu_agent)
    orc.register_agent("io_agent", fake_io_agent)
    orc.register_agent("api_agent", fake_api_agent)

    orc.start()
    print("\n[+] Orchestrator started.")

    tasks = [
        Task(
            name="train_neural_net",
            agent_type="gpu_agent",
            resource_requirements=ResourceRequirements(gpu_memory_gb=4.0),
            payload={"duration_seconds": 0.5, "result_value": "model_weights.bin"},
            priority=10,
        ),
        Task(
            name="export_csv_report_1",
            agent_type="io_agent",
            resource_requirements=ResourceRequirements(exclusive_resources=["output.csv"]),
            payload={"duration_seconds": 0.3, "file_path": "output.csv"},
            priority=5,
        ),
        Task(
            name="export_csv_report_2",
            agent_type="io_agent",
            resource_requirements=ResourceRequirements(exclusive_resources=["output.csv"]),
            payload={"duration_seconds": 0.3, "file_path": "output.csv"},
            priority=4,
        ),
        Task(
            name="call_llm_api",
            agent_type="api_agent",
            resource_requirements=ResourceRequirements(api_rate_tokens={"openai": 1}),
            payload={"duration_seconds": 0.2, "endpoint": "openai"},
            priority=8,
        ),
        Task(
            name="crunch_numbers",
            agent_type="cpu_agent",
            resource_requirements=ResourceRequirements(cpu_cores=2.0),
            payload={"duration_seconds": 0.4, "result_value": 9999},
            priority=7,
        ),
    ]

    print(f"\n[+] Submitting {len(tasks)} tasks with varying priorities and resource demands...")
    for t in tasks:
        orc.submit_task(t)
        print(f"  -> Submitted: {t.name:<22} (Agent: {t.agent_type:<10} | Priority: {t.priority:>2} | {t.resource_requirements})")

    time.sleep(0.1)
    print("\n[+] System Snapshot during execution:")
    print(f"  Active Agents : {orc.active_agent_count()}")
    print(f"  Queued Tasks  : {orc.queue_size()}")
    print(f"  Resources     : {orc.resource_snapshot()}")

    print("\n[+] Waiting for all tasks to complete...")
    start_wait = time.monotonic()
    done = orc.wait_until_done(timeout=10.0)
    elapsed = round(time.monotonic() - start_wait, 2)

    if done:
        print(f"[+] All tasks completed successfully in {elapsed}s!")
    else:
        print(f"[-] Timed out after {elapsed}s.")

    log_path = orc.log_file
    orc.stop()
    print("[+] Orchestrator stopped cleanly.")
    if log_path:
        print(f"[+] Session log saved to: {log_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
