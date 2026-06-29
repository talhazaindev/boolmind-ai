"""Eval timeout provider tests."""

from app.advisor.constants import eval_timeout_ms_for_provider


def test_ollama_eval_timeout_is_extended() -> None:
    assert eval_timeout_ms_for_provider("ollama") == 60000


def test_groq_eval_timeout_default() -> None:
    assert eval_timeout_ms_for_provider("groq") == 2000
