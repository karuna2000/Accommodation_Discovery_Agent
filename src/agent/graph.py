from typing import Any

from langgraph.graph import END, StateGraph

from src.agent.nodes.evaluate import evaluate_node
from src.agent.nodes.execute import execute_node
from src.agent.nodes.intent import intent_node
from src.agent.nodes.plan import plan_node
from src.agent.nodes.synthesize import synthesize_node
from src.agent.nodes.validate import validate_node
from src.agent.state import AgentState


def _evaluate_router(state: AgentState) -> str:
    decision = state.get("decision", "execute")
    if decision == "synthesize":
        return "validate"
    if decision == "plan":
        return "plan"
    return "execute"


def _intent_router(state: AgentState) -> str:
    if state.get("needs_clarification"):
        return "synthesize"
    return "plan"


def build_agent() -> StateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("intent", intent_node)
    builder.add_node("plan", plan_node)
    builder.add_node("execute", execute_node)
    builder.add_node("evaluate", evaluate_node)
    builder.add_node("validate", validate_node)
    builder.add_node("synthesize", synthesize_node)

    builder.set_entry_point("intent")

    builder.add_conditional_edges("intent", _intent_router)
    builder.add_edge("plan", "execute")
    builder.add_edge("execute", "evaluate")
    builder.add_conditional_edges("evaluate", _evaluate_router)
    builder.add_edge("validate", "synthesize")
    builder.add_edge("synthesize", END)

    return builder


async def run_agent(
    query: str,
    tools: dict[str, Any],
    tool_schemas: list[dict],
    bedrock_client: Any | None = None,
    search_repo: Any | None = None,
    max_iterations: int = 5,
    max_steps: int = 10,
):
    context: dict[str, Any] = {
        "tools": tools,
        "tool_schemas": tool_schemas,
        "bedrock_client": bedrock_client,
        "search_repo": search_repo,
        "max_iterations": max_iterations,
        "max_steps": max_steps,
    }

    initial: AgentState = {
        "query": query,
        "intent": {},
        "plan": "",
        "step_index": 0,
        "max_steps": max_steps,
        "results": [],
        "synthesized_answer": None,
        "error": None,
        "iteration": 0,
        "decision": "execute",
        "step_vars": {},
        "page_stats": [],
        "needs_clarification": False,
        "clarification_message": None,
        "validation_report": None,
        "constraint_tier": 0,
    }

    graph = build_agent().compile()

    async for event in graph.astream(
        initial,
        config={"configurable": {"context": context, "thread_id": "agent-1"}},
    ):
        yield event
