"""boolmind-crm MCP server: crm_create_lead."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

crm_mcp = FastMCP("boolmind-crm")

# Tool registration for external MCP hosts; runtime chat uses McpToolRouter → handlers.
