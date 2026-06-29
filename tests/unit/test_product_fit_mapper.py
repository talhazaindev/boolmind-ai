"""Product fit mapper tests."""

from app.advisor.orchestrator.product_fit_mapper import map_product_fit
from app.advisor.types import SessionMetadata


def test_logistics_not_forecasting() -> None:
    fit = map_product_fit(
        SessionMetadata(),
        "We have a logistics fleet with manual dispatch",
        [],
    )
    assert fit.catalog_product_fit != "forecasting"
    assert fit.solution_category == "custom_solutions"


def test_demand_planning_maps_forecasting() -> None:
    fit = map_product_fit(
        SessionMetadata(),
        "We need demand planning and inventory forecast for SKUs",
        [],
    )
    assert fit.catalog_product_fit == "forecasting"
    assert fit.catalog_reasons


def test_custom_without_catalog() -> None:
    fit = map_product_fit(
        SessionMetadata(),
        "We want a bespoke automation platform with AI workflow",
        [],
    )
    assert fit.catalog_product_fit is None
    assert fit.solution_category == "custom_solutions"
    assert fit.solution_reasons
