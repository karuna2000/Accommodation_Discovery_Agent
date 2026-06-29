from mcp.server.fastmcp import FastMCP

from src.mcp.tools.base import BaseTool


def create_mcp_server(tools: dict[str, BaseTool]) -> FastMCP:
    mcp = FastMCP("accommodation-agent")

    for name, tool in tools.items():
        mcp.add_tool(
            fn=tool.run,
            name=name,
            description=tool.description,
            parameters=tool.input_schema,
        )

    return mcp
