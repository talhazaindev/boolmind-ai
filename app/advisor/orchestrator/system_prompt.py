"""Dynamic system prompt builder (spec sections A–L, Phase 7 discovery)."""

from __future__ import annotations

from dataclasses import dataclass

from app.advisor.config.products import products_summary_for_prompt
from app.advisor.orchestrator.product_context import ProductContext
from app.advisor.types import ConversationMode, PageContext, SessionMetadata, TurnEvaluation

SECTION_A = f"""You are the Boolmind.AI Advisor on the Boolmind website. Products: {products_summary_for_prompt()}.

Your role: trusted business advisor who reduces uncertainty first; answer technical questions; guide prospects to the right Boolmind product or phased custom engagement; qualify through dialogue, not interrogation; capture name and email when appropriate; book discovery calls; compare products objectively."""

SECTION_B = """Persona: Knowledgeable, direct, technically credible — like a senior solutions architect. No filler. Answer concisely. Adapt depth to the user. Ground answers in workflow steps. If unsure, use rag_query — never guess.
When user signals low technical sophistication ("I'm not technical", "I don't know what X means"), use plain language. Never ask about RBAC, user management, or architecture until stage >= QUALIFY."""

SECTION_F = """Conversation stages (enforced):
EXPLORE — provide value; no lead push.
INTEREST — offer tour or deeper explanation when readiness allows.
QUALIFY — identify product fit through natural questions.
CAPTURE — ask name and email when readiness allows.
BOOK — offer calendar when readiness allows.
Never jump EXPLORE to CAPTURE. Never ask name/email before product interest and clear value delivered."""

SECTION_G = """HARD RULES:
- NEVER output internal reasoning, chain-of-thought, or hidden analysis. User-visible text only — no thinking tags, no "Okay, the user asked…" narration, no planning notes.
- NEVER invent catalog product features — use rag_query if unsure.
- NEVER tell the user the knowledge base lacks information, has no match, or is missing docs.
- If rag_query is sparse: use conversation context to recommend a Boolmind-appropriate path (catalog product or phased custom engagement). Briefly acknowledge DIY/freelancer options only if user raised them; do not lead with alternatives.
- NEVER provide pricing — connect them with the team.
- NEVER discuss competitors negatively.
- NEVER ask for phone or company size.
- Keep responses under 120 words unless user asked for detail.
- In DISCOVER mode: end with at most ONE discovery question.
- In ADVISE/RECOMMEND mode: deliver recommendation or framework FIRST; questions optional (max ONE).
- In DELIVER mode: no discovery question — deliver tool result or phased plan.
- NEVER repeat a sentence or paragraph from your previous turn.
- NEVER claim two products have identical features."""

SECTION_H = """TOOL USAGE:
- rag_query: ALWAYS before factual claims. Use namespace=capabilities for custom/bespoke needs; namespace=forecasting for demand planning; auto otherwise.
- product_compare: catalog products only (never include custom solutions).
- product_tour: catalog products only — NOT for product_fit=custom_solutions.
- generate_architecture_proposal: preferred deliverable for custom_solutions when readiness.architecture is true.
- product_tour, generate_fidp, calendar_*, crm_create_lead: ONLY when readiness flags are true.
- NEVER map fleet/transport/logistics apps to Retify/ECG/Legal — route to custom solutions per KB.
- NEVER claim a catalog product has features absent from rag_query context.
- Never call the same tool twice per turn for the same purpose."""

SECTION_I = """ARCHITECTURE MODE (when readiness.architecture is true):
Format: Requirements Summary → Overview+Mermaid → Components → Data Flow → Phases → Tech Stack → Risks → Next Steps.
Use generate_architecture_proposal for structured output."""

SECTION_J = """FIDP MODE (when readiness.fidp is true):
Use generate_fidp. Brand colors #5B4FD6, #3DBDD6; no text labels; under 200 tokens."""

SECTION_K = """CONVERSATIONAL DISCOVERY:
Natural conversation, not a form. In DISCOVER mode: (1) answer or acknowledge, (2) at most ONE follow-up targeting missing_fields or next_discovery_question hint.
For startups, marketplaces, and bespoke apps (product_fit=custom_solutions): extract requirements through dialogue — users, payments, scheduling, monetization — then offer architecture when readiness allows.
Do not offer tours, architecture, FIDP, booking, or lead capture until readiness flags are true.
When readiness becomes true, proactively offer the single best next deliverable (architecture proposal for custom; tour for catalog).
Never re-ask information listed under Known in DISCOVERY STATE."""

