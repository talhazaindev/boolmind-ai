"""Thread D tool-layer smoke (no Groq) — maps to advisor-manual-test-plan section 6."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.advisor.mcp.mcp_tool_router import McpToolRouter  # noqa: E402
from app.advisor.orchestrator.product_context import ProductContext  # noqa: E402


async def run() -> list[dict[str, str]]:
    router = McpToolRouter()
    ctx = ProductContext(
        active_product="retify",
        active_product_name="Retify",
        products_discussed=["retify"],
        namespace="retify",
    )
    sid = "smoke-thread-d"
    cases: list[tuple[str, str, dict]] = [
        ("D1", "rag_query", {"query": "Retify 10-step workflow Shopify Snowflake"}),
        ("D3", "generate_architecture_proposal", {
            "summary": "Multi-source retail ingest to Snowflake",
            "product_id": "retify",
        }),
        ("D4", "generate_fidp", {
            "description": "Pipeline dashboard mockup",
            "product_id": "retify",
        }),
        ("D5", "product_compare", {"products": ["retify", "ecg", "legal"]}),
        ("D6", "product_tour", {"product_id": "retify", "start_step": 3}),
    ]
    out: list[dict[str, str]] = []
    for tid, tool, args in cases:
        r = await router.call_tool(tool, args, ctx, sid, None)
        status = "PASS" if r.success else "PARTIAL" if r.fallback else "FAIL"
        snippet = ""
        if r.data:
            snippet = json.dumps(r.data)[:200]
        elif r.fallback:
            snippet = r.fallback[:200]
        out.append({"id": tid, "tool": tool, "status": status, "snippet": snippet})
        print(f"{tid} {tool}: {status} — {snippet[:120]}")
    return out


if __name__ == "__main__":
    asyncio.run(run())
