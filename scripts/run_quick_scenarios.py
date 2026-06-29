#!/usr/bin/env python3
"""Quick scenario runner with per-scenario IP to avoid init rate limits."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BASE = "http://127.0.0.1:8000"

SCENARIOS = {
    "product_compare": [
        "What's the difference between Retify and your Forecasting Engine in terms of workflow and use case?",
    ],
    "rag_concept": [
        "What does demand planning actually mean in plain language?",
    ],
    "lending_bottleneck": [
        "We operate a regional commercial lending business. Approval turnaround went from 3 days to 9 days.",
        "We process around 220 loan applications per day with a 600-application compliance backlog. Prior doc automation failed — analysts went back to email.",
    ],
    "custom_architecture": [
        "We're building a two-sided marketplace for equipment rentals — bookings, payments, and vendor dashboards.",
        "Main pain is manual coordination between vendors and renters; we need to scale past 500 transactions per week.",
        "Can you design a system architecture for this? Include integrations and data flow.",
    ],
}


def run(name: str, messages: list[str], ip: str) -> None:
    print(f"\n=== {name} (ip={ip}) ===")
    with httpx.Client() as c:
        init = c.post(
            f"{BASE}/api/chat-init",
            json={"page_context": {"title": "t", "url": f"{BASE}/advisor"}},
            headers={"X-Forwarded-For": ip},
            timeout=30,
        )
        init.raise_for_status()
        data = init.json()
        sid, vid = data["sessionId"], data.get("visitorId")
        for i, msg in enumerate(messages, 1):
            payload = {
                "session_id": sid,
                "message": msg,
                "visitor_id": vid,
                "user_language": "en",
                "page_context": {"title": "t", "url": f"{BASE}/advisor"},
            }
            body = json.dumps(payload).encode()
            headers = {"Content-Type": "application/json", "X-Forwarded-For": ip}
            events: list[dict] = []
            text: list[str] = []
            with c.stream(
                "POST",
                f"{BASE}/api/chat",
                content=body,
                headers=headers,
                timeout=300,
            ) as resp:
                buf = ""
                for chunk in resp.iter_text():
                    buf += chunk
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw:
                            continue
                        try:
                            evt = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        events.append(evt)
                        if evt.get("type") == "delta":
                            text.append(evt.get("content") or "")
            tools = [e["tool"] for e in events if e.get("type") == "tool_start"]
            done = next((e for e in events if e.get("type") == "done"), {})
            rd = done.get("routerDecision") or {}
            print(
                f"T{i} mode={done.get('executionMode')} tools={tools} rag={done.get('ragStatus')} "
                f"intent={rd.get('intent')} tool={rd.get('tool_selected')} gates={rd.get('confidence_gates_applied')}"
            )
            excerpt = "".join(text).replace("\n", " ")[:400]
            print(f"  {excerpt}")
            if i < len(messages):
                time.sleep(4)


def main() -> None:
    for idx, (name, msgs) in enumerate(SCENARIOS.items()):
        run(name, msgs, f"10.99.0.{idx + 10}")


if __name__ == "__main__":
    main()
