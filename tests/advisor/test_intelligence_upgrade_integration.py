"""
Integration smoke tests for the intelligence upgrade layers.

These tests use mock session state — no live Pinecone or Redis required.
"""

from __future__ import annotations

import json

import pytest

from app.advisor.knowledge.ontology_loader import _cosine_similarity, _load_archetypes
from app.advisor.knowledge.translation_map import get_outcome_framing
from app.advisor.pipeline.conversation_planner import ConversationPlanner
from app.advisor.pipeline.diagnostic_protocol import DiagnosticDepth, DiagnosticPhase, IssueTree
from app.advisor.pipeline.hypothesis_question_engine import select_hypothesis_question
from app.advisor.pipeline.turn_pipeline import TurnPipeline
from app.advisor.pipeline.types import TurnPipelineResult
from app.advisor.types import SessionMetadata


class TestOntologyLoader:
    def test_loads_all_archetypes(self) -> None:
        archetypes = _load_archetypes()
        assert len(archetypes) == 25

    def test_all_archetypes_have_discriminating_question(self) -> None:
        for arch in _load_archetypes():
            assert arch.discriminating_question, f"{arch.id} missing discriminating_question"
            assert len(arch.discriminating_question) > 30, f"{arch.id} question too short"
            generic_phrases = ["tell me more", "how are things", "what do you do"]
            for phrase in generic_phrases:
                assert phrase not in arch.discriminating_question.lower(), (
                    f"{arch.id} discriminating_question appears generic: "
                    f"{arch.discriminating_question}"
                )

    def test_cosine_similarity_identical_vectors(self) -> None:
        v = [1.0, 0.0, 0.5]
        assert abs(_cosine_similarity(v, v) - 1.0) < 0.001

    def test_cosine_similarity_zero_vector(self) -> None:
        assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


class TestDiagnosticDepth:
    def test_starts_at_zero(self) -> None:
        d = DiagnosticDepth()
        assert d.score == 0

    def test_solution_gated_below_60(self) -> None:
        d = DiagnosticDepth(score=59)
        assert d.solution_gated is True

    def test_solution_not_gated_at_60(self) -> None:
        d = DiagnosticDepth(score=60)
        assert d.solution_gated is False

    def test_lead_capture_gated_below_40(self) -> None:
        d = DiagnosticDepth(score=39)
        assert d.lead_capture_gated is True

    def test_score_capped_at_100(self) -> None:
        d = DiagnosticDepth(score=95)
        d.add_root_cause_confirmed()
        assert d.score == 100

    def test_phase_progression(self) -> None:
        d = DiagnosticDepth(score=0)
        assert d.phase == DiagnosticPhase.PROBLEM_IDENTIFICATION
        d.score = 45
        assert d.phase == DiagnosticPhase.ROOT_CAUSE_HYPOTHESIS
        d.score = 90
        assert d.phase == DiagnosticPhase.SOLUTION_READINESS


class TestHypothesisQuestionEngine:
    def test_no_archetypes_returns_discovery_question(self) -> None:
        d = DiagnosticDepth(score=5)
        q = select_hypothesis_question([], IssueTree(), d, set())
        assert q is not None
        assert len(q) > 20

    def test_single_archetype_returns_discriminating_question(self) -> None:
        archetypes = _load_archetypes()
        lead_leakage = next(a for a in archetypes if a.id == "lead_leakage")
        d = DiagnosticDepth(score=15)
        q = select_hypothesis_question([(0.72, lead_leakage)], IssueTree(), d, set())
        assert q == lead_leakage.discriminating_question

    def test_already_asked_skips_to_next(self) -> None:
        from app.advisor.pipeline.question_ledger import normalize_question_fingerprint

        archetypes = _load_archetypes()
        lead_leakage = next(a for a in archetypes if a.id == "lead_leakage")
        d = DiagnosticDepth(score=15)
        already_asked = {
            normalize_question_fingerprint(lead_leakage.discriminating_question)
        }
        q = select_hypothesis_question(
            [(0.72, lead_leakage)], IssueTree(), d, already_asked
        )
        assert q != lead_leakage.discriminating_question or q is None


class TestConversationPlanner:
    def test_early_turns_force_discovery(self) -> None:
        planner = ConversationPlanner()
        session = SessionMetadata(message_count=2)
        d = DiagnosticDepth(score=5)
        plan = planner.plan(session, d, [], message_count=2)
        assert plan.force_discovery_mode is True
        assert plan.allow_solution_hint is False

    def test_late_turn_with_depth_allows_solution(self) -> None:
        planner = ConversationPlanner()
        session = SessionMetadata(
            industry="retail",
            data_context="15 employees",
            pain_point="stockouts",
            message_count=9,
        )
        d = DiagnosticDepth(score=70)
        plan = planner.plan(session, d, [], message_count=9)
        assert plan.allow_solution_hint is True
        assert plan.force_discovery_mode is False

    def test_identifies_vertical_gap(self) -> None:
        planner = ConversationPlanner()
        session = SessionMetadata()
        d = DiagnosticDepth(score=0)
        plan = planner.plan(session, d, [], message_count=1)
        assert plan.this_turn_priority == "identify_vertical"


class TestTranslationMap:
    def test_returns_framing_for_known_lever(self) -> None:
        framing = get_outcome_framing("crm_implementation")
        assert "pain_frame" in framing
        assert "solution_frame" in framing
        assert "avoid_terms" in framing
        assert "use_instead" in framing

    def test_returns_empty_for_unknown_lever(self) -> None:
        framing = get_outcome_framing("nonexistent_lever_xyz")
        assert framing == {}

    def test_avoid_terms_are_it_jargon(self) -> None:
        framing = get_outcome_framing("bi_dashboard")
        assert "BI" in framing["avoid_terms"]


class TestTurnPipelineResultSerialization:
    def test_model_dump_json_roundtrip(self) -> None:
        import app.advisor.knowledge.ontology_loader as loader_mod
        from unittest.mock import patch

        def _fake_embed(text: str) -> list[float]:
            seed = sum(ord(c) for c in text) % 1000
            return [float((seed + i) % 97) / 97.0 for i in range(8)]

        loader_mod._cache_loaded = False
        loader_mod._archetypes = []
        loader_mod._archetype_embeddings = []

        with patch("app.advisor.knowledge.ontology_loader.embed_query", side_effect=_fake_embed):
            result = TurnPipeline.run(
                SessionMetadata(message_count=1),
                "we lose track of new leads every week",
                [],
            )

        assert isinstance(result, TurnPipelineResult)
        payload = json.loads(result.model_dump_json())
        assert "diagnostic_depth" in payload
        assert "matched_archetype_ids" in payload
        assert "issue_tree_snapshot" in payload
        assert isinstance(payload["issue_tree_snapshot"], dict)