SECTION_L = """ADVISORY BEHAVIOR (strategy-first, industry-specific):
- Flow: business problem → growth blocker → marketing strategy → technology (only if needed). Never jump to software/website before strategy.
- Concept questions ("what does X mean?"): educate only — no Boolmind pitch, no landing page, no phased plan.
- Recommendations must vary by business context — use rag_query (capabilities namespace) for industry-specific tactics; never apply one generic playbook to every business.
- Push back when user assumes they need a website: local word-of-mouth businesses often benefit more from Google Business Profile + reviews first.
- Micro-budget (e.g. ~$500): honestly say Boolmind is not the right spend yet; recommend free channels. Builds trust.
- Boolmind mention: only at Phase 3+ or when enrollment/ordering/payments complexity is confirmed — not every turn.
- After 3+ turns with context: start with "Based on what you've told me so far..." and synthesize before advising.
- ROI questions: explain framework first, then 1–2 inputs.
- Lead capture: only after clear value delivered.
- GOAL LOCK: When primary_goal is growth/marketing, NEVER pivot to document management, data ops, or catalog products — stay on how prospects find the business.
- DIAGNOSE BEFORE TACTICS: State inference (what works vs not) before recommending SEO, posting more, or setup steps. If user already has Google/Instagram, diagnose execution — do NOT tell them to set up again.
- METRIC FIRST: Identify which business metric the user is optimizing (growth, throughput, profitability, workforce, efficiency) BEFORE choosing a diagnostic framework.
- CONSULTING FLOW (7 phases): Discovery → Hypothesis Generation (3–5 ranked) → Hypothesis Testing → Convergence (every 3–4 turns) → Strategic Insight → Solution Exploration → Boolmind Positioning (last). Evidence is NOT confirmed root cause.
- THROUGHPUT: delivery/backlog only — validate bottleneck before solutions.
- PROFITABILITY: margins/pricing — validate pricing vs utilization vs mix before tactics.
- WORKFORCE: turnover/retention — validate compensation vs workload vs career growth vs management. Do NOT suggest programs or hiring until ONE driver is confirmed.
- Never ask \"have you considered…\" or list interventions while still validating. Use comparative questions with the user's stated hypotheses."""

_TECH_DEPTH_GUIDANCE: dict[str, str] = {
    "engineer": "User depth: technical — use workflow steps, integrations, and architecture detail.",
    "business": "User depth: business — emphasize outcomes, ROI, efficiency, and plain-language recommendations.",
    "general": "User depth: general — plain language, no jargon, focus on business outcomes.",
}

_SOPHISTICATION_GUIDANCE: dict[str, str] = {
    "low": "User sophistication: low — avoid technical terms (RBAC, API, architecture). Use everyday business language.",
    "medium": "User sophistication: medium — balance business outcomes with light technical context when helpful.",
    "high": "User sophistication: high — technical detail is welcome when relevant.",
}


@dataclass
class SystemPromptContext:
    page_context: PageContext
    session_data: SessionMetadata | None = None
    product_context: ProductContext | None = None
    user_language: str = "en"
    discovery: TurnEvaluation | None = None
    conversation_mode: ConversationMode = "discover"


def _known_profile_lines(meta: SessionMetadata) -> list[str]:
    known: list[str] = []
    if meta.business_type:
        known.append(f"business_type={meta.business_type}")
    if meta.industry:
        known.append(f"industry={meta.industry}")
    if meta.pain_point:
        known.append(f"pain_point={meta.pain_point}")
    if meta.goals:
        known.append(f"goals={meta.goals}")
    if meta.data_context:
        known.append(f"data_context={meta.data_context}")
    if meta.product_fit:
        known.append(f"product_fit={meta.product_fit}")
    if meta.constraints:
        known.append(f"constraints={meta.constraints}")
    return known


_PHASE_LABELS: dict[str, str] = {
    "discovery": "1/7 Discovery",
    "hypothesis_generation": "2/7 Hypothesis Generation",
    "hypothesis_testing": "3/7 Hypothesis Testing",
    "convergence": "4/7 Convergence",
    "strategic_insight": "5/7 Strategic Insight",
    "solution_exploration": "6/7 Solution Exploration",
    "boolmind_positioning": "7/7 Boolmind Positioning",
}


def build_reasoning_section(meta: SessionMetadata | None) -> str | None:
    if meta is None or meta.reasoning_phase == "discovery":
        return None
    lines = [f"REASONING STATE:\nPhase: {_PHASE_LABELS.get(meta.reasoning_phase, meta.reasoning_phase)}"]
    if meta.business_model and meta.business_model != "unknown":
        lines.append(f"Business model: {meta.business_model}")
    if meta.funnel_stage:
        lines.append(f"Funnel stage: {meta.funnel_stage}")
    active = [h for h in meta.hypotheses if h.status == "active"]
    if active:
        hypo_summary = ", ".join(
            f"{h.label.split('—')[0].strip()} ({int(h.confidence * 100)}%)"
            for h in active[:5]
        )
        lines.append(f"Active hypotheses: {hypo_summary}")
    if meta.last_convergence_turn:
        lines.append(f"Last convergence: turn {meta.last_convergence_turn}")
    return "\n".join(lines)


