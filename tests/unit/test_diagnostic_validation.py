"""Shared validation gate — evidence is not confirmation."""

from app.advisor.orchestrator.diagnostic_validation import hypotheses_need_validation


def test_multiple_hypotheses_always_need_validation() -> None:
    assert hypotheses_need_validation(
        ["workload", "career_growth"],
        "feedback suggests both",
        [],
        None,
    ) is True


def test_confirmed_single_hypothesis_exits_validation() -> None:
    assert hypotheses_need_validation(
        ["workload"],
        "the main reason is workload during peak periods",
        [],
        "workload",
    ) is False
