from __future__ import annotations

import time

from agents import fake_api_agent, fake_cpu_agent, fake_gpu_agent, fake_io_agent
from orchestrator import Dashboard, Orchestrator, ResourcePool, ResourceRequirements, Task


def main() -> None:
    pool = ResourcePool(
        total_cpu_cores=4.0,
        total_gpu_memory_gb=8.0,
        exclusive_resources=["output.csv", "db_writer"],
        api_rate_limits={"openai": 2, "claude": 1},
    )

    orc = Orchestrator(pool=pool)
    orc.register_agent("cpu_agent", fake_cpu_agent)
    orc.register_agent("gpu_agent", fake_gpu_agent)
    orc.register_agent("io_agent", fake_io_agent)
    orc.register_agent("api_agent", fake_api_agent)

    flaky_state = {"attempt": 0}

    def flaky_agent(task_id: str, payload: dict) -> dict:
        flaky_state["attempt"] += 1
        if flaky_state["attempt"] == 1:
            time.sleep(0.1)
            raise RuntimeError("Transient crash on first attempt")
        time.sleep(0.2)
        return {"status": "recovered", "attempts": flaky_state["attempt"]}

    orc.register_agent("flaky_agent", flaky_agent)

    orc.start()

    dashboard = Dashboard(orchestrator=orc, refresh_per_second=4.0)
    dashboard.start()

    tasks = [
        Task(
            name="train_vision_model",
            agent_type="gpu_agent",
            resource_requirements=ResourceRequirements(gpu_memory_gb=4.0),
            payload={"duration_seconds": 1.2, "result_value": "vision_v1.pt"},
            priority=10,
        ),
        Task(
            name="crunch_dataset_batch",
            agent_type="cpu_agent",
            resource_requirements=ResourceRequirements(cpu_cores=2.0),
            payload={"duration_seconds": 0.8},
            priority=8,
        ),
        Task(
            name="write_metrics_csv",
            agent_type="io_agent",
            resource_requirements=ResourceRequirements(exclusive_resources=["output.csv"]),
            payload={"duration_seconds": 0.5, "file_path": "output.csv"},
            priority=7,
        ),
        Task(
            name="append_log_csv",
            agent_type="io_agent",
            resource_requirements=ResourceRequirements(exclusive_resources=["output.csv"]),
            payload={"duration_seconds": 0.5, "file_path": "output.csv"},
            priority=6,
        ),
        Task(
            name="query_llm_embeddings",
            agent_type="api_agent",
            resource_requirements=ResourceRequirements(api_rate_tokens={"openai": 1}),
            payload={"duration_seconds": 0.4, "endpoint": "openai"},
            priority=7,
        ),
        Task(
            name="flaky_recovery_job",
            agent_type="flaky_agent",
            resource_requirements=ResourceRequirements(cpu_cores=1.0),
            priority=9,
            max_retries=2,
        ),
        Task(
            name="background_analytics",
            agent_type="cpu_agent",
            resource_requirements=ResourceRequirements(cpu_cores=1.0),
            payload={"duration_seconds": 0.6},
            priority=3,
        ),
        Task(
            name="cache_cleanup",
            agent_type="cpu_agent",
            resource_requirements=ResourceRequirements(cpu_cores=1.0),
            payload={"duration_seconds": 0.3},
            priority=2,
        ),
    ]

    for t in tasks:
        orc.submit_task(t)
        time.sleep(0.05)

    orc.wait_until_done(timeout=15.0)
    time.sleep(1.0)

    dashboard.stop()
    orc.stop()

    print("\n[+] Demonstration completed cleanly.")
    if orc.log_file:
        print(f"[+] Session log saved at: {orc.log_file}\n")


if __name__ == "__main__":
    main()
