"""Image generation adapters: mock, Replicate, local SDXL Turbo."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

PLACEHOLDER_URL = "/fidp-placeholder.svg"


@dataclass
class ImageResult:
    url: str


class ImageGenClient(ABC):
    @abstractmethod
    async def generate(self, prompt: str, seed: int, timeout_s: float) -> ImageResult:
        pass


class MockImageGenClient(ImageGenClient):
    async def generate(self, prompt: str, seed: int, timeout_s: float) -> ImageResult:
        return ImageResult(url=PLACEHOLDER_URL)


class ReplicateImageGenClient(ImageGenClient):
    async def generate(self, prompt: str, seed: int, timeout_s: float) -> ImageResult:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                "https://api.replicate.com/v1/predictions",
                headers={"Authorization": f"Token {settings.replicate_api_token}"},
                json={
                    "version": "black-forest-labs/flux-schnell",
                    "input": {"prompt": prompt, "seed": seed},
                },
            )
            resp.raise_for_status()
            pred = resp.json()
            poll_url = pred.get("urls", {}).get("get", "")
            for _ in range(30):
                poll = await client.get(
                    poll_url,
                    headers={"Authorization": f"Token {settings.replicate_api_token}"},
                )
                poll.raise_for_status()
                body = poll.json()
                if body.get("status") == "succeeded":
                    out = body.get("output", [])
                    url = out[0] if out else PLACEHOLDER_URL
                    return ImageResult(url=url)
                if body.get("status") == "failed":
                    break
        return ImageResult(url=PLACEHOLDER_URL)


def get_image_gen_client() -> ImageGenClient:
    provider = settings.image_gen_provider.strip().lower()
    if provider == "local":
        from app.advisor.integrations.local_sdxl_turbo import LocalSdxlTurboImageGenClient

        return LocalSdxlTurboImageGenClient()
    if provider == "replicate" and settings.replicate_configured:
        return ReplicateImageGenClient()
    if provider == "replicate" and not settings.replicate_configured:
        logger.warning("IMAGE_GEN_PROVIDER=replicate but REPLICATE_API_TOKEN is unset; using mock")
    return MockImageGenClient()
