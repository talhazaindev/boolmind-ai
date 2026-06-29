"""FastMCP server modules."""

from app.advisor.mcp.servers.calendar_server import calendar_mcp
from app.advisor.mcp.servers.crm_server import crm_mcp
from app.advisor.mcp.servers.experience_server import experience_mcp
from app.advisor.mcp.servers.knowledge_server import knowledge_mcp

ALL_MCPS = (knowledge_mcp, crm_mcp, calendar_mcp, experience_mcp)

__all__ = ["ALL_MCPS", "knowledge_mcp", "crm_mcp", "calendar_mcp", "experience_mcp"]
