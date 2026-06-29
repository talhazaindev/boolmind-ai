"""Tests for CRM lead Supabase mirror."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.advisor.tools import crm_create_lead


@pytest.mark.asyncio
async def test_mirror_lead_called_when_hubspot_not_configured() -> None:
    with (
        patch("app.advisor.tools.crm_create_lead.settings") as mock_settings,
        patch(
            "app.advisor.tools.crm_create_lead._mirror_lead_to_supabase",
            AsyncMock(),
        ) as mirror,
        patch("app.advisor.tools.crm_create_lead.get_redis_store"),
    ):
        mock_settings.hubspot_configured = False
        mock_settings.supabase_configured = True
        result = await crm_create_lead.handle(
            {"email": "test@example.com", "name": "Test User"},
            "sess-1",
            None,
        )
    assert result["status"] == "queued"
    mirror.assert_awaited_once()


@pytest.mark.asyncio
async def test_mirror_lead_called_after_hubspot_create() -> None:
    mock_resp = type("R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"id": "99"}})()
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.advisor.tools.crm_create_lead.settings") as mock_settings,
        patch("app.advisor.tools.crm_create_lead.httpx.AsyncClient", return_value=mock_client),
        patch("app.advisor.tools.crm_create_lead.lead_captured"),
        patch("app.advisor.tools.crm_create_lead.get_redis_store"),
        patch(
            "app.advisor.tools.crm_create_lead._mirror_lead_to_supabase",
            AsyncMock(),
        ) as mirror,
    ):
        mock_settings.hubspot_configured = True
        mock_settings.hubspot_access_token = "token"
        result = await crm_create_lead.handle(
            {
                "email": "test@example.com",
                "name": "Test User",
                "products_discussed": ["retify"],
            },
            "sess-1",
            None,
        )
    assert result["status"] == "created"
    mirror.assert_awaited_once()
    assert mirror.await_args.kwargs["hubspot_id"] == "99"
