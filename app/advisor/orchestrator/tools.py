"""Groq/OpenAI-compatible tool definitions — enums derived from product registry."""

from __future__ import annotations

from typing import Any

from app.advisor.config.products import (
    catalog_product_ids,
    compare_product_ids,
    crm_primary_product_ids,
    tour_product_ids,
)

_RAG_NAMESPACES = [
    *catalog_product_ids(),
    "capabilities",
    "general",
    "architecture",
    "all",
    "auto",
]


def _build_advisor_tools() -> list[dict[str, Any]]:
    tour_ids = tour_product_ids()
    compare_ids = compare_product_ids()
    crm_ids = crm_primary_product_ids()
    arch_ids = [*crm_ids, "custom_solutions"]

    return [
        {
            "type": "function",
            "function": {
                "name": "rag_query",
                "description": (
                    "Search the Boolmind knowledge base for catalog products, "
                    "Forecasting Engine, custom solutions/capabilities, or company info. "
                    "Call before answering ANY factual question."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Standalone search query; include product or capability area.",
                        },
                        "namespace": {
                            "type": "string",
                            "enum": _RAG_NAMESPACES,
                            "description": (
                                "Pinecone namespace; use capabilities for custom/bespoke needs; "
                                "auto from active product or product_fit."
                            ),
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "crm_create_lead",
                "description": (
                    "Create a lead in HubSpot when you have BOTH name and email. "
                    "Runs silently; do not ask the user to confirm."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "email": {"type": "string"},
                        "company": {"type": "string"},
                        "use_case": {"type": "string"},
                        "products_discussed": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "primary_product": {
                            "type": "string",
                            "enum": [*crm_ids, "custom_solutions"],
                        },
                        "qualification_score": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10,
                        },
                        "stage_at_capture": {
                            "type": "string",
                            "enum": ["QUALIFY", "CAPTURE", "BOOK"],
                        },
                    },
                    "required": [
                        "name",
                        "email",
                        "use_case",
                        "products_discussed",
                        "qualification_score",
                        "stage_at_capture",
                    ],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "product_tour",
                "description": (
                    "Retrieve an interactive catalog product tour. "
                    "Not for custom solutions — use architecture proposal instead."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_id": {
                            "type": "string",
                            "enum": tour_ids,
                        },
                        "start_step": {"type": "integer"},
                    },
                    "required": ["product_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "product_compare",
                "description": (
                    "Compare Boolmind catalog products using knowledge-base content. "
                    "Not for custom solutions. Never invent comparison facts."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_ids": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": compare_ids,
                            },
                            "description": "Catalog products to compare (2–4).",
                        },
                        "comparison_focus": {
                            "type": "string",
                            "enum": [
                                "general",
                                "workflow",
                                "features",
                                "integration",
                                "compliance",
                            ],
                        },
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "calendar_get_slots",
                "description": "Get available discovery call time slots from Cal.com.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                        "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                        "timezone": {"type": "string"},
                    },
                    "required": ["start_date", "end_date"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "calendar_book_slot",
                "description": "Book a discovery call after the user picks a slot.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "string", "description": "UTC ISO start time"},
                        "name": {"type": "string"},
                        "email": {"type": "string"},
                        "timezone": {"type": "string"},
                        "product_context": {"type": "string"},
                    },
                    "required": ["start", "name", "email"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "send_meeting_invite",
                "description": "Send branded meeting confirmation email after booking.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "email": {"type": "string"},
                        "name": {"type": "string"},
                        "start": {"type": "string"},
                        "booking_uid": {"type": "string"},
                        "product_name": {"type": "string"},
                    },
                    "required": ["email", "name", "start"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_architecture_proposal",
                "description": (
                    "Generate a solution architecture proposal for technical or custom solution requests."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "requirements_summary": {"type": "string"},
                        "primary_product": {
                            "type": "string",
                            "enum": arch_ids,
                        },
                        "constraints": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["requirements_summary"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_fidp",
                "description": "Generate Future Interface Design Preview image for the conversation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "conversation_id": {"type": "string"},
                        "primary_product": {
                            "type": "string",
                            "enum": arch_ids,
                        },
                        "trigger": {
                            "type": "string",
                            "enum": ["explicit", "post_architecture", "post_tour", "qual_score"],
                        },
                    },
                    "required": ["conversation_id"],
                },
            },
        },
    ]


ADVISOR_TOOLS: list[dict[str, Any]] = _build_advisor_tools()


def get_tool_definitions() -> list[dict[str, Any]]:
    return ADVISOR_TOOLS
