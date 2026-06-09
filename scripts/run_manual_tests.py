#!/usr/bin/env python3
"""Execute advisor-manual-test-plan cases against live API; write results report."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402

BASE = "http://127.0.0.1:8000"
DELAY_S = 12  # Groq rate-limit buffer


@dataclass
class CaseResult:
    test_id: str
    status: str  # PASS, FAIL, PARTIAL, SKIP, ERROR
    tools_seen: list[str] = field(default_factory=list)
    assistant_excerpt: str = ""
    notes: list[str] = field(default_factory=list)
    http_status: int = 0


def _sign_body(body: bytes, secret: str) -> dict[str, str]:
    ts = str(int(time.time()))
    sig = hmac.new(
        secret.encode(),
        f"{ts}.{body.decode('utf-8')}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return {"X-Chat-Timestamp": ts, "X-Chat-Signature": sig}


def chat_init(
    client: httpx.Client,
    url: str = "http://127.0.0.1:8000/advisor",
    product_id: str | None = None,
    visitor_id: str | None = None,
    test_ip: str = "127.0.0.1",
) -> dict[str, Any]:
    pc: dict[str, Any] = {
        "title": "Boolmind Advisor Test",
        "url": url,
    }
    if product_id:
        pc["product_id"] = product_id
    r = client.post(
        f"{BASE}/api/chat-init",
        json={"visitor_id": visitor_id, "page_context": pc},
        headers={"X-Forwarded-For": test_ip},
        timeout=30.0,
    )
    r.raise_for_status()
    return r.json()


def parse_sse_chat(
    client: httpx.Client,
    session_id: str,
    message: str,
    visitor_id: str | None,
    page_url: str = "http://127.0.0.1:8000/advisor",
    product_id: str | None = None,
    test_ip: str = "127.0.0.1",
) -> tuple[list[dict[str, Any]], str, int]:
    payload = {
        "session_id": session_id,
        "message": message,
        "visitor_id": visitor_id,
        "user_language": "en",
        "page_context": {
            "title": "Test",
            "url": page_url,
            "product_id": product_id,
        },
    }
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "X-Forwarded-For": test_ip}
    if settings.chat_api_secret:
        headers.update(_sign_body(body, settings.chat_api_secret))

    events: list[dict[str, Any]] = []
    text_parts: list[str] = []
    with client.stream(
        "POST",
        f"{BASE}/api/chat",
        content=body,
        headers=headers,
        timeout=120.0,
    ) as resp:
        status = resp.status_code
        buf = ""
        for chunk in resp.iter_text():
            buf += chunk
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.strip()
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
                if evt.get("type") == "delta" and evt.get("content"):
                    text_parts.append(evt["content"])
    return events, "".join(text_parts), status


def tools_from_events(events: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for e in events:
        if e.get("type") == "tool_start" and e.get("tool"):
            t = e["tool"]
            if t not in seen:
                seen.append(t)
    return seen


def check_contains(text: str, keywords: list[str]) -> tuple[bool, list[str]]:
    lower = text.lower()
    missing = [k for k in keywords if k.lower() not in lower]
    return len(missing) == 0, missing


def check_forbidden(text: str, forbidden: list[str]) -> tuple[bool, list[str]]:
    lower = text.lower()
    found = [f for f in forbidden if f.lower() in lower]
    return len(found) == 0, found


def is_rate_limit_error(events: list[dict[str, Any]], notes: list[str]) -> bool:
    if any(e.get("type") == "error" and e.get("code") == "RATE_LIMIT" for e in events):
        return True
    blob = " ".join(notes).lower()
    return "high demand" in blob or "rate limit" in blob


def expect_tools(actual: list[str], expected: list[str], optional: bool = False) -> tuple[bool, str]:
    if not expected:
        return True, "no tool required"
    if optional:
        if any(t in actual for t in expected):
            return True, f"one of {expected} seen"
        return False, f"expected one of {expected}, got {actual}"
    missing = [t for t in expected if t not in actual]
    if missing and optional is False:
        # allow superset (model may chain tools)
        if not any(t in actual for t in expected):
            return False, f"missing {missing}, got {actual}"
    return True, f"tools: {actual}"


@dataclass
class ChatThread:
    name: str
    page_url: str
    product_id: str | None
    cases: list[dict[str, Any]]


THREADS: list[ChatThread] = [
    ChatThread(
        "A-Naive",
        "http://127.0.0.1:8000/advisor",
        None,
        [
            {
                "id": "A1",
                "msg": "Hi, what does Boolmind actually do?",
                "tools": ["rag_query"],
                "tools_optional": True,
                "must": ["retify", "ecg", "legal"],
                "forbid": ["$", "pricing is"],
            },
            {
                "id": "A2",
                "msg": "I run a chain of stores and our sales data is a mess. Which product fits?",
                "tools": ["rag_query"],
                "tools_optional": True,
                "must": ["retify", "retail"],
            },
            {
                "id": "A3",
                "msg": "Can you walk me through it?",
                "tools": ["product_tour"],
                "must": [],
            },
            {
                "id": "A4",
                "msg": "How is that different from your medical product?",
                "tools": ["product_compare", "rag_query"],
                "tools_optional": True,
                "must": ["10", "7"],
                "forbid": ["identical", "same features", "interchangeable"],
            },
            {
                "id": "A5",
                "msg": "What does it cost?",
                "tools": [],
                "forbid": ["$", "per month", "/month", "pricing is $"],
                "must_any": ["team", "connect", "discovery", "pricing"],
            },
            {
                "id": "A6",
                "msg": "OK I'm interested — my name is Sam Lee and email sam.lee@example.com, we need help unifying store data.",
                "tools": ["crm_create_lead"],
                "tools_optional": True,
                "forbid": ["phone number", "company size"],
            },
            {
                "id": "A7",
                "msg": "Can I book a call?",
                "tools": ["calendar_get_slots"],
                "tools_optional": True,
            },
        ],
    ),
    ChatThread(
        "B-ECG",
        "http://127.0.0.1:8000/advisor?product=ecg",
        "ecg",
        [
            {
                "id": "B2",
                "msg": "We get Holter PDFs and some WFDB exports. What can you ingest?",
                "tools": ["rag_query"],
                "tools_optional": True,
                "must": ["wfdb"],
            },
            {
                "id": "B3",
                "msg": "What happens in the OCR step?",
                "tools": ["rag_query"],
                "tools_optional": True,
                "must": ["ocr"],
            },
            {
                "id": "B4",
                "msg": "Show me a tour of ECG",
                "tools": ["product_tour"],
            },
            {
                "id": "B5",
                "msg": "Compare ECG and Legal Data Fusion for our hospital legal team",
                "tools": ["product_compare"],
                "tools_optional": True,
            },
            {
                "id": "B6",
                "msg": "We're also looking at retail analytics for the gift shop — is ECG enough?",
                "tools": ["rag_query"],
                "tools_optional": True,
                "must": ["retify"],
            },
        ],
    ),
    ChatThread(
        "C-Legal",
        "http://127.0.0.1:8000/advisor?product=legal",
        "legal",
        [
            {
                "id": "C1",
                "msg": "What is Legal Data Fusion in plain English?",
                "tools": ["rag_query"],
                "tools_optional": True,
                "must": ["6", "legal"],
            },
            {
                "id": "C2",
                "msg": "We have contracts CSV and matter exports in JSON. Supported?",
                "tools": ["rag_query"],
                "tools_optional": True,
                "must": ["csv", "json"],
            },
            {
                "id": "C3",
                "msg": "Give me a walkthrough",
                "tools": ["product_tour"],
            },
            {
                "id": "C4",
                "msg": "Compare all three Boolmind products for a general counsel office",
                "tools": ["product_compare"],
                "tools_optional": True,
            },
            {
                "id": "C5",
                "msg": "My email is jordan@lawfirm.example — name Jordan Reese, we need dataset consolidation.",
                "tools": ["crm_create_lead"],
                "tools_optional": True,
            },
        ],
    ),
    ChatThread(
        "D-Technical-Retify",
        "http://127.0.0.1:8000/advisor?product=retify",
        "retify",
        [
            {
                "id": "D1",
                "msg": "Map Retify's pipeline to our stack: POS from Shopify, ERP logs, warehouse in Snowflake.",
                "tools": ["rag_query"],
                "tools_optional": True,
                "must": ["10"],
            },
            {
                "id": "D2",
                "msg": "Which step handles entity resolution across SKU and store IDs?",
                "tools": ["rag_query"],
                "tools_optional": True,
                "must": ["entity", "match"],
            },
            {
                "id": "D3",
                "msg": "Design a technical architecture for ingesting multi-format retail feeds into Snowflake with schema drift handling.",
                "tools": ["generate_architecture_proposal"],
                "tools_optional": True,
            },
            {
                "id": "D4",
                "msg": "Show me a UI mockup / visual preview for this pipeline",
                "tools": ["generate_fidp"],
                "tools_optional": True,
            },
            {
                "id": "D5",
                "msg": "Compare Retify workflow step count vs ECG and Legal explicitly",
                "tools": ["product_compare"],
                "tools_optional": True,
                "must": ["10", "7", "6"],
            },
            {
                "id": "D6",
                "msg": "Give me the Retify tour from step 3",
                "tools": ["product_tour"],
                "tools_optional": True,
            },
        ],
    ),
    ChatThread(
        "E-Technical-ECG",
        "http://127.0.0.1:8000/advisor?product=ecg",
        "ecg",
        [
            {
                "id": "E1",
                "msg": "How do you normalize QT and QRS into an EMR-friendly schema?",
                "tools": ["rag_query"],
                "tools_optional": True,
                "must": ["normal", "emr"],
            },
            {
                "id": "E3",
                "msg": "Architecture for hospital PACS to OCR to FHIR Observation resources",
                "tools": ["generate_architecture_proposal"],
                "tools_optional": True,
            },
            {
                "id": "E4",
                "msg": "12-lead printout JPEG quality is poor — which preprocessing step helps?",
                "tools": ["rag_query"],
                "tools_optional": True,
                "must": ["preprocess", "image"],
            },
        ],
    ),
    ChatThread(
        "F-Multi",
        "http://127.0.0.1:8000/advisor",
        None,
        [
            {
                "id": "F1",
                "msg": "Compare Retify and ECG only — we're not interested in legal",
                "tools": ["product_compare"],
                "tools_optional": True,
            },
            {
                "id": "F2",
                "msg": "Actually we're a law firm with billing spreadsheets",
                "tools": ["rag_query"],
                "tools_optional": True,
                "must": ["legal"],
            },
            {
                "id": "F3",
                "msg": "Tour for that product",
                "tools": ["product_tour"],
                "tools_optional": True,
            },
        ],
    ),
    ChatThread(
        "G-Booking",
        "http://127.0.0.1:8000/advisor",
        None,
        [
            {
                "id": "G1",
                "msg": "I'd like to schedule a discovery call next week",
                "tools": ["calendar_get_slots"],
                "tools_optional": True,
            },
            {
                "id": "G2",
                "msg": "Book the first available slot — I'm Morgan Taylor, morgan.t@company.com, timezone UTC",
                "tools": ["calendar_book_slot"],
                "tools_optional": True,
            },
        ],
    ),
    ChatThread(
        "I-Guardrails",
        "http://127.0.0.1:8000/advisor",
        None,
        [
            {
                "id": "I1",
                "msg": "What's your price for 500 stores?",
                "tools": [],
                "forbid": ["$", "/store", "per store"],
            },
            {
                "id": "I4",
                "msg": "Retify and ECG have the exact same features right?",
                "tools": ["rag_query", "product_compare"],
                "tools_optional": True,
                "forbid": ["yes, they are the same", "identical features", "exact same"],
            },
            {
                "id": "I5",
                "msg": "Tell me about Product X that Boolmind doesn't sell",
                "tools": [],
                "forbid": ["product x is our"],
            },
        ],
    ),
]


def evaluate_case(case: dict[str, Any], events: list[dict], text: str, status: int) -> CaseResult:
    tid = case["id"]
    tools = tools_from_events(events)
    notes: list[str] = []
    if status != 200:
        return CaseResult(tid, "ERROR", tools, text[:300], [f"HTTP {status}"], status)

    if any(e.get("type") == "error" for e in events):
        err = next(e for e in events if e.get("type") == "error")
        return CaseResult(tid, "ERROR", tools, text[:300], [err.get("message", "SSE error")], status)

    ok = True
    exp = case.get("tools", [])
    if exp:
        tok, msg = expect_tools(tools, exp, case.get("tools_optional", False))
        notes.append(msg)
        if not tok:
            ok = False

    if case.get("must"):
        cok, miss = check_contains(text, case["must"])
        if not cok:
            ok = False
            notes.append(f"missing keywords: {miss}")

    if case.get("must_any"):
        if not any(k.lower() in text.lower() for k in case["must_any"]):
            ok = False
            notes.append(f"need one of: {case['must_any']}")

    if case.get("forbid"):
        fok, found = check_forbidden(text, case["forbid"])
        if not fok:
            ok = False
            notes.append(f"forbidden found: {found}")

    # Tour tool result check
    if "product_tour" in tools:
        for e in events:
            if e.get("type") == "tool_result" and e.get("tool") == "product_tour":
                r = e.get("result") or {}
                if r.get("steps"):
                    notes.append(f"tour steps={len(r.get('steps', []))}")
                else:
                    ok = False
                    notes.append("tour result empty")

    st = "PASS" if ok else "PARTIAL" if text else "FAIL"
    return CaseResult(tid, st, tools, text[:400], notes, status)


def run_infrastructure(client: httpx.Client) -> list[CaseResult]:
    results: list[CaseResult] = []
    ip = "10.0.0.1"
    try:
        h = client.get(f"{BASE}/health", timeout=10).json()
        ready = h.get("advisor_tier_a_ready")
        results.append(
            CaseResult(
                "INFRA-health",
                "PASS" if ready else "FAIL",
                [],
                json.dumps(h)[:200],
                [f"tier_a={ready}"],
            )
        )
    except Exception as e:
        results.append(CaseResult("INFRA-health", "ERROR", [], "", [str(e)]))

    try:
        a = client.get(f"{BASE}/api/admin/stats", timeout=10).json()
        results.append(
            CaseResult("INFRA-admin", "PASS", [], json.dumps(a)[:200], ["admin stats ok"])
        )
    except Exception as e:
        results.append(CaseResult("INFRA-admin", "ERROR", [], "", [str(e)]))

    for i, (label, url, pid) in enumerate(
        [
            ("INFRA-init-general", "http://127.0.0.1:8000/advisor", None),
            ("INFRA-init-ecg", "http://127.0.0.1:8000/advisor?product=ecg", "ecg"),
            ("INFRA-init-compare", "http://127.0.0.1:8000/compare", None),
        ]
    ):
        try:
            data = chat_init(client, url, pid, test_ip=f"10.0.0.{10 + i}")
            opening = data.get("openingMessage") or ""
            ok = bool(data.get("sessionId"))
            if pid == "ecg" and opening:
                ok = ok and ("ecg" in opening.lower() or "scanned" in opening.lower())
            if "compare" in url and opening:
                ok = ok and "compar" in opening.lower()
            results.append(
                CaseResult(
                    label,
                    "PASS" if ok else "PARTIAL",
                    [],
                    opening[:200],
                    [f"session={data.get('sessionId', '')[:8]}…"],
                )
            )
        except Exception as e:
            results.append(CaseResult(label, "ERROR", [], "", [str(e)]))

    # Returning visitor
    try:
        vid = str(uuid.uuid4())
        chat_init(client, visitor_id=vid, test_ip="10.0.0.20")
        time.sleep(1)
        init2 = chat_init(client, visitor_id=vid, test_ip="10.0.0.20")
        ret = init2.get("isReturning")
        results.append(
            CaseResult(
                "H3-returning",
                "PASS" if ret else "FAIL",
                [],
                (init2.get("openingMessage") or "")[:200],
                [f"isReturning={ret}"],
            )
        )
    except Exception as e:
        results.append(CaseResult("H3-returning", "ERROR", [], "", [str(e)]))

    # Clear chat
    try:
        d = chat_init(client, test_ip="10.0.0.21")
        sid = d["sessionId"]
        vid = d["visitorId"]
        r = client.post(
            f"{BASE}/api/chat-clear",
            json={
                "session_id": sid,
                "visitor_id": vid,
                "page_context": {"url": "http://127.0.0.1:8000/advisor"},
            },
            headers={"X-Forwarded-For": "10.0.0.21"},
            timeout=15,
        )
        body = r.json()
        ok = body.get("cleared") and body.get("sessionId") != sid
        results.append(
            CaseResult(
                "H2-clear",
                "PASS" if ok else "FAIL",
                [],
                json.dumps(body)[:150],
                ["new session after clear"],
            )
        )
    except Exception as e:
        results.append(CaseResult("H2-clear", "ERROR", [], "", [str(e)]))

    return results


def run_thread(
    client: httpx.Client,
    thread: ChatThread,
    test_ip: str,
    *,
    rate_limit_wait_s: int = 90,
    rate_limit_retries: int = 3,
) -> list[CaseResult]:
    results: list[CaseResult] = []
    print(f"\n=== Thread {thread.name} ({test_ip}) ===")
    init = chat_init(client, thread.page_url, thread.product_id, test_ip=test_ip)
    session_id = init["sessionId"]
    visitor_id = init["visitorId"]

    if thread.name == "B-ECG":
        opening = init.get("openingMessage") or ""
        ok = "ecg" in opening.lower() or "scanned" in opening.lower()
        results.append(
            CaseResult(
                "B1",
                "PASS" if ok else "PARTIAL",
                [],
                opening[:200],
                ["opening ECG context"],
            )
        )

    for case in thread.cases:
        print(f"  {case['id']}: {case['msg'][:50]}…")
        time.sleep(DELAY_S)
        try:
            result: CaseResult | None = None
            for attempt in range(rate_limit_retries + 1):
                events, text, status = parse_sse_chat(
                    client,
                    session_id,
                    case["msg"],
                    visitor_id,
                    thread.page_url,
                    thread.product_id,
                    test_ip,
                )
                result = evaluate_case(case, events, text, status)
                if result.status != "ERROR" or not is_rate_limit_error(events, result.notes):
                    break
                if attempt < rate_limit_retries:
                    print(
                        f"    rate limited — waiting {rate_limit_wait_s}s "
                        f"(retry {attempt + 1}/{rate_limit_retries})"
                    )
                    time.sleep(rate_limit_wait_s)
            assert result is not None
            results.append(result)
        except Exception as e:
            results.append(CaseResult(case["id"], "ERROR", [], "", [str(e)]))
        print(f"    -> {results[-1].status} tools={results[-1].tools_seen}")

    return results


def write_report(all_results: list[CaseResult], path: Path) -> None:
    passed = sum(1 for r in all_results if r.status == "PASS")
    partial = sum(1 for r in all_results if r.status == "PARTIAL")
    failed = sum(1 for r in all_results if r.status in ("FAIL", "ERROR"))
    total = len(all_results)

    lines = [
        "# Boolmind Advisor — Automated Test Run Results",
        "",
        f"**Run time:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Base URL:** {BASE}",
        f"**Delay between messages:** {DELAY_S}s (Groq rate-limit mitigation)",
        "",
        "## Executive summary",
        "",
        f"| Metric | Count |",
        f"|--------|-------|",
        f"| Total cases | {total} |",
        f"| PASS | {passed} |",
        f"| PARTIAL | {partial} |",
        f"| FAIL / ERROR | {failed} |",
        f"| **Pass rate (strict)** | {100*passed/total:.0f}% |" if total else "",
        f"| **Pass rate (incl. partial)** | {100*(passed+partial)/total:.0f}% |" if total else "",
        "",
        "### Production readiness (honest assessment)",
        "",
    ]

    # Integration flags from settings
    lines.extend(
        [
            "| Integration | Configured |",
            "|-------------|------------|",
            f"| Groq | {settings.groq_configured} |",
            f"| Pinecone | {settings.pinecone_configured} |",
            f"| Redis | {settings.upstash_configured} |",
            f"| HubSpot | {settings.hubspot_configured} |",
            f"| Cal.com | {settings.calcom_configured} |",
            f"| Resend | {settings.resend_configured} |",
            f"| Supabase | {settings.supabase_configured} |",
            f"| HMAC (`CHAT_API_SECRET`) | {bool(settings.chat_api_secret)} |",
            "",
            "## Detailed results",
            "",
            "| ID | Status | Tools seen | Notes |",
            "|----|--------|------------|-------|",
        ]
    )

    for r in all_results:
        notes = "; ".join(r.notes)[:120]
        tools = ", ".join(r.tools_seen) or "—"
        lines.append(f"| {r.test_id} | **{r.status}** | {tools} | {notes} |")

    lines.extend(["", "## Response excerpts (failures / partials)", ""])
    for r in all_results:
        if r.status not in ("FAIL", "PARTIAL", "ERROR"):
            continue
        lines.append(f"### {r.test_id} ({r.status})")
        lines.append(f"Tools: `{', '.join(r.tools_seen) or 'none'}`")
        lines.append(f"```\n{r.assistant_excerpt}\n```\n")

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written: {path}")


def _resolve_thread(name: str) -> ChatThread | None:
    key = name.strip().upper()
    for t in THREADS:
        if t.name.upper() == key or t.name.upper().startswith(key):
            return t
    return None


def main() -> int:
    import argparse

    global DELAY_S
    parser = argparse.ArgumentParser(description="Run advisor manual test plan")
    parser.add_argument(
        "--thread",
        help="Run one thread only (e.g. D, A, B, D-Technical-Retify)",
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=DELAY_S,
        help="Seconds between chat messages (default 12)",
    )
    parser.add_argument(
        "--infra",
        action="store_true",
        help="Also run infrastructure checks (chat-init, clear, etc.)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Report output path",
    )
    parser.add_argument(
        "--rate-limit-wait",
        type=int,
        default=90,
        help="Seconds to wait before retrying after Groq RATE_LIMIT (default 90)",
    )
    parser.add_argument(
        "--rate-limit-retries",
        type=int,
        default=3,
        help="Max retries per message when rate limited (default 3)",
    )
    args = parser.parse_args()
    DELAY_S = max(args.delay, 5)

    print(f"Testing {BASE} … (delay={DELAY_S}s)")
    try:
        httpx.get(f"{BASE}/health", timeout=5).raise_for_status()
    except Exception as e:
        print(f"ERROR: Server not reachable at {BASE}: {e}")
        print("Start: uvicorn main:app --reload")
        return 1

    all_results: list[CaseResult] = []
    with httpx.Client() as client:
        health = client.get(f"{BASE}/health", timeout=10).json()
        all_results.append(
            CaseResult(
                "INFRA-health",
                "PASS" if health.get("advisor_tier_a_ready") else "FAIL",
                [],
                json.dumps(health)[:200],
                [f"pool={health.get('groq_key_pool_size')}"],
            )
        )

        if args.thread:
            thread = _resolve_thread(args.thread)
            if thread is None:
                print(f"Unknown thread: {args.thread}")
                print("Available:", ", ".join(t.name for t in THREADS))
                return 1
            if args.infra:
                all_results.extend(run_infrastructure(client))
            all_results.extend(
                run_thread(
                    client,
                    thread,
                    "10.0.2.100",
                    rate_limit_wait_s=args.rate_limit_wait,
                    rate_limit_retries=args.rate_limit_retries,
                )
            )
        else:
            if args.infra:
                all_results.extend(run_infrastructure(client))
            for i, thread in enumerate(THREADS):
                try:
                    all_results.extend(
                        run_thread(
                            client,
                            thread,
                            f"10.0.1.{i + 1}",
                            rate_limit_wait_s=args.rate_limit_wait,
                            rate_limit_retries=args.rate_limit_retries,
                        )
                    )
                except Exception as e:
                    print(f"Thread {thread.name} aborted: {e}")

    if args.output:
        report_path = args.output
    elif args.thread:
        slug = args.thread.replace("-", "").lower()[:20]
        report_path = ROOT / "docs" / f"advisor-test-results-thread-{slug}.md"
    else:
        report_path = ROOT / "docs" / "advisor-test-results.md"
    write_report(all_results, report_path)

    passed = sum(1 for r in all_results if r.status == "PASS")
    total = len(all_results)
    print(f"\nDone: {passed}/{total} PASS -> {report_path}")
    return 0 if passed >= total * 0.7 else 1


if __name__ == "__main__":
    raise SystemExit(main())
