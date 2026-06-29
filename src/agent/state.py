from typing import Any, TypedDict


class AgentState(TypedDict):
    query: str
    plan: str
    step_index: int
    max_steps: int
    results: list[dict[str, Any]]
    synthesized_answer: str | None
    error: str | None
    iteration: int
    decision: str
    step_vars: dict[str, Any]
