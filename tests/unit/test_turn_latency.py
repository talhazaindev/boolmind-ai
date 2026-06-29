"""Turn latency breakdown tests."""

from app.advisor.monitoring.latency import TurnLatency


def test_turn_latency_summary_accounts_phases() -> None:
    tracker = TurnLatency()
    tracker.mark("turn_start")
    tracker.mark("eval_start")
    tracker.mark("eval_end")
    tracker.mark("llm_r0_start")
    tracker.mark("llm_r0_end")
    tracker.finish_llm_round(0)
    tracker.record_tool("rag_query", 1200.0)
    tracker.mark("llm_r1_start")
    tracker.mark("first_token")
    tracker.mark("llm_r1_end")
    tracker.finish_llm_round(1)
    tracker.mark("turn_end")

    summary = tracker.summary()
    assert "eval_ms" in summary
    assert len(summary["llm_rounds_ms"]) == 2
    assert summary["tools_total_ms"] == 1200.0
    assert summary["tools"][0]["tool"] == "rag_query"
    assert summary["total_ms"] >= 0
