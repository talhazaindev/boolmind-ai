"""SSE event shape tests."""

import json


def test_sse_event_types() -> None:
    events = [
        {"type": "delta", "content": "Hi"},
        {"type": "tool_start", "tool": "rag_query", "input": {"query": "x"}},
        {"type": "tool_result", "tool": "rag_query", "result": {}},
        {"type": "done", "sessionId": "s1", "stage": "EXPLORE"},
        {"type": "error", "code": "INTERNAL", "message": "fail"},
    ]
    for evt in events:
        line = f"data: {json.dumps(evt)}"
        assert line.startswith("data:")
        parsed = json.loads(line[5:].strip())
        assert parsed["type"] in ("delta", "tool_start", "tool_result", "done", "error")
