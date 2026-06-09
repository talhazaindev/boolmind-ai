"""Playwright E2E smoke (optional — requires running server)."""

import pytest

pytest.importorskip("playwright")

pytestmark = pytest.mark.skip(reason="Run manually: pytest tests/e2e -m e2e with server on :8000")


@pytest.mark.e2e
def test_advisor_page_title() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto("http://127.0.0.1:8000/advisor")
        assert "Boolmind Advisor" in page.title()
        browser.close()
