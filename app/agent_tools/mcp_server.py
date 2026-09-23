"""Expose LocalLibrary read-only tools over MCP stdio (Agent track M1).

Install with the ``agent`` extra, then point an MCP client at
``patent-workbench-mcp [--db PATH]``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from app.agent_tools.tools import TOOL_DESCRIPTIONS, TOOL_NAMES, LibraryTools, open_read_only
from app.desktop.paths import AppPaths

INSTRUCTIONS = (
    "悬架/减振器专利 LocalLibrary 的只读工具。结论必须引用返回结果 receipts 中的公开号；"
    "结果只覆盖本地库。不得据此给出新颖性、FTO、侵权或概率性结论。"
    "公司名先用 list_companies 查精确名称。"
)


def build_server(tools: LibraryTools) -> FastMCP:
    server = FastMCP("patent-workbench", instructions=INSTRUCTIONS)
    read_only = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
    for name in TOOL_NAMES:
        server.add_tool(
            getattr(tools, name),
            name=name,
            description=TOOL_DESCRIPTIONS[name],
            annotations=read_only,
        )
    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="LocalLibrary read-only MCP server")
    parser.add_argument(
        "--db",
        type=Path,
        default=AppPaths.default().library_db,
        help="LocalLibrary SQLite path (default: the desktop app's database)",
    )
    args = parser.parse_args(argv)
    build_server(open_read_only(args.db)).run("stdio")


if __name__ == "__main__":
    main()
