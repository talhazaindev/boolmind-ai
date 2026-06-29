"""Response guard tests."""

from app.advisor.orchestrator.response_guards import (
    asks_for_contact,
    has_repeated_content,
)


def test_detects_email_ask() -> None:
    assert asks_for_contact("Can you share your name and email address?") is True


def test_no_contact_ask_in_advice() -> None:
    assert asks_for_contact("I recommend starting with a Boolmind-scoped landing page.") is False


def test_detects_repeated_content() -> None:
    prev = "A simple website can be a good starting point. What are your goals?"
    cur = "A simple website can be a good starting point. Tell me about enrollment."
    assert has_repeated_content(cur, prev) is True


def test_no_false_positive_on_short_responses() -> None:
    assert has_repeated_content("Sure.", "Hello there.") is False
