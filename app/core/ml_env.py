"""Apply ML cache paths from .env before Hugging Face / torch download."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIGURED = False


def configure_ml_environment() -> None:
    """Set HF hub cache on disk (e.g. D:) and ensure directories exist."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    from dotenv import load_dotenv

    project_root = Path(__file__).resolve().parent.parent.parent
    load_dotenv(project_root / ".env")

    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

    hf_home = os.getenv("HF_HOME", "").strip()
    if hf_home:
        base = Path(hf_home)
        hub = base / "hub"
        base.mkdir(parents=True, exist_ok=True)
        hub.mkdir(parents=True, exist_ok=True)
        os.environ["HF_HOME"] = str(base)
        os.environ["HUGGINGFACE_HUB_CACHE"] = str(hub)
        os.environ.setdefault("TRANSFORMERS_CACHE", str(base / "transformers"))
        logger.info("ML cache: HF_HOME=%s", base)
    else:
        logger.debug("HF_HOME not set; using default Hugging Face cache location")

    fidp_dir = os.getenv("FIDP_OUTPUT_DIR", "").strip()
    if fidp_dir:
        Path(fidp_dir).mkdir(parents=True, exist_ok=True)
        logger.info("FIDP output dir: %s", fidp_dir)

    _CONFIGURED = True