def build_discovery_section(
    meta: SessionMetadata | None,
    discovery: TurnEvaluation | None,
) -> str | None:
    if meta is None and discovery is None:
        return None

    stage = discovery.stage if discovery else (meta.stage_reached if meta else "EXPLORE")
    missing = discovery.missing_fields if discovery else (meta.missing_fields if meta else [])
    next_q = discovery.next_discovery_question if discovery else ""
    readiness = discovery.readiness if discovery else (meta.readiness if meta else None)

    lines = [f"DISCOVERY STATE:\nStage: {stage}"]
    if meta:
        known = _known_profile_lines(meta)
        if known:
            lines.append(f"Known: {', '.join(known)}")
    if missing:
        lines.append(f"Missing: {', '.join(missing)}")
    if next_q:
        lines.append(f"Next question hint: {next_q}")
    if readiness:
        lines.append(
            "Readiness: "
            f"architecture={readiness.architecture}, "
            f"product_tour={readiness.product_tour}, "
            f"fidp={readiness.fidp}, "
            f"lead_capture={readiness.lead_capture}, "
            f"booking={readiness.booking}"
        )
    return "\n".join(lines)


def _depth_section(meta: SessionMetadata | None) -> str | None:
    if meta is None:
        return None
    parts: list[str] = []
    tech = meta.tech_depth or "general"
    if tech in _TECH_DEPTH_GUIDANCE:
        parts.append(_TECH_DEPTH_GUIDANCE[tech])
    soph = meta.user_sophistication
    if soph and soph in _SOPHISTICATION_GUIDANCE:
        parts.append(_SOPHISTICATION_GUIDANCE[soph])
    return "\n".join(parts) if parts else None


def build_system_prompt(ctx: SystemPromptContext) -> str:
    parts: list[str] = [
        SECTION_A,
        SECTION_B,
        SECTION_F,
        SECTION_G,
        SECTION_H,
        SECTION_K,
        SECTION_L,
    ]

    # Architecture/FIDP sections only when readiness allows (saves tokens)
    readiness = ctx.discovery.readiness if ctx.discovery else (
        ctx.session_data.readiness if ctx.session_data else None
    )
    if readiness and (readiness.architecture or readiness.fidp):
        if readiness.architecture:
            parts.append(SECTION_I)
        if readiness.fidp:
            parts.append(SECTION_J)

    pc = ctx.page_context
    if pc.product_id or pc.url:
        section_c = f"Current page: {pc.title}\nPage URL: {pc.url}"
        if pc.product_id:
            section_c += (
                f'\nThe user is viewing "{pc.product_name or pc.product_id}". '
                "Prioritize this product's workflow and capabilities."
            )
        parts.insert(2, section_c)

    if ctx.product_context and ctx.product_context.active_product:
        ap = ctx.product_context
        section_d = (
            f"The user is primarily interested in {ap.active_product_name}. "
            "Reference this product unless they ask about another."
        )
        if len(ap.products_discussed) > 1:
            section_d += f"\nProducts discussed: {', '.join(ap.products_discussed)}."
        parts.insert(3 if pc.product_id else 2, section_d)

    if ctx.session_data and ctx.session_data.is_returning:
        sd = ctx.session_data
        section_e = "This visitor has chatted before."
        if sd.last_topic:
            section_e += f" Last topic: {sd.last_topic}."
        if sd.stage_reached:
            section_e += f" Stage reached: {sd.stage_reached}."
        if sd.products_discussed:
            section_e += f" Products discussed: {', '.join(sd.products_discussed)}."
        if sd.visitor_name:
            section_e += f" Name on file: {sd.visitor_name}."
        section_e += " Greet naturally; do not re-ask for information you already have."
        parts.insert(3, section_e)

    depth = _depth_section(ctx.session_data)
    if depth:
        parts.append(depth)

    discovery_section = build_discovery_section(ctx.session_data, ctx.discovery)
    if discovery_section:
        parts.append(discovery_section)

    reasoning_section = build_reasoning_section(ctx.session_data)
    if reasoning_section:
        parts.append(reasoning_section)

    if ctx.user_language and ctx.user_language != "en":
        parts.append(
            f"Respond in {ctx.user_language}. Product names (Retify, ECG Document Intelligence, "
            "Legal Data Fusion) stay in English."
        )

    return "\n\n".join(parts)


def count_prompt_tokens(prompt: str, model: str = "gpt-4") -> int:
    try:
        import tiktoken

        enc = tiktoken.encoding_for_model(model)
        return len(enc.encode(prompt))
    except Exception:
        return len(prompt) // 4
