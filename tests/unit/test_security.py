"""Security helpers tests."""

from app.advisor.security import sanitize_message


def test_sanitize_strips_html() -> None:
    assert "<script>" not in sanitize_message("Hello <b>world</b>")
    assert sanitize_message("  hi  ") == "hi"


def test_sanitize_truncates() -> None:
    long = "a" * 3000
    assert len(sanitize_message(long)) == 2000
