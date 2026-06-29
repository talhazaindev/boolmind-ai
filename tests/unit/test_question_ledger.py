"""Question ledger — declined answers and repeat prevention."""

from __future__ import annotations

from app.advisor.pipeline.question_ledger import (
    is_declined_reply,
    is_question_exhausted,
    normalize_question_fingerprint,
    process_ledger_on_user_turn,
    question_topic_key,
)
from app.advisor.pipeline.turn_pipeline import TurnPipeline
from app.advisor.types import SessionMetadata


def test_declined_reply_detected() -> None:
    assert is_declined_reply("I dont know about this.")
    assert is_declined_reply("not sure")
    assert not is_declined_reply(
        "We process 200 orders per day mostly dine-in with manual kitchen tickets."
    )


def test_declined_marks_timeline_skipped() -> None:
    meta = SessionMetadata(
        last_appended_question="When did you first notice this shift — roughly which quarter or month?",
        asked_question_fingerprints=[
            normalize_question_fingerprint(
                "When did you first notice this shift — roughly which quarter or month?"
            )
        ],
        open_question_keys=["timeline"],
    )
    open_keys, answered, skipped = process_ledger_on_user_turn(
        meta, "I dont know about this.", []
    )
    assert "timeline" in skipped
    assert "timeline" not in open_keys


def test_exhausted_question_blocked() -> None:
    meta = SessionMetadata(
        skipped_question_keys=["timeline"],
        asked_question_fingerprints=[
            normalize_question_fingerprint(
                "When did you first notice this shift — roughly which quarter or month?"
            )
        ],
    )
    q = "When did you first notice this shift — roughly which quarter or month?"
    assert is_question_exhausted(q, meta)
    assert question_topic_key(q) == "timeline"


def test_restaurant_turn3_advances_after_decline() -> None:
    t1 = (
        "I am a small restaurant owner. I want to automate everything from order taking "
        "to kitchen to serving and then managing my stocks"
    )
    t2 = (
        "The thing which is hurting me the most is I am managing everything manually and "
        "I cant have a clear picture of what is more profitable and which items are costing "
        "me more. And then order taking system is also manual. I want a solution where my "
        "order taking system is automated and kitchen can receive the order and waiter should "
        "know which order came from which table."
    )
    t3 = (
        "I dont know about this. But I think it will help me in reducing my labor cost "
        "and help me maximizing my profit."
    )

    r1 = TurnPipeline.run(SessionMetadata(), t1, [])
    r2 = TurnPipeline.run(r1.extracted_meta, t2, [t1])
    r3 = TurnPipeline.run(r2.extracted_meta, t3, [t1, t2])

    q2 = (r2.snapshot.required_question or "").lower()
    q3 = (r3.snapshot.required_question or "").lower()
    assert q2
    assert q3
    assert q3 != q2
    assert "first notice" not in q3
    assert "quarter or month" not in q3
    assert any(
        term in q3
        for term in (
            "profit",
            "order",
            "manual",
            "kitchen",
            "stock",
            "flow",
            "labor",
            "role",
            "revenue",
            "rollout",
            "budget",
            "workflow",
            "automate",
            "busy",
        )
    )


def test_restaurant_long_conversation_no_stock_repeat() -> None:
    """After rich operational context, bot must not repeat stock-tracking probes."""
    turns = [
        (
            "I am a small restaurant owner and I want to automate everything from order taking "
            "to the menu, kitchen coordination, and stocks management."
        ),
        (
            "There are waiters, taking order manually on a paper bill which we use later to "
            "track the sales and profits. Same for the delivery."
        ),
        "All of the above. Order entry, kitchen coordination and stockout problem.",
        "No. Total manual",
        (
            "I ask the kitchen staff at the end of the day. And it may not be fulfilled on "
            "weekends. Sometimes we have to face stockouts on weekends and on some special days."
        ),
        "I don't have any proper data. Just based on my assumptions and guesses",
        "Manually and it takes too long maybe 2 hours after closing.",
        (
            "There is no way to track stock levels other then day end report. We often run out "
            "of stock and few times I have over order which caused huge loss as they got rotten "
            "and useless the next day"
        ),
    ]

    meta = SessionMetadata()
    history: list[str] = []
    last_q = ""

    for message in turns:
        result = TurnPipeline.run(meta, message, history)
        meta = result.extracted_meta
        history.append(message)
        q = (result.snapshot.required_question or "").lower()
        if q:
            last_q = q

    assert last_q
    assert "track stock levels" not in last_q
    assert "run out or over-order" not in last_q
    assert any(
        term in last_q
        for term in (
            "automate",
            "workflow",
            "first",
            "priorit",
            "highest-impact",
            "urgent",
            "pick one",
        )
    )
    assert "inventory_tracking" in meta.answered_question_keys or "order_flow" in meta.answered_question_keys
