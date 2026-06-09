"""Custom complexity detection tests."""

from app.advisor.orchestrator.custom_complexity import is_custom_complexity_confirmed


def test_not_confirmed_with_single_signal() -> None:
    assert is_custom_complexity_confirmed("I want online enrollment") is False


def test_confirmed_with_multiple_signals() -> None:
    msg = "I need online enrollment with payment processing and scheduling"
    assert is_custom_complexity_confirmed(msg) is True


def test_confirmed_across_messages() -> None:
    assert is_custom_complexity_confirmed(
        "We need enrollment",
        "And payment integration for parents",
    ) is True
