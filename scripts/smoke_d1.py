"""Single-case D1 smoke test (no Groq burst)."""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from run_manual_tests import chat_init, parse_sse_chat, tools_from_events  # noqa: E402

BASE = "http://127.0.0.1:8000"
PAGE = f"{BASE}/advisor?product=retify"


def main() -> None:
    with httpx.Client() as c:
        init = chat_init(c, PAGE, "retify", test_ip="10.0.9.99")
        sid, vid = init["sessionId"], init["visitorId"]
        msg = (
            "Map Retify pipeline to our stack: POS from Shopify, "
            "ERP logs, warehouse in Snowflake."
        )
        events, text, status = parse_sse_chat(
            c, sid, msg, vid, PAGE, "retify", "10.0.9.99"
        )
        tools = tools_from_events(events)
        errs = [e for e in events if e.get("type") == "error"]
        print("status", status)
        print("tools", tools)
        print("errors", errs)
        print("text_len", len(text))
        print("excerpt:", (text[:500] if text else "(empty)"))


if __name__ == "__main__":
    main()
