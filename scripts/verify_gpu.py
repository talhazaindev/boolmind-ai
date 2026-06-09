#!/usr/bin/env python3
"""Verify CUDA PyTorch and ML cache paths (run after scripts/setup_gpu.ps1)."""

from __future__ import annotations

import sys
from pathlib import Path

# Project root on path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.ml_env import configure_ml_environment


def main() -> int:
    configure_ml_environment()
    import os

    import torch

    print("torch version:", torch.__version__)
    print("cuda available:", torch.cuda.is_available())
    hf = os.environ.get("HF_HOME", "(default)")
    print("HF_HOME:", hf)
    if hf != "(default)" and Path(hf).exists():
        print("HF_HOME exists: yes")
    if not torch.cuda.is_available():
        print(
            "\nFAIL: CUDA not available. Re-run: .\\scripts\\setup_gpu.ps1",
            file=sys.stderr,
        )
        return 1
    name = torch.cuda.get_device_name(0)
    props = torch.cuda.get_device_properties(0)
    vram_gb = props.total_memory / (1024**3)
    print("gpu:", name)
    print(f"vram: {vram_gb:.2f} GiB")
    # Quick allocation smoke test
    x = torch.zeros(1, device="cuda")
    del x
    torch.cuda.empty_cache()
    print("\nOK: GPU ready for local image models (FLUX Klein 4B / SDXL Turbo).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
