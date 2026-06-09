"""Local SDXL Turbo image generation (CUDA, lazy-loaded pipeline)."""



from __future__ import annotations



import asyncio

import logging

import threading

import uuid

from pathlib import Path



from app.advisor.integrations.image_gen import ImageGenClient, ImageResult

from app.core.config import settings



logger = logging.getLogger(__name__)



_pipeline = None

_pipeline_lock = threading.Lock()



# Model download/load can take 20+ minutes on first run; only inference is bounded.

LOAD_TIMEOUT_S = 3600.0





def _get_pipeline():

    global _pipeline

    if _pipeline is not None:

        return _pipeline

    with _pipeline_lock:

        if _pipeline is not None:

            return _pipeline

        import torch

        from diffusers import AutoPipelineForText2Image



        if not torch.cuda.is_available():

            raise RuntimeError(

                "CUDA is not available. Run scripts/setup_gpu.ps1 and restart the server."

            )



        model_id = settings.image_gen_model

        logger.info("Loading local image model: %s (first run downloads to HF_HOME)", model_id)

        pipe = AutoPipelineForText2Image.from_pretrained(

            model_id,

            torch_dtype=torch.float16,

            variant="fp16",

        )

        pipe.to("cuda")

        pipe.enable_attention_slicing()

        pipe.set_progress_bar_config(disable=not settings.debug)

        _pipeline = pipe

        logger.info("Local image model ready on %s", torch.cuda.get_device_name(0))

        return _pipeline





def is_pipeline_loaded() -> bool:

    return _pipeline is not None





def _run_inference_sync(prompt: str, seed: int, output_dir: Path) -> ImageResult:

    import torch



    pipe = _get_pipeline()

    generator = torch.Generator(device="cuda").manual_seed(seed)

    size = settings.image_gen_size

    logger.info("FIDP inference start (%dx%d, %d steps)", size, size, settings.image_gen_steps)

    result = pipe(

        prompt=prompt,

        num_inference_steps=settings.image_gen_steps,

        guidance_scale=0.0,

        height=size,

        width=size,

        generator=generator,

    )

    image = result.images[0]

    filename = f"fidp_{uuid.uuid4().hex[:12]}.png"

    output_dir.mkdir(parents=True, exist_ok=True)

    out_path = output_dir / filename

    image.save(out_path, format="PNG")

    logger.info("FIDP image saved: %s", out_path)

    return ImageResult(url=f"/fidp/{filename}")





async def ensure_pipeline_loaded() -> None:

    """Download/load weights (unbounded except LOAD_TIMEOUT_S). Call before first inference."""

    if is_pipeline_loaded():

        return

    await asyncio.wait_for(

        asyncio.to_thread(_get_pipeline),

        timeout=LOAD_TIMEOUT_S,

    )





class LocalSdxlTurboImageGenClient(ImageGenClient):

    """SDXL Turbo on local GPU; load and inference run in worker threads."""



    async def generate(self, prompt: str, seed: int, timeout_s: float) -> ImageResult:

        output_dir = settings.fidp_output_path

        await ensure_pipeline_loaded()

        return await asyncio.wait_for(

            asyncio.to_thread(_run_inference_sync, prompt, seed, output_dir),

            timeout=timeout_s,

        )





def reset_local_pipeline() -> None:

    """Clear cached pipeline (for tests)."""

    global _pipeline

    with _pipeline_lock:

        _pipeline = None


