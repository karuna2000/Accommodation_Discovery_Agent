from typing import Any, TypedDict


class AgentState(TypedDict):
    query: str
    intent: dict[str, Any]
    plan: str
    step_index: int
    max_steps: int
    results: list[dict[str, Any]]
    synthesized_answer: str | None
    error: str | None
    iteration: int
    decision: str
    step_vars: dict[str, Any]
    page_stats: list[dict[str, Any]]
    needs_clarification: bool
    clarification_message: str | None
    validation_report: dict | None
    constraint_tier: int
