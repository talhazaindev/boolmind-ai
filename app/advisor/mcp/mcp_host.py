"""MCP host — lifecycle for in-process FastMCP servers."""

from __future__ import annotations

import logging

from app.advisor.mcp.servers import ALL_MCPS

logger = logging.getLogger(__name__)


class McpHost:
    """Boots advisor MCP servers (in-process; no HTTP on chat hot path)."""

    def __init__(self) -> None:
        self.servers = list(ALL_MCPS)

    def startup(self) -> None:
        names = [getattr(s, "name", str(s)) for s in self.servers]
        logger.info("Advisor MCP host ready: %s", ", ".join(names))

    def shutdown(self) -> None:
        logger.info("Advisor MCP host shutdown")


_host: McpHost | None = None


def get_mcp_host() -> McpHost:
    global _host
    if _host is None:
        _host = McpHost()
        _host.startup()
    return _host
