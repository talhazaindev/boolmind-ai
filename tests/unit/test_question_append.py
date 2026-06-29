"""Question append tests."""

from app.advisor.orchestrator.question_append import finalize_response


def test_append_required_question() -> None:
    q = "Which step creates the most delay?"
    body = "Observation: manual dispatch.\nInference: planning bottleneck."
    out = finalize_response(body, q)
    assert out.endswith(q)


def test_no_duplicate_append() -> None:
    q = "Which step creates the most delay?"
    body = f"Analysis complete.\n\n{q}"
    assert finalize_response(body, q) == body


def test_strips_body_questions_when_appending() -> None:
    q = "Which workflow would you automate first?"
    body = (
        "You rely on manual processes.\n\n"
        "How do you track stock levels today — and how often do you run out?"
    )
    out = finalize_response(body, q)
    assert out.endswith(q)
    assert "track stock" not in out.lower()
    assert "manual processes" in out.lower()
