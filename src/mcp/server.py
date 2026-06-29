from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.tools.base import Tool
from mcp.server.fastmcp.utilities.func_metadata import ArgModelBase, FuncMetadata

from src.mcp.tools.base import BaseTool


class _EmptyArgModel(ArgModelBase):
    pass


_EMPTY_FN_META = FuncMetadata(arg_model=_EmptyArgModel)


def create_mcp_server(tools: dict[str, BaseTool]) -> FastMCP:
    mcp = FastMCP("accommodation-agent")

    for name, tool in tools.items():
        t = Tool(
            fn=tool.run,
            name=name,
            description=tool.description,
            parameters=tool.input_schema,
            fn_metadata=_EMPTY_FN_META,
            is_async=True,
            context_kwarg=None,
        )
        mcp._tool_manager._tools[name] = t

    return mcp
