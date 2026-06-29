"""Tests for IT-to-business translation map."""

from __future__ import annotations

import pytest

from app.advisor.knowledge.translation_map import get_outcome_framing


def test_get_outcome_framing_crm_implementation_returns_full_dict() -> None:
    framing = get_outcome_framing("crm_implementation")
    assert framing
    assert "pain_frame" in framing
    assert "solution_frame" in framing
    assert "avoid_terms" in framing
    assert "use_instead" in framing
    assert isinstance(framing["avoid_terms"], list)
    assert isinstance(framing["use_instead"], list)
    assert "CRM" in framing["avoid_terms"]


def test_get_outcome_framing_nonexistent_lever_returns_empty_dict() -> None:
    assert get_outcome_framing("nonexistent_lever") == {}


@pytest.mark.parametrize(
    "lever",
    [
        "workflow_automation_and_integration",
        "bi_dashboard",
        "crm_with_reporting",
        "inventory_management_system",
        "ai_chatbot_or_helpdesk",
        "field_ops_mobile_app",
        "document_ai",
        "lead_gen_website",
        "approval_workflow_automation",
    ],
)
def test_all_mapped_levers_have_required_keys(lever: str) -> None:
    framing = get_outcome_framing(lever)
    assert framing
    for key in ("pain_frame", "solution_frame", "avoid_terms", "use_instead"):
        assert key in framing
