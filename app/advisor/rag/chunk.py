"""Document chunking for knowledge base ingest."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import tiktoken

MAX_CHUNK_TOKENS = 400
MIN_CHUNK_TOKENS = 50
OVERLAP_TOKENS = 50

_ENC = tiktoken.get_encoding("cl100k_base")


@dataclass
class Chunk:
    text: str
    source_doc: str
    section_title: str
    product_name: str
    namespace: str
    last_updated: str
    chunk_index: int


def _count_tokens(text: str) -> int:
    return len(_ENC.encode(text))


def _parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    meta: dict[str, str] = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    meta[k.strip().lower()] = v.strip()
            body = parts[2].strip()
    return meta, body


def chunk_markdown_file(path: Path, namespace: str) -> list[Chunk]:
    raw = path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(raw)
    product_name = meta.get("product", namespace)
    last_updated = meta.get("last updated", meta.get("last_updated", "2026-06-01"))
    source_doc = path.name

    chunks: list[Chunk] = []
    sections = re.split(r"\n(?=## )", body)
    chunk_index = 0

    for section in sections:
        section = section.strip()
        if not section:
            continue
        lines = section.split("\n", 1)
        section_title = lines[0].lstrip("#").strip() if lines else "Content"
        section_body = lines[1] if len(lines) > 1 else section

        header = (
            f"[Source: {source_doc} — {section_title} | Product: {product_name}]\n"
        )
        full_text = header + section_body
        tokens = _count_tokens(full_text)

        if tokens <= MAX_CHUNK_TOKENS:
            if tokens >= MIN_CHUNK_TOKENS or "?" in section_body:
                chunks.append(
                    Chunk(
                        text=full_text,
                        source_doc=source_doc,
                        section_title=section_title,
                        product_name=product_name,
                        namespace=namespace,
                        last_updated=last_updated,
                        chunk_index=chunk_index,
                    )
                )
                chunk_index += 1
            continue

        paragraphs = section_body.split("\n\n")
        buffer = header
        for para in paragraphs:
            candidate = buffer + ("\n\n" if buffer != header else "") + para
            if _count_tokens(candidate) > MAX_CHUNK_TOKENS and buffer != header:
                if _count_tokens(buffer) >= MIN_CHUNK_TOKENS:
                    chunks.append(
                        Chunk(
                            text=buffer.strip(),
                            source_doc=source_doc,
                            section_title=section_title,
                            product_name=product_name,
                            namespace=namespace,
                            last_updated=last_updated,
                            chunk_index=chunk_index,
                        )
                    )
                    chunk_index += 1
                buffer = header + para
            else:
                buffer = candidate
        if buffer != header and _count_tokens(buffer) >= MIN_CHUNK_TOKENS:
            chunks.append(
                Chunk(
                    text=buffer.strip(),
                    source_doc=source_doc,
                    section_title=section_title,
                    product_name=product_name,
                    namespace=namespace,
                    last_updated=last_updated,
                    chunk_index=chunk_index,
                )
            )
            chunk_index += 1

    return chunks
