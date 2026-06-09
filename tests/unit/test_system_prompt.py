"""System prompt tests."""

from app.advisor.orchestrator.product_context import ProductContext
from app.advisor.orchestrator.system_prompt import (
    SystemPromptContext,
    build_discovery_section,
    build_system_prompt,
    count_prompt_tokens,
)
from app.advisor.types import PageContext, ReadinessFlags, SessionMetadata, TurnEvaluation


def test_build_system_prompt_always_sections() -> None:
    prompt = build_system_prompt(
        SystemPromptContext(page_context=PageContext(title="Home", url="https://boolmind.ai/"))
    )
    assert "Boolmind.AI Advisor" in prompt
    assert "HARD RULES" in prompt
    assert "rag_query" in prompt
    assert "EXPLORE" in prompt
    assert "CONVERSATIONAL DISCOVERY" in prompt
    assert "ADVISORY BEHAVIOR" in prompt
    assert "NEVER tell the user the knowledge base lacks information" in prompt


def test_build_system_prompt_product_page() -> None:
    prompt = build_system_prompt(
        SystemPromptContext(
            page_context=PageContext(
                title="Retify",
                url="https://boolmind.ai/products/retify",
                product_id="retify",
                product_name="Retify — Retail Data Unification",
            ),
            product_context=ProductContext(
                active_product="retify",
                active_product_name="Retify — Retail Data Unification",
                products_discussed=[],
                namespace="retify",
            ),
        )
    )
    assert "Retify" in prompt
    assert "primarily interested" in prompt


def test_build_discovery_section() -> None:
    section = build_discovery_section(
        SessionMetadata(
            industry="retail",
            pain_point="POS mess",
            stage_reached="QUALIFY",
        ),
        TurnEvaluation(
            stage="QUALIFY",
            missing_fields=["goals"],
            next_discovery_question="What outcome matters most?",
            readiness=ReadinessFlags(product_tour=False),
        ),
    )
    assert section is not None
    assert "DISCOVERY STATE" in section
    assert "industry=retail" in section
    assert "goals" in section


def test_token_count_under_1800() -> None:
    prompt = build_system_prompt(
        SystemPromptContext(
            page_context=PageContext(
                title="Retify",
                url="https://boolmind.ai/products/retify",
                product_id="retify",
            ),
            session_data=SessionMetadata(
                is_returning=True,
                visitor_name="Alex",
                last_topic="schema detection",
                products_discussed=["retify"],
                stage_reached="INTEREST",
                industry="retail",
                pain_point="fragmented data",
            ),
            discovery=TurnEvaluation(
                stage="INTEREST",
                missing_fields=["goals"],
                next_discovery_question="What would success look like?",
                readiness=ReadinessFlags(),
            ),
        )
    )
    assert count_prompt_tokens(prompt) < 1800
