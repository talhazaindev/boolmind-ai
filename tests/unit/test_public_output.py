"""Tests for public output filtering."""

from app.advisor.orchestrator.public_output import (
    PublicOutputFilter,
    is_internal_narration_block,
    sanitize_public_output,
)


def test_sanitize_strips_diagnose_labels() -> None:
    raw = (
        "Observation: Manual compliance creates queue delay.\n\n"
        "Evidence: Volume exceeds review capacity.\n\n"
        "Inference: Compliance is the bottleneck."
    )
    cleaned = sanitize_public_output(raw)
    assert "Observation:" not in cleaned
    assert "compliance" in cleaned.lower()


def test_sanitize_removes_redacted_thinking_block() -> None:
    raw = (
        "<think>internal plan</think>\n\n"
        "Boolmind offers RETIFY and ECG."
    )
    assert sanitize_public_output(raw) == "Boolmind offers RETIFY and ECG."


def test_sanitize_removes_internal_narration() -> None:
    raw = (
        "Boolmind offers RETIFY.\n\n"
        "Okay, the user asked about services. I need to list them clearly.\n\n"
        "What challenge are you solving?"
    )
    cleaned = sanitize_public_output(raw)
    assert "Okay, the user" not in cleaned
    assert "I need to list" not in cleaned
    assert "What challenge are you solving?" in cleaned


def test_sanitize_removes_user_reported_narration_block() -> None:
    raw = (
        "Boolmind offers AI services tailored to specific business needs.\n\n"
        "Okay, the user asked about the AI services offered by Boolmind. "
        "I need to provide a clear overview of the products without mentioning any "
        "specific features that aren't covered in the provided knowledge. "
        "The user might be looking for a high-level understanding of what each product "
        "does, so I'll list them with brief descriptions. I should also prompt them to "
        "provide more context about their industry or problem to move the conversation "
        "forward. Let me make sure I'm not including any internal reasoning or "
        "technical jargon. Keep it simple and business-focused.\n\n"
        "Boolmind offers AI-driven solutions tailored to specific business challenges."
    )
    cleaned = sanitize_public_output(raw)
    assert "Okay, the user" not in cleaned
    assert "provided knowledge" not in cleaned
    assert "internal reasoning" not in cleaned
    assert cleaned.count("Boolmind offers") == 1


def test_is_internal_narration_detects_meta_monologue() -> None:
    text = (
        "Okay, the user asked about the AI services offered by Boolmind. "
        "I need to provide a clear overview."
    )
    assert is_internal_narration_block(text) is True


def test_stream_filter_splits_thinking_across_chunks() -> None:
    filt = PublicOutputFilter()
    assert filt.feed("Hello <redacted_thi") == "Hello "
    assert filt.feed("nking>secret</think> world") == " world"
    assert filt.flush() == ""


def test_stream_filter_discards_incomplete_thinking_at_end() -> None:
    filt = PublicOutputFilter()
    assert filt.feed("Answer <think>still thinking") == "Answer "
    assert filt.flush() == ""


def test_stream_filter_preserves_partial_tag_at_chunk_boundary() -> None:
    filt = PublicOutputFilter()
    assert filt.feed("Visible text <redac") == "Visible text "
    assert filt.feed("ted_thinking>hidden") == ""
    assert filt.feed("</think> tail") == " tail"


def test_stream_filter_preserves_words_ending_in_i() -> None:
    """Regression: must not strip trailing 'i' from words like custom / trying."""
    filt = PublicOutputFilter()
    part1 = filt.feed("Boolmind offers custom ")
    part2 = filt.feed("AI builds for industries you're trying to solve.")
    assert part1 == "Boolmind offers custom "
    assert part2 == "AI builds for industries you're trying to solve."
    assert filt.flush() == ""


def test_stream_filter_suppresses_narration_on_final_sanitize() -> None:
    raw = (
        "Boolmind offers Retify and ECG.\n\n"
        "Okay, the user asked about services. I need to provide a clear overview "
        "without mentioning any specific features that aren't covered in the "
        "provided knowledge.\n\n"
        "What industry are you in?"
    )
    cleaned = sanitize_public_output(raw)
    assert "Okay, the user" not in cleaned
    assert "What industry are you in?" in cleaned
