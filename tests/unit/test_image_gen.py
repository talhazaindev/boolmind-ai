"""Unit tests for image generation client selection and local FIDP save."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.advisor.integrations import local_sdxl_turbo
from app.advisor.integrations.image_gen import (
    MockImageGenClient,
    ReplicateImageGenClient,
    get_image_gen_client,
)
from app.core.config import settings


def test_get_image_gen_client_mock_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "image_gen_provider", "mock")
    assert isinstance(get_image_gen_client(), MockImageGenClient)


def test_get_image_gen_client_replicate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "image_gen_provider", "replicate")
    monkeypatch.setattr(settings, "replicate_api_token", "test-token")
    assert isinstance(get_image_gen_client(), ReplicateImageGenClient)


def test_get_image_gen_client_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "image_gen_provider", "local")
    client = get_image_gen_client()
    assert client.__class__.__name__ == "LocalSdxlTurboImageGenClient"


@pytest.mark.asyncio
async def test_local_generate_saves_png(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "fidp_output_dir", str(tmp_path))
    monkeypatch.setattr(settings, "image_gen_steps", 1)
    monkeypatch.setattr(settings, "image_gen_size", 512)

    fake_image = MagicMock()
    fake_pipe = MagicMock()
    fake_pipe.return_value.images = [fake_image]

    def _write_png(path: Path, format: str | None = None) -> None:
        Path(path).write_bytes(b"\x89PNG\r\n")

    fake_image.save.side_effect = _write_png

    local_sdxl_turbo.reset_local_pipeline()
    with (
        patch.object(local_sdxl_turbo, "_get_pipeline", return_value=fake_pipe),
        patch.object(local_sdxl_turbo, "ensure_pipeline_loaded", new=AsyncMock()),
    ):
        from app.advisor.integrations.local_sdxl_turbo import LocalSdxlTurboImageGenClient

        client = LocalSdxlTurboImageGenClient()
        result = await client.generate("dashboard ui mockup", seed=42, timeout_s=30.0)

    assert result.url.startswith("/fidp/fidp_")
    assert result.url.endswith(".png")
    saved = list(tmp_path.glob("fidp_*.png"))
    assert len(saved) == 1
    fake_image.save.assert_called_once()
    local_sdxl_turbo.reset_local_pipeline()
