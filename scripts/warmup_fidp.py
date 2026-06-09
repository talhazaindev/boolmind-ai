#!/usr/bin/env python3

"""Download SDXL Turbo weights and run one smoke image (optional before manual D4 tests)."""



from __future__ import annotations



import asyncio

import sys

from pathlib import Path



ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT))



from app.core.ml_env import configure_ml_environment



configure_ml_environment()





async def main() -> int:

    from app.advisor.integrations.local_sdxl_turbo import (

        LocalSdxlTurboImageGenClient,

        ensure_pipeline_loaded,

    )



    print("Step 1/2: Loading SDXL Turbo (first run downloads ~7GB to HF_HOME on D:)...")

    print("         This can take 15–30+ minutes. Inference timeout does not apply here.")

    await ensure_pipeline_loaded()

    print("Step 2/2: Running smoke inference on GPU...")



    client = LocalSdxlTurboImageGenClient()

    prompt = (

        "Futuristic data intelligence dashboard UI, purple and cyan accents, "

        "clean minimal SaaS, no text labels, abstract workflow"

    )

    result = await client.generate(prompt, seed=0, timeout_s=600.0)

    print("OK:", result.url)

    return 0





if __name__ == "__main__":

    raise SystemExit(asyncio.run(main()))


