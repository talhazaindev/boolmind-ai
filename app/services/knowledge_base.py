"""Load knowledge base from markdown/text files for system prompt injection."""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".md", ".txt", ".markdown"}


def _product_name_from_path(path: Path) -> str:
    """Derive a short product name from filename (e.g. medical.md -> Medical)."""
    return path.stem.replace("_", " ").replace("-", " ").title()


def load_knowledge_base(base_path: Optional[Path] = None) -> str:
    """
    Load all markdown/text files from the knowledge base directory and format them
    as separate products in the system prompt so the LLM knows they are distinct.
    """
    if base_path is None:
        project_root = Path(__file__).resolve().parent.parent.parent
        base_path = project_root / "knowledge"

    if not base_path.exists() or not base_path.is_dir():
        logger.warning("Knowledge base path does not exist or is not a directory: %s", base_path)
        return ""

    parts: list[str] = []
    for path in sorted(base_path.iterdir()):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            try:
                content = path.read_text(encoding="utf-8", errors="replace").strip()
                if content:
                    product_name = _product_name_from_path(path)
                    parts.append(
                        f"## Domain / product: {product_name} (reference: {path.name})\n\n{content}"
                    )
            except OSError as e:
                logger.warning("Could not read knowledge file %s: %s", path, e)

    if not parts:
        logger.info("No knowledge base files found in %s", base_path)
        return ""

    intro = (
        "Internal reference: how we do data fusion in each domain. "
        "When the user's problem fits a domain, cite it—e.g. which pipeline, which step, how it works—so your answer is grounded in this. "
        "Do not pitch; do reference concretely when relevant.\n\n"
    )
    result = intro + "\n\n---\n\n".join(parts)
    logger.info("Loaded knowledge base: %d products (files), %d chars", len(parts), len(result))
    return result
