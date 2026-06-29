"""Product compare tool."""

from unittest.mock import patch

import pytest

from app.advisor.tools import product_compare


@pytest.mark.asyncio
async def test_product_compare_returns_rows() -> None:
    fake_context = "Retify has 10 workflow steps for retail unification."

    with patch(
        "app.advisor.tools.product_compare.retrieve",
        return_value=fake_context,
    ):
        result = await product_compare.handle(
            {"product_ids": ["retify", "ecg"], "comparison_focus": "workflow"}
        )

    assert result["productsCompared"] == ["retify", "ecg"]
    assert len(result["rows"]) == 2
    assert result["rows"][0]["productId"] == "retify"
    assert "10" in result["rows"][0]["excerpt"]
