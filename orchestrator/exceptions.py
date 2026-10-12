class OrchestratorError(Exception):
    """Base class for all orchestrator exceptions."""


class AgentNotFoundError(OrchestratorError):
    def __init__(self, agent_type: str) -> None:
        self.agent_type = agent_type
        super().__init__(f"No agent registered for type {agent_type!r}.")


class ResourceNotDeclaredError(OrchestratorError):
    def __init__(self, resource_name: str) -> None:
        self.resource_name = resource_name
        super().__init__(f"Exclusive resource {resource_name!r} not declared in ResourcePool.")


class InsufficientResourcesError(OrchestratorError):
    def __init__(self, task_id: str, detail: str) -> None:
        self.task_id = task_id
        super().__init__(f"Task {task_id!r} exceeds pool capacity: {detail}")


class OrchestratorNotRunningError(OrchestratorError):
    def __init__(self) -> None:
        super().__init__("The orchestrator is not running. Call start() first.")


class AgentTimeoutError(OrchestratorError):
    def __init__(self, task_id: str, timeout: float) -> None:
        self.task_id = task_id
        self.timeout = timeout
        super().__init__(f"Agent for task {task_id!r} exceeded timeout of {timeout}s.")
