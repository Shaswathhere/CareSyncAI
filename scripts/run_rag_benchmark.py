"""
scripts/run_rag_benchmark.py
----------------------------
CLI runner for the CareSync AI 50-Scenario Public Health RAG Benchmark.

Usage:
    python scripts/run_rag_benchmark.py [--llm-judge] [--output-dir DIR] [--mock]

Features:
    - Runs all 50 clinical and operational test scenarios.
    - Measures Retrieval Precision, Faithfulness/Groundedness, Answer Correctness.
    - Generates GitHub-flavored Markdown report and JSON artifacts.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.test_rag_benchmark import FULL_50_BENCHMARK_SCENARIOS
from rag.evaluation import (
    BenchmarkSummary,
    format_benchmark_markdown,
    run_rag_benchmark,
)
from rag.llm import SCOPE_REFUSAL_MESSAGE, SAFE_FALLBACK_MESSAGE


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CareSync AI 50-Scenario RAG Benchmark")
    parser.add_argument("--llm-judge", action="store_true", help="Enable Groq LLM-as-judge evaluation")
    parser.add_argument("--output-dir", default="benchmark_reports", help="Directory to save output reports")
    parser.add_argument("--mock", action="store_true", help="Run in mock/offline mode for verification")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 70)
    print("[CareSync AI] 50-Scenario Public Health RAG Benchmark")
    print("=" * 70)
    print(f"Total Scenarios: {len(FULL_50_BENCHMARK_SCENARIOS)}")
    print(f"Mode: {'Mock Simulation' if args.mock else 'Live Pipeline'}")
    print(f"LLM-as-judge: {args.llm_judge}")
    print("-" * 70)

    query_fn = None
    if args.mock:
        def mock_pipeline(query: str):
            for tc in FULL_50_BENCHMARK_SCENARIOS:
                if tc.query == query:
                    if tc.is_out_of_scope:
                        return {"answer": SCOPE_REFUSAL_MESSAGE, "sources": [], "confidence": 0.0}
                    return {
                        "answer": tc.ground_truth_answer,
                        "sources": [{
                            "document_title": tc.expected_document_title,
                            "version": tc.expected_version,
                            "content": tc.ground_truth_answer,
                        }],
                        "confidence": 0.94,
                    }
            return {"answer": SAFE_FALLBACK_MESSAGE, "sources": [], "confidence": 0.0}
        query_fn = mock_pipeline

    start_time = time.time()
    summary = run_rag_benchmark(
        dataset=FULL_50_BENCHMARK_SCENARIOS,
        query_fn=query_fn,
        llm_judge=args.llm_judge,
    )
    duration = time.time() - start_time

    print(f"\nExecution finished in {duration:.2f}s")
    print(f"Passed: {summary.passed_tests}/{summary.total_tests} ({summary.pass_rate_pct}%)")
    print(f"Average Overall Score: {summary.avg_overall_score:.3f}")
    print(f"Average Retrieval Precision: {summary.avg_retrieval_precision:.3f}")
    print(f"Average Faithfulness: {summary.avg_faithfulness:.3f}")
    print(f"Average Latency: {summary.avg_latency_ms:.1f} ms")

    # Save reports
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    md_report = format_benchmark_markdown(summary)
    md_file = out_dir / f"rag_benchmark_{timestamp}.md"
    md_file.write_text(md_report, encoding="utf-8")

    json_file = out_dir / f"rag_benchmark_{timestamp}.json"
    summary_dict = {
        "timestamp": timestamp,
        "total_tests": summary.total_tests,
        "passed_tests": summary.passed_tests,
        "pass_rate_pct": summary.pass_rate_pct,
        "avg_overall_score": summary.avg_overall_score,
        "avg_retrieval_precision": summary.avg_retrieval_precision,
        "avg_faithfulness": summary.avg_faithfulness,
        "avg_answer_correctness": summary.avg_answer_correctness,
        "avg_latency_ms": summary.avg_latency_ms,
        "category_breakdown": summary.category_breakdown,
    }
    json_file.write_text(json.dumps(summary_dict, indent=2), encoding="utf-8")

    print(f"\nReports saved:")
    print(f"  Markdown: {md_file}")
    print(f"  JSON:     {json_file}")
    print("=" * 70)


if __name__ == "__main__":
    main()
