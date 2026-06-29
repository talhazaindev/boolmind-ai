#!/usr/bin/env python3
"""Live execution-engine audit: multi-turn conversations + SSE telemetry."""

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
TURN_DELAY_S = 4
HEALTH_RETRIES = 30
HEALTH_RETRY_S = 5


def wait_for_health(client: httpx.Client) -> None:
    """Wait for API after container restart (embedding warmup can take minutes)."""
    last_err: Exception | None = None
    for attempt in range(1, HEALTH_RETRIES + 1):
        try:
            r = client.get(f"{BASE}/health", timeout=10.0)
            r.raise_for_status()
            return
        except (httpx.ConnectError, httpx.HTTPError) as e:
            last_err = e
            print(
                f"Health check {attempt}/{HEALTH_RETRIES} failed, retry in {HEALTH_RETRY_S}s...",
                file=sys.stderr,
            )
            time.sleep(HEALTH_RETRY_S)
    raise SystemExit(f"API not ready at {BASE}/health after {HEALTH_RETRIES} attempts: {last_err}")


@dataclass
class TurnResult:
    turn: int
    message: str
    http_status: int
    tools: list[str]
    tool_outcomes: list[dict[str, Any]]
    execution_mode: str | None
    internal_mode: str | None
    routing_confidence: float | None
    rag_status: str | None
    quality_passed: bool | None
    stage: str | None
    resolution_trace: list[str]
    router_decision: dict[str, Any] | None
    decision_trace: dict[str, Any] | None
    assistant_text: str
    flags: list[str] = field(default_factory=list)


@dataclass
class ScenarioResult:
    name: str
    turns: list[TurnResult] = field(default_factory=list)


