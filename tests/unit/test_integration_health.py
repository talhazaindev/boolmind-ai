"""Tests for failed-ops retry and integration health probes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.advisor.integrations import failed_ops_retry as retry
from app.advisor.integrations.integration_health import (
    _status,
    check_calcom,
    check_hubspot,
    check_supabase,
)


def test_status_off_when_not_configured() -> None:
    result = _status(False, False)
    assert result["status"] == "OFF"
    assert result["configured"] is False


def test_status_degraded_when_unreachable() -> None:
    result = _status(True, False, "timeout")
    assert result["status"] == "DEGRADED"
    assert result["error"] == "timeout"


def test_normalize_supabase_row() -> None:
    row = {
        "id": "abc",
        "operation": "crm_create_lead",
        "payload": {"email": "a@b.com", "session_id": "sess-1"},
        "error_message": "boom",
        "retries": 1,
        "created_at": "2026-01-01T00:00:00Z",
    }
    item = retry._normalize_supabase_row(row)
    assert item["source"] == "supabase"
    assert item["payload"]["email"] == "a@b.com"
    assert item["session_id"] == "sess-1"


@pytest.mark.asyncio
async def test_replay_all_queues_merges_results() -> None:
    memory_result = {"retried": 1, "succeeded": 1, "pending": 0, "results": [{"ok": True}]}
    supabase_result = {"retried": 2, "succeeded": 1, "pending": 1, "results": [{"ok": False}]}
    with (
        patch.object(retry, "replay_memory_queue", AsyncMock(return_value=memory_result)),
        patch.object(retry, "replay_supabase_queue", AsyncMock(return_value=supabase_result)),
    ):
        merged = await retry.replay_all_queues()
    assert merged["retried"] == 3
    assert merged["succeeded"] == 2
    assert merged["pending"] == 1
    assert len(merged["results"]) == 2


@pytest.mark.asyncio
async def test_check_supabase_not_configured() -> None:
    with patch("app.advisor.integrations.integration_health.settings") as mock_settings:
        mock_settings.supabase_configured = False
        result = await check_supabase()
    assert result["status"] == "OFF"


@pytest.mark.asyncio
async def test_check_hubspot_success() -> None:
    mock_resp = MagicMock(status_code=200, text="")
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with (
        patch("app.advisor.integrations.integration_health.settings") as mock_settings,
        patch("app.advisor.integrations.integration_health.httpx.AsyncClient", return_value=mock_client),
    ):
        mock_settings.hubspot_configured = True
        mock_settings.hubspot_access_token = "token"
        result = await check_hubspot()
    assert result["status"] == "ON"


@pytest.mark.asyncio
async def test_check_calcom_degraded_on_error() -> None:
    mock_resp = MagicMock(status_code=404, text="not found")
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with (
        patch("app.advisor.integrations.integration_health.settings") as mock_settings,
        patch("app.advisor.integrations.integration_health.httpx.AsyncClient", return_value=mock_client),
    ):
        mock_settings.calcom_configured = True
        mock_settings.calcom_api_key = "key"
        mock_settings.calcom_event_type_id = "123"
        result = await check_calcom()
    assert result["status"] == "DEGRADED"
