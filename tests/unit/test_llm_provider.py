"""LLM provider factory tests."""

from unittest.mock import patch

import pytest

from app.advisor.integrations.groq_llm import (
    GroqKeyRotator,
    OllamaChatClient,
    get_chat_llm_client,
    reset_groq_rotator,
)
from app.core.config import Settings


def test_llm_configured_ollama_without_groq_key() -> None:
    s = Settings(
        _env_file=None,
        llm_provider="ollama",
        ollama_base_url="http://localhost:11434/v1",
        ollama_model="qwen3:14b",
        groq_api_key="",
    )
    assert s.llm_configured is True
    assert s.groq_configured is False
    assert s.llm_model_resolved == "qwen3:14b"


def test_llm_configured_groq_requires_key() -> None:
    s = Settings(_env_file=None, llm_provider="groq", groq_api_key="")
    assert s.llm_configured is False


def test_get_chat_llm_client_ollama() -> None:
    reset_groq_rotator()
    with patch("app.advisor.integrations.groq_llm.settings") as mock_settings:
        mock_settings.llm_provider_resolved = "ollama"
        mock_settings.ollama_base_url = "http://localhost:11434/v1"
        mock_settings.ollama_model = "qwen3:14b"
        client = get_chat_llm_client()
    assert isinstance(client, OllamaChatClient)
    reset_groq_rotator()


def test_get_chat_llm_client_groq() -> None:
    reset_groq_rotator()
    with patch("app.advisor.integrations.groq_llm.settings") as mock_settings:
        mock_settings.llm_provider_resolved = "groq"
        mock_settings.get_groq_api_keys.return_value = ["test-key"]
        mock_settings.llm_model_resolved = "llama-3.3-70b-versatile"
        mock_settings.llm_eval_model_resolved = "llama-3.3-70b-versatile"
        client = get_chat_llm_client()
    assert isinstance(client, GroqKeyRotator)
    reset_groq_rotator()


def test_unsupported_llm_provider_raises() -> None:
    reset_groq_rotator()
    with patch("app.advisor.integrations.groq_llm.settings") as mock_settings:
        mock_settings.llm_provider_resolved = "unknown"
        mock_settings.llm_provider = "unknown"
        with pytest.raises(ValueError, match="Unsupported LLM_PROVIDER"):
            get_chat_llm_client()
    reset_groq_rotator()
