"""Namespace resolution tests."""

from app.advisor.rag.namespaces import resolve_namespace


def test_resolve_custom_solutions() -> None:
    ns = resolve_namespace("auto", None, product_fit="custom_solutions")
    assert ns == ["capabilities", "business_intelligence", "general"]


def test_resolve_forecasting() -> None:
    ns = resolve_namespace("auto", "forecasting", product_fit="forecasting")
    assert ns == ["forecasting"]


def test_resolve_all_includes_forecasting() -> None:
    ns = resolve_namespace("all", None)
    assert "forecasting" in ns
    assert "retify" in ns
    assert "custom_solutions" not in ns
