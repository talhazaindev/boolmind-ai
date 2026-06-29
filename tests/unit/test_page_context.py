"""Page context and opening message tests."""

from app.advisor.orchestrator.page_context import (
    opening_message_for_page,
    page_mode_from_url,
    product_id_from_url,
)
from app.advisor.types import PageContext


def test_compare_page_mode() -> None:
    assert page_mode_from_url("https://boolmind.ai/compare") == "compare"


def test_product_id_ecg_url() -> None:
    pid, name = product_id_from_url("https://boolmind.ai/products/ecg")
    assert pid == "ecg"
    assert "ECG" in (name or "")


def test_opening_compare_page() -> None:
    msg = opening_message_for_page(
        PageContext(url="https://boolmind.ai/compare", title="Compare"),
    )
    assert msg is not None
    assert "comparison" in msg.lower()
