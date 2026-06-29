from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolDependencies:
    # Infrastructure clients (injected at startup)
    brave_client: Any = None
    firecrawl_client: Any = None
    bedrock_client: Any = None
    search_repo: Any = None
    cache_repo: Any = None
    job_repo: Any = None
    idem_repo: Any = None

    # Cancellation registry
    cancel_registry: Any = None

    # Pre-created tool instances (set by registry)
    tools: dict[str, "BaseTool"] = field(default_factory=dict)


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    input_schema: dict = {}

    def __init__(self, deps: ToolDependencies):
        self._deps = deps

    @abstractmethod
    async def run(self, **kwargs) -> Any: ...
