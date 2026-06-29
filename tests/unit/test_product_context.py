"""Product context resolution tests."""

from app.advisor.orchestrator.product_context import (
    detect_product_in_message,
    product_id_from_url,
    resolve_product_context,
)
from app.advisor.types import PageContext, SessionMetadata


def test_product_id_from_url_retify() -> None:
    pid, _ = product_id_from_url("https://boolmind.ai/products/retify")
    assert pid == "retify"


def test_detect_product_ecg() -> None:
    assert detect_product_in_message("We process holter ECG PDFs daily") == "ecg"


def test_resolve_priority_page_over_session() -> None:
    ctx = resolve_product_context(
        PageContext(url="https://boolmind.ai/products/retify", product_id="retify"),
        SessionMetadata(active_product="legal", products_discussed=["legal"]),
        message="hello",
    )
    assert ctx.active_product == "retify"
    assert ctx.namespace == "retify"


def test_resolve_general_default() -> None:
    ctx = resolve_product_context(
        PageContext(url="https://boolmind.ai/"),
        None,
        "hello",
    )
    assert ctx.active_product is None
    assert ctx.namespace == "general"
