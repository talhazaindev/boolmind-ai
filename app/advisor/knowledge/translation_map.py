"""
IT-to-Business Translation Map.

Converts internal IT lever terminology into the outcome language business
owners actually respond to. Used to populate the OUTCOME_FRAMING prompt block.

Never says: "We will implement a CRM with workflow automation"
Always says: "You'll know exactly where every lead is, your team gets
              automatic follow-up reminders, and nothing falls through the cracks"

This is injected into the LLM prompt as framing constraints — the LLM narrates
in business language, not IT language.
"""

from __future__ import annotations

IT_LEVER_TO_OUTCOME_LANGUAGE: dict[str, dict[str, str | list[str]]] = {
    "crm_implementation": {
        "avoid_terms": ["CRM", "database", "platform", "integration"],
        "use_instead": [
            "never lose track of a customer again",
            "your team knows exactly who to follow up with and when",
            "every conversation in one place",
        ],
        "pain_frame": (
            "Right now something falls through the cracks between when a lead "
            "comes in and when they buy. That gap costs you revenue you've already earned."
        ),
        "solution_frame": (
            "The fix is making sure every lead, every customer, and every "
            "conversation is visible to your whole team — automatically."
        ),
    },
    "workflow_automation_and_integration": {
        "avoid_terms": ["API", "integration", "middleware", "ETL", "pipeline", "automation layer"],
        "use_instead": [
            "your systems talk to each other",
            "your team stops copy-pasting",
            "the handoff happens automatically",
        ],
        "pain_frame": (
            "Your team is acting as the bridge between systems that should be "
            "connected. That's hours of their time every week doing work a computer should do."
        ),
        "solution_frame": (
            "Connecting your tools so data flows automatically between them gives "
            "that time back — your team does the thinking, not the data entry."
        ),
    },
    "bi_dashboard": {
        "avoid_terms": ["BI", "data warehouse", "ETL", "dashboard", "analytics layer"],
        "use_instead": [
            "see your business performance live",
            "know by Monday morning exactly how last week went",
            "stop waiting for reports",
        ],
        "pain_frame": (
            "You're making decisions with information that's already a week old. "
            "By the time you see the numbers, it's too late to act on them."
        ),
        "solution_frame": (
            "A live view of your business means you catch problems while you can "
            "still fix them, not after they've cost you money."
        ),
    },
    "crm_with_reporting": {
        "avoid_terms": ["CRM", "pipeline reporting", "forecast module"],
        "use_instead": [
            "know your revenue number before the month ends",
            "see which deals are stalling",
            "stop being surprised by what your sales team is doing",
        ],
        "pain_frame": (
            "Right now you find out how sales went after it happened. That means "
            "you can't intervene, you can only react."
        ),
        "solution_frame": (
            "Knowing where every deal is in real time means you can coach your "
            "team, spot problems early, and forecast accurately."
        ),
    },
    "inventory_management_system": {
        "avoid_terms": ["ERP", "inventory module", "SKU tracking", "demand forecasting model"],
        "use_instead": [
            "never run out of your best-selling products",
            "stop over-ordering things that sit on shelves",
            "know when to reorder before it's too late",
        ],
        "pain_frame": (
            "Stockouts cost you sales you should have made. Overstock ties up cash "
            "in products that aren't moving. Both happen because the system can't "
            "see what's coming."
        ),
        "solution_frame": (
            "When your system can predict what you need before you run out, you "
            "stop losing sales and stop carrying dead stock."
        ),
    },
    "ai_chatbot_or_helpdesk": {
        "avoid_terms": ["LLM", "NLP", "chatbot", "AI model", "ticket system"],
        "use_instead": [
            "customers get answers in seconds",
            "your team handles the hard problems",
            "no message goes unanswered at 2am",
        ],
        "pain_frame": (
            "Your best support staff are spending half their day answering the same "
            "questions. That's not a people problem — it's a systems problem."
        ),
        "solution_frame": (
            "Training a system on your product knowledge means it handles the "
            "routine, your team handles the complex, and your customers are never waiting."
        ),
    },
    "field_ops_mobile_app": {
        "avoid_terms": [
            "mobile app",
            "GPS tracking",
            "dispatch system",
            "mobile workforce management",
        ],
        "use_instead": [
            "know where your team is at any moment",
            "customers can track their own order",
            "your drivers don't call in for instructions",
        ],
        "pain_frame": (
            "Every call your field team makes to the office to ask for instructions "
            "is time they're not working — and time your office staff are losing too."
        ),
        "solution_frame": (
            "When instructions, job details, and updates flow through an app, your "
            "field team works faster and your customers get visibility they currently don't have."
        ),
    },
    "document_ai": {
        "avoid_terms": ["OCR", "document intelligence", "LLM extraction", "NLP pipeline"],
        "use_instead": [
            "your team stops re-typing information that's already on a page",
            "documents process themselves",
            "data goes straight into your system",
        ],
        "pain_frame": (
            "Every invoice, form, or document your team manually reads and re-types "
            "is a task a computer can do in seconds. Your staff cost more than a "
            "computer — they should be doing work a computer can't do."
        ),
        "solution_frame": (
            "Document processing that extracts and routes data automatically means "
            "your team focuses on decisions, not data entry."
        ),
    },
    "lead_gen_website": {
        "avoid_terms": ["SEO", "conversion rate optimisation", "UX", "landing page"],
        "use_instead": [
            "people find you when they search for what you do",
            "visitors know exactly what to do next",
            "your website works while you sleep",
        ],
        "pain_frame": (
            "Right now your website is a brochure. Brochures don't generate "
            "enquiries — they just confirm you exist. You need a website that "
            "actively brings in business."
        ),
        "solution_frame": (
            "A website built to generate leads puts your best pitch in front of "
            "the right people at the exact moment they're looking for what you offer."
        ),
    },
    "approval_workflow_automation": {
        "avoid_terms": ["workflow engine", "approval matrix", "BPM", "process automation"],
        "use_instead": [
            "routine decisions happen without needing you",
            "your team moves faster",
            "you see everything without being in everything",
        ],
        "pain_frame": (
            "Every time your team waits for your sign-off on something routine, "
            "they lose momentum and you get interrupted. You built a business to "
            "escape this — not create a new version of it."
        ),
        "solution_frame": (
            "Setting clear rules for what requires your attention and what doesn't "
            "gives your team autonomy and gives you back your time."
        ),
    },
}


def get_outcome_framing(it_lever: str) -> dict[str, str | list[str]]:
    """
    Return outcome language for a given IT lever.

    Returns empty dict if lever not in map — caller handles gracefully.
    """
    return IT_LEVER_TO_OUTCOME_LANGUAGE.get(it_lever, {})
