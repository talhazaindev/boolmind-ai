"""Optional HTTP mounts for external MCP clients (not on widget hot path)."""

from __future__ import annotations

from fastapi import FastAPI

from app.advisor.mcp.servers.calendar_server import calendar_mcp
from app.advisor.mcp.servers.crm_server import crm_mcp
from app.advisor.mcp.servers.experience_server import experience_mcp
from app.advisor.mcp.servers.knowledge_server import knowledge_mcp


def mount_advisor_mcp_servers(app: FastAPI) -> None:
    """Mount FastMCP SSE endpoints for debugging / external hosts."""
    try:
        app.mount("/mcp/knowledge", knowledge_mcp.sse_app())
        app.mount("/mcp/crm", crm_mcp.sse_app())
        app.mount("/mcp/calendar", calendar_mcp.sse_app())
        app.mount("/mcp/experience", experience_mcp.sse_app())
    except Exception:
        # SSE mount optional — in-process router is primary
        pass
