from typing import Any

from langgraph.graph import END, StateGraph

from src.agent.nodes.evaluate import evaluate_node
from src.agent.nodes.execute import execute_node
from src.agent.nodes.plan import plan_node
from src.agent.nodes.synthesize import synthesize_node
from src.agent.state import AgentState


def _router(state: AgentState) -> str:
    decision = state.get("decision", "execute")
    if decision == "synthesize":
        return "synthesize"
    if decision == "plan":
        return "plan"
    return "execute"


def build_agent() -> StateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("plan", plan_node)
    builder.add_node("execute", execute_node)
    builder.add_node("evaluate", evaluate_node)
    builder.add_node("synthesize", synthesize_node)

    builder.set_entry_point("plan")

    builder.add_edge("plan", "execute")
    builder.add_edge("execute", "evaluate")
    builder.add_conditional_edges("evaluate", _router)
    builder.add_edge("synthesize", END)

    return builder


async def run_agent(
    query: str,
    tools: dict[str, Any],
    tool_schemas: list[dict],
    bedrock_client: Any | None = None,
    max_iterations: int = 5,
    max_steps: int = 10,
):
    context: dict[str, Any] = {
        "tools": tools,
        "tool_schemas": tool_schemas,
        "bedrock_client": bedrock_client,
        "max_iterations": max_iterations,
        "max_steps": max_steps,
    }

    initial: AgentState = {
        "query": query,
        "plan": "",
        "step_index": 0,
        "max_steps": max_steps,
        "results": [],
        "synthesized_answer": None,
        "error": None,
        "iteration": 0,
        "decision": "execute",
    }

    graph = build_agent().compile()

    async for event in graph.astream(
        initial,
        config={"configurable": {"context": context, "thread_id": "agent-1"}},
    ):
        yield event