def _sign_body(body: bytes, secret: str) -> dict[str, str]:
    ts = str(int(time.time()))
    sig = hmac.new(
        secret.encode(),
        f"{ts}.{body.decode('utf-8')}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return {"X-Chat-Timestamp": ts, "X-Chat-Signature": sig}


def chat_init(client: httpx.Client, test_ip: str) -> dict[str, Any]:
    r = client.post(
        f"{BASE}/api/chat-init",
        json={"page_context": {"title": "Execution Audit", "url": f"{BASE}/advisor"}},
        headers={"X-Forwarded-For": test_ip},
        timeout=30.0,
    )
    r.raise_for_status()
    return r.json()


def send_turn(
    client: httpx.Client,
    session_id: str,
    visitor_id: str | None,
    message: str,
    test_ip: str,
) -> TurnResult:
    payload = {
        "session_id": session_id,
        "message": message,
        "visitor_id": visitor_id,
        "user_language": "en",
        "page_context": {"title": "Audit", "url": f"{BASE}/advisor"},
    }
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "X-Forwarded-For": test_ip}
    if settings.chat_api_secret:
        headers.update(_sign_body(body, settings.chat_api_secret))

    events: list[dict[str, Any]] = []
    text_parts: list[str] = []
    status = 0
    with client.stream(
        "POST",
        f"{BASE}/api/chat",
        content=body,
        headers=headers,
        timeout=600.0,
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

    tools: list[str] = []
    tool_outcomes: list[dict[str, Any]] = []
    for e in events:
        if e.get("type") == "tool_start" and e.get("tool"):
            t = e["tool"]
            if t not in tools:
                tools.append(t)
        if e.get("type") == "tool_result":
            tool_outcomes.append(
                {
                    "tool": e.get("tool"),
                    "outcome": e.get("outcome"),
                    "duration_ms": e.get("duration_ms"),
                }
            )

    done = next((e for e in events if e.get("type") == "done"), {})
    assistant = "".join(text_parts)
    flags: list[str] = []

    lower = assistant.lower()
    solution_phrases = [
        "custom automation",
        "ai-driven",
        "we recommend building",
        "our solution would",
        "automation platform",
    ]
    if any(p in lower for p in solution_phrases):
        flags.append("PREMATURE_SOLUTIONING")

    if "observation:" in lower:
        flags.append("LEAKED_DIAGNOSE_LABELS")

    if re.search(r"^\s*\d+[\.)]\s", assistant, re.M):
        flags.append("GENERIC_CHECKLIST_QUESTION")

    if done.get("executionMode") == "DISCOVERY" and any(
        w in message.lower() for w in ("dispatch", "shipment", "manual", "spreadsheet")
    ):
        flags.append("STUCK_IN_DISCOVERY")

    trace = done.get("decisionTrace") or {}
    if trace.get("conflict_hold"):
        flags.append("CONFLICT_HOLD")

    if "driver receives which shipment" in assistant.lower():
        if "logistics" not in message.lower() and "dispatch" not in message.lower():
            flags.append("LOGISTICS_QUESTION_LEAK")

    return TurnResult(
        turn=0,
        message=message,
        http_status=status,
        tools=tools,
        tool_outcomes=tool_outcomes,
        execution_mode=done.get("executionMode"),
        internal_mode=done.get("conversationMode"),
        routing_confidence=done.get("routingConfidence"),
        rag_status=done.get("ragStatus"),
        quality_passed=done.get("qualityPassed"),
        stage=done.get("stage"),
    resolution_trace=done.get("resolutionTrace") or [],
    router_decision=done.get("routerDecision"),
    decision_trace=done.get("decisionTrace"),
    assistant_text=assistant,
        flags=flags,
    )


def _intelligence_flags(
    turn: TurnResult,
    prior_turns: list[TurnResult],
    user_message: str,
) -> list[str]:
    flags: list[str] = []
    trace = turn.decision_trace or {}
    qkey = trace.get("required_question_key")
    prior_keys = [
        t.decision_trace.get("required_question_key")
        for t in prior_turns
        if t.decision_trace
    ]
    if qkey and qkey in prior_keys:
        flags.append("REPEATED_QUESTION_TOPIC")

    appended = turn.assistant_text.split("\n\n")[-1] if turn.assistant_text else ""
    blob = " ".join(
        [user_message]
        + [t.message for t in prior_turns[-2:]]
    ).lower()
    words = {w for w in re.findall(r"[a-z]{5,}", blob)}
    if appended.endswith("?") and words:
        overlap = sum(1 for w in re.findall(r"[a-z]{5,}", appended.lower()) if w in words)
        if overlap >= 2:
            flags.append("CONTEXTUAL_QUESTION")
        elif turn.turn > 2:
            flags.append("CONTEXTUAL_QUESTION_WEAK")

    if trace.get("active_thread") and prior_turns:
        prev = prior_turns[-1].decision_trace or {}
        if prev.get("active_thread") == trace.get("active_thread"):
            flags.append("THREAD_CONTINUATION")

    hyp_ids = trace.get("top_hypothesis_ids") or []
    if hyp_ids and prior_turns:
        prev_h = (prior_turns[-1].decision_trace or {}).get("top_hypothesis_ids") or []
        if prev_h and hyp_ids != prev_h:
            flags.append("HYPOTHESIS_PROGRESSION")

    if "volume" in appended.lower() and "220" in blob:
        flags.append("REPEATED_SCALE_QUESTION")

    return flags


def run_scenario(
    client: httpx.Client, name: str, messages: list[str], scenario_idx: int
) -> ScenarioResult:
    test_ip = f"10.88.0.{scenario_idx + 1}"
    init = chat_init(client, test_ip)
    session_id = init["sessionId"]
    visitor_id = init.get("visitorId")
    result = ScenarioResult(name=name)
    for i, msg in enumerate(messages, 1):
        tr = send_turn(client, session_id, visitor_id, msg, test_ip)
        tr.turn = i
        tr.flags.extend(_intelligence_flags(tr, result.turns, msg))
        result.turns.append(tr)
        if i < len(messages):
            time.sleep(TURN_DELAY_S)
    return result


SCENARIOS: dict[str, list[str]] = {
    "logistics_bottleneck": [
        "We run a logistics company. Orders are growing but dispatch delays are getting worse.",
        "We dispatch around 1,500 shipments per day. Planning is done manually in spreadsheets by three coordinators. Drivers often wait 30–60 minutes during peak periods.",
        "What do you recommend?",
        "We are a manufacturing company with 40 employees.",
    ],
    "premature_solution_block": [
        "We have operational inefficiencies and want to improve efficiency.",
        "What do you recommend we should do?",
    ],
    "product_compare": [
        "What's the difference between Retify and your Forecasting Engine in terms of workflow and use case?",
    ],
    "rag_concept": [
        "What does demand planning actually mean in plain language?",
    ],
    "custom_architecture": [
        "We're building a two-sided marketplace for equipment rentals — bookings, payments, and vendor dashboards.",
        "Main pain is manual coordination between vendors and renters; we need to scale past 500 transactions per week.",
        "Goal is to automate intake, scheduling, and status tracking with a custom platform.",
        "We use Stripe for payments and need API integrations with our CRM.",
        "Can you design a system architecture for this? Include integrations and data flow.",
    ],
    "healthcare_compliance_bottleneck": [
        "We're a 200-bed regional hospital group. Patient intake still relies on fax, phone callbacks, and shared Excel trackers across three sites.",
        "We process about 400 referrals per day. Authorization checks are manual — staff copy data between our EHR (Epic) and payer portals. Average delay is 2–3 business days before a patient gets scheduled.",
        "Compliance is non-negotiable: HIPAA audit trail, role-based access, and no PHI in external tools. Budget is tight but leadership will fund something that cuts authorization turnaround.",
        "What do you think is actually causing the delay — people, process, or systems?",
        "If we were to fix one bottleneck first, what would you prioritize and why?",
    ],
    "saas_churn_onboarding": [
        "We're a B2B SaaS company — project management for construction firms. ~2,800 paying accounts, $4.2M ARR, mostly mid-market.",
        "Activation is the problem: only 38% of trials create a project in week one. CSMs manually onboard via Zoom; we can't scale that. Churn in month 2–3 is 11%.",
        "We use HubSpot CRM, Stripe billing, and Mixpanel. Product is React + Node on AWS. Sales wants faster time-to-value; engineering wants fewer one-off integrations.",
        "Compare what Boolmind could realistically help with versus what we should fix in-product first.",
        "What do you recommend — and what evidence would you need before proposing a custom build?",
    ],
    "partial_automation_logistics": [
        "Mid-size 3PL — we already have a TMS (MercuryGate) and GPS on trucks, but dispatch planning is still manual.",
        "About 900 shipments/day across two regions. Coordinators export TMS data to Excel, re-plan routes when drivers call in sick, then re-upload. Peak season adds 45–90 min driver idle time.",
        "We tried a route optimization plugin last year — adoption failed because coordinators didn't trust the black-box assignments.",
        "What bottleneck should we isolate first given we already have a TMS?",
        "What do you recommend?",
    ],
    "conflicting_priorities_manufacturing": [
        "Precision parts manufacturer — 120 employees, two plants. ERP is SAP B1. Production scheduling is spreadsheet-driven; shop floor uses paper travelers.",
        "Leadership wants 20% throughput increase this year but also cut overtime by 15%. Quality escapes rose 8% last quarter when we pushed volume.",
        "IT budget is $180k. Union is sensitive to surveillance. We cannot rip-and-replace SAP mid-year.",
        "Which constraint is binding — capacity, planning visibility, or change management?",
        "Can you outline a phased approach without committing to a full MES yet?",
    ],
    "lending_approval_bottleneck": [
        "We operate a regional commercial lending business. Loan applications have increased significantly over the last year, but approval turnaround times have gone from 3 days to nearly 9 days on average.",
        "We process around 220 loan applications per day. Initial intake is digital, but underwriting analysts manually gather supporting documents from email, verify financial statements, and enter data into our loan origination system. Compliance reviews are handled by a separate team and applications often sit in queues waiting for approval. We actually tried automating document collection last year. Adoption was poor because analysts said the system missed exceptions and they went back to email. Compliance reviews are completely manual and there is currently a backlog of about 600 applications.",
        "Mostly edge-case document types like partnership tax returns — standard statements were usually fine.",
    ],
    "rapid_context_switch": [
        "We run a food delivery marketplace in three cities — 12k orders/day, own fleet plus gig drivers.",
        "Actually wait — I'm also evaluating this for our separate B2B catering arm. Different ops: bulk orders, fixed routes, 48-hour lead times.",
        "For the marketplace side: dispatch is the pain. For catering: kitchen prep coordination and slot booking.",
        "Which context are you using right now — marketplace or catering?",
        "Focus on marketplace only. Drivers wait 25–40 minutes at peak; we use spreadsheets for surge planning.",
    ],
}


def print_report(results: list[ScenarioResult]) -> None:
    print("=" * 72)
    print("EXECUTION ENGINE LIVE AUDIT")
    print("=" * 72)
    for sc in results:
        print(f"\n### {sc.name}")
        for t in sc.turns:
            print(f"\n--- Turn {t.turn} ---")
            print(f"USER: {t.message[:120]}{'...' if len(t.message) > 120 else ''}")
            print(f"HTTP: {t.http_status} | mode: {t.execution_mode} | internal: {t.internal_mode}")
            print(f"tools: {t.tools or 'none'} | rag: {t.rag_status} | stage: {t.stage}")
            print(f"routing_conf: {t.routing_confidence} | quality_passed: {t.quality_passed}")
            if t.resolution_trace:
                print(f"resolution: {t.resolution_trace}")
            if t.tool_outcomes:
                print(f"tool_outcomes: {t.tool_outcomes}")
            if t.flags:
                print(f"FLAGS: {t.flags}")
            rd = t.router_decision
            if rd:
                print(
                    f"router: intent={rd.get('intent')} tool={rd.get('tool_selected')} "
                    f"rag_req={rd.get('rag_required')} gates={rd.get('confidence_gates_applied')}"
                )
            excerpt = t.assistant_text.replace("\n", " ")[:400]
            print(f"ASSISTANT: {excerpt}{'...' if len(t.assistant_text) > 400 else ''}")
    print("\n" + "=" * 72)


def main() -> int:
    names = sys.argv[1:] or list(SCENARIOS.keys())
    results: list[ScenarioResult] = []
    with httpx.Client() as client:
        wait_for_health(client)
        for idx, name in enumerate(names):
            if name not in SCENARIOS:
                print(f"Unknown scenario: {name}", file=sys.stderr)
                continue
            print(f"Running {name}...", file=sys.stderr)
            results.append(run_scenario(client, name, SCENARIOS[name], idx))
    print_report(results)
    out = ROOT / "scripts" / "execution_audit_report.json"
    out.write_text(
        json.dumps(
            [
                {
                    "name": sc.name,
                    "turns": [
                        {
                            "turn": t.turn,
                            "message": t.message,
                            "http_status": t.http_status,
                            "tools": t.tools,
                            "tool_outcomes": t.tool_outcomes,
                            "execution_mode": t.execution_mode,
                            "internal_mode": t.internal_mode,
                            "routing_confidence": t.routing_confidence,
                            "rag_status": t.rag_status,
                            "quality_passed": t.quality_passed,
                            "stage": t.stage,
                            "resolution_trace": t.resolution_trace,
                            "router_decision": t.router_decision,
                            "decision_trace": t.decision_trace,
                            "flags": t.flags,
                            "assistant_text": t.assistant_text,
                        }
                        for t in sc.turns
                    ],
                }
                for sc in results
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nWrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
