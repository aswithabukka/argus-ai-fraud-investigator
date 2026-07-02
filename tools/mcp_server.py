"""MCP server exposing the Argus transaction data tools.

This is the rubric's "MCP server" concept: the same functions in
`tools/data_tools.py`, served over the Model Context Protocol via stdio.
ADK agents connect to it with `MCPToolset` (see agents/retriever.py), and any
MCP-capable client (Claude Desktop, Gemini CLI, an IDE) can use it too.

Run standalone:
    python -m tools.mcp_server
"""

import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import data_tools

mcp = FastMCP("argus-transaction-data")

for fn in data_tools.ALL_TOOLS:
    mcp.tool()(fn)


if __name__ == "__main__":
    mcp.run(transport="stdio")
