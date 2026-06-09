"""Pinecone index connection — normalize host and resolve from API."""

from __future__ import annotations

import logging
import socket

from pinecone import Pinecone

from app.core.config import settings

logger = logging.getLogger(__name__)


def normalize_pinecone_host(host: str) -> str:
    """Strip quotes/scheme so the SDK gets a bare hostname."""
    cleaned = host.strip().strip('"').strip("'")
    if cleaned.startswith("https://"):
        cleaned = cleaned[len("https://") :]
    elif cleaned.startswith("http://"):
        cleaned = cleaned[len("http://") :]
    return cleaned.rstrip("/")


def _local_pinecone_url(host: str) -> str:
    """Docker service names (e.g. pinecone) need a URL with port for the SDK."""
    bare = normalize_pinecone_host(host)
    if bare.startswith("http://") or bare.startswith("https://"):
        return bare.rstrip("/")
    port = settings.pinecone_port
    if "." not in bare and bare != "localhost":
        return f"http://{bare}:{port}"
    if ":" not in bare:
        return f"http://{bare}:{port}"
    return f"http://{bare}"


def resolve_pinecone_host(pc: Pinecone | None = None) -> str:
    """
    Return the data-plane hostname for the configured index.
    Local mode uses PINECONE_HOST directly; cloud mode prefers describe_index.
    """
    if settings.pinecone_mode.strip().lower() == "local":
        if not settings.pinecone_host:
            raise RuntimeError("PINECONE_HOST is required when PINECONE_MODE=local")
        return _local_pinecone_url(settings.pinecone_host)

    client = pc or Pinecone(api_key=settings.pinecone_api_key)
    desc = client.describe_index(settings.pinecone_index_name)
    api_host = normalize_pinecone_host(desc.host)

    if settings.pinecone_host:
        env_host = normalize_pinecone_host(settings.pinecone_host)
        if env_host != api_host:
            logger.warning(
                "PINECONE_HOST in .env (%s) does not match API host (%s). Using API host.",
                env_host,
                api_host,
            )
    return api_host


def verify_host_resolves(host: str) -> None:
    lookup_host = host
    port = (
        settings.pinecone_port
        if settings.pinecone_mode.strip().lower() == "local"
        else 443
    )
    if "://" in lookup_host:
        from urllib.parse import urlparse

        parsed = urlparse(lookup_host)
        lookup_host = parsed.hostname or lookup_host
        if parsed.port:
            port = parsed.port
    try:
        socket.getaddrinfo(lookup_host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise RuntimeError(
            f"Cannot resolve Pinecone host '{host}' (DNS/getaddrinfo failed). "
            "Check PINECONE_HOST / PINECONE_MODE and that the vector service is running. "
            f"({e})"
        ) from e


def get_pinecone_index(pc: Pinecone | None = None):
    """Connected Index client for upsert/query."""
    api_key = settings.pinecone_api_key or "pclocal"
    client = pc or Pinecone(api_key=api_key)
    host = resolve_pinecone_host(client)
    verify_host_resolves(host)
    logger.debug(
        "Pinecone index %s @ %s (mode=%s)",
        settings.pinecone_index_name,
        host,
        settings.pinecone_mode,
    )
    return client.Index(host=host)
