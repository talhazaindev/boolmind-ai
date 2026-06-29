"""Proactive trigger rules."""

from app.advisor.proactive.rules import get_proactive_triggers
from app.advisor.types import PageContext


def test_product_page_has_scroll_trigger() -> None:
    triggers = get_proactive_triggers(
        PageContext(url="https://boolmind.ai/products/retify", product_id="retify"),
        is_returning=False,
    )
    ids = {t["id"] for t in triggers}
    assert "product_scroll_offer" in ids


def test_compare_page_has_dwell_trigger() -> None:
    triggers = get_proactive_triggers(
        PageContext(url="https://boolmind.ai/compare"),
        is_returning=False,
    )
    ids = {t["id"] for t in triggers}
    assert "compare_dwell" in ids
