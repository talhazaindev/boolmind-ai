"""Page URL → product id, page mode, and opening messages."""

from __future__ import annotations

from typing import Literal

from app.advisor.config.products import PRODUCTS, get_product
from app.advisor.constants import PRODUCT_NAMES
from app.advisor.types import PageContext

PageMode = Literal["home", "product", "compare", "pricing", "services", "about"]

_URL_PRODUCT_PATHS: tuple[tuple[str, str], ...] = (
    ("/products/retify", "retify"),
    ("/retify", "retify"),
    ("/products/ecg", "ecg"),
    ("/ecg", "ecg"),
    ("/products/legal", "legal"),
    ("/legal", "legal"),
    ("/products/forecasting", "forecasting"),
    ("/forecasting", "forecasting"),
    ("/forecasting-engine", "forecasting"),
)


def page_mode_from_url(url: str) -> PageMode:
    lower = url.lower()
    if "/compare" in lower:
        return "compare"
    if "/pricing" in lower:
        return "pricing"
    if "/services" in lower:
        return "services"
    if "/about" in lower:
        return "about"
    if any(p in lower for p in ("/products/", "/retify", "/ecg", "/legal", "/forecasting")):
        return "product"
    return "home"


def product_id_from_url(url: str) -> tuple[str | None, str | None]:
    """Map URL path to product id and display name (spec 9.1.1)."""
    lower = url.lower()
    for path, pid in _URL_PRODUCT_PATHS:
        if path in lower:
            return pid, PRODUCT_NAMES.get(pid, pid)
    return None, None


def opening_message_for_page(page: PageContext) -> str | None:
    """Product- and page-specific opening lines for chat-init."""
    if page.product_id:
        product = get_product(page.product_id)
        if product:
            return (
                f"I see you're exploring {product.name}. "
                f"{product.discovery_question}"
            )

    mode = page_mode_from_url(page.url)
    if mode == "compare":
        names = ", ".join(
            p.name.split(" — ")[0] if " — " in p.name else p.name
            for p in PRODUCTS
            if p.compare_in_default
        )
        return (
            f"You're on our product comparison page. I can explain how {names} differ — "
            "what's your primary use case?"
        )
    if mode == "pricing":
        return (
            "I can't share pricing in chat, but I can help you identify the right product "
            "or custom solution and connect you with our team for a quote."
        )
    if mode == "services":
        return (
            "Boolmind offers catalog data products plus custom web, mobile, and applied-AI solutions. "
            "What business challenge are you trying to solve?"
        )
    if mode == "about":
        return (
            "Welcome to Boolmind. We build data intelligence products and custom engineering solutions. "
            "What would you like to explore?"
        )
    return "Hi, I'm the Boolmind Advisor. What brings you to Boolmind today?"
