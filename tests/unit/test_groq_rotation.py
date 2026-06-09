"""Groq API key pool tests."""

import os
from unittest.mock import patch

from app.advisor.integrations.groq_llm import GroqKeyRotator, reset_groq_rotator
from app.core.config import settings


def test_get_groq_api_keys_dedupes() -> None:
    from app.core.config import Settings

    s = Settings(
        _env_file=None,
        groq_api_key="key-primary",
        groq_api_key_1="key-one",
        groq_api_key_2="key-primary",
        groq_api_key_3="",
    )
    keys = s.get_groq_api_keys()
    assert keys[0] == "key-primary"
    assert "key-one" in keys
    assert keys.count("key-primary") == 1


def test_pool_keys_only_without_primary() -> None:
    from app.core.config import Settings

    s = Settings(
        _env_file=None,
        groq_api_key="",
        groq_api_key_1="k1",
        groq_api_key_2="k2",
    )
    keys = s.get_groq_api_keys()
    assert keys == ["k1", "k2"]
    assert s.groq_configured is True


def test_rotator_round_robin() -> None:
    rotator = GroqKeyRotator(["a", "b", "c"])
    assert rotator.next_key() == "a"
    assert rotator.next_key() == "b"
    assert rotator.next_key() == "c"
    assert rotator.next_key() == "a"


def test_groq_key_pool_size_caps_numbered_keys() -> None:
    from app.core.config import Settings

    s = Settings(
        _env_file=None,
        groq_api_key="",
        groq_api_key_1="k1",
        groq_api_key_2="k2",
        groq_api_key_3="k3",
        groq_api_key_4="k4",
        groq_api_key_5="k5",
        groq_key_pool_size=5,
    )
    assert s.get_groq_api_keys() == ["k1", "k2", "k3", "k4", "k5"]


def test_groq_key_pool_size_three_ignores_four_and_five() -> None:
    from app.core.config import Settings

    s = Settings(
        _env_file=None,
        groq_api_key_1="k1",
        groq_api_key_2="k2",
        groq_api_key_3="k3",
        groq_api_key_4="k4",
        groq_api_key_5="k5",
        groq_key_pool_size=3,
    )
    assert s.get_groq_api_keys() == ["k1", "k2", "k3"]


def test_reset_rotator() -> None:
    reset_groq_rotator()
