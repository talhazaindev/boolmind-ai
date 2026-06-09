#!/usr/bin/env python3
"""RAG retrieval eval harness — keyword presence in retrieved context."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.advisor.rag.retrieve import retrieve
from app.core.config import settings

EVAL_ROOT = ROOT / "tests" / "evals"
DEFAULT_SUITES = ("retify", "ecg", "legal", "forecasting", "capabilities", "cross-product")
THRESHOLDS = {
    "retify": 0.90,
    "ecg": 0.90,
    "legal": 0.90,
    "forecasting": 0.90,
    "capabilities": 0.90,
    "cross-product": 0.95,
}


def load_suite(name: str) -> list[dict]:
    path = EVAL_ROOT / name / "ground-truth.json"
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def run_case(case: dict) -> bool:
    ns = case.get("namespace", "auto")
    non_product_ns = ("general", "all", "capabilities", "architecture")
    active = None if ns in non_product_ns else ns
    if ns == "cross-product" or ns == "all":
        ns = "general"
    context = retrieve(
        query=case["query"],
        namespace_arg=ns,
        active_product=active,
        top_k=5,
        product_fit=case.get("product_fit"),
    )
    lower = context.lower()
    for token in case.get("must_contain", []):
        if token.lower() not in lower:
            return False
    for token in case.get("must_not_contain", []):
        if token.lower() in lower:
            return False
    return True


def run_suite(name: str) -> tuple[int, int, float]:
    cases = load_suite(name)
    passed = sum(1 for c in cases if run_case(c))
    total = len(cases)
    rate = passed / total if total else 0.0
    return passed, total, rate


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RAG eval suites")
    parser.add_argument(
        "--suite",
        default="all",
        help="Suite name or 'all' (retify, ecg, legal, cross-product)",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=None,
        help="Override minimum pass rate (0–1)",
    )
    args = parser.parse_args()

    if not settings.pinecone_configured or not settings.embeddings_configured:
        print("ERROR: Pinecone and embeddings must be configured in .env")
        return 1

    suites = list(DEFAULT_SUITES) if args.suite == "all" else [args.suite]
    failed_any = False

    for name in suites:
        try:
            passed, total, rate = run_suite(name)
        except FileNotFoundError as e:
            print(f"SKIP {name}: {e}")
            continue
        min_rate = args.min_score if args.min_score is not None else THRESHOLDS.get(name, 0.90)
        ok = rate >= min_rate
        status = "PASS" if ok else "FAIL"
        print(f"{status} {name}: {passed}/{total} ({rate:.0%}) threshold {min_rate:.0%}")
        if not ok:
            failed_any = True

    return 1 if failed_any else 0


if __name__ == "__main__":
    raise SystemExit(main())
