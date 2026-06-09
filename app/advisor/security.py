"""HMAC signing, rate limiting, input sanitization."""

from __future__ import annotations

import hashlib
import hmac
import re
import time
from collections import defaultdict
from typing import Any

from fastapi import HTTPException, Request

from app.core.config import settings

_HTML_TAG = re.compile(r"<[^>]+>")
_RATE_BUCKETS: dict[str, list[float]] = defaultdict(list)
_REPLAY_WINDOW_S = 60


def sanitize_message(text: str, max_len: int = 2000) -> str:
    cleaned = _HTML_TAG.sub("", text).strip()
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len]
    return cleaned


def verify_chat_signature(request: Request, body: bytes) -> None:
    if not settings.chat_api_secret:
        return
    sig = request.headers.get("X-Chat-Signature", "")
    ts = request.headers.get("X-Chat-Timestamp", "")
    if not sig or not ts:
        raise HTTPException(status_code=401, detail="Missing chat signature")
    try:
        ts_int = int(ts)
    except ValueError as e:
        raise HTTPException(status_code=401, detail="Invalid timestamp") from e
    if abs(time.time() - ts_int) > _REPLAY_WINDOW_S:
        raise HTTPException(status_code=401, detail="Request expired")
    expected = hmac.new(
        settings.chat_api_secret.encode(),
        f"{ts}.{body.decode('utf-8')}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=401, detail="Invalid signature")


def check_rate_limit(key: str, limit: int, window_s: int = 60) -> None:
    now = time.time()
    bucket = _RATE_BUCKETS[key]
    _RATE_BUCKETS[key] = [t for t in bucket if now - t < window_s]
    if len(_RATE_BUCKETS[key]) >= limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    _RATE_BUCKETS[key].append(now)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"
