"""Command-line entry point for the frozen V7 Day 3 benchmark."""

from __future__ import annotations

import argparse
from pathlib import Path

from askanu_rag.retrieval.benchmark import (
    CurrentSparseBaseline,
    Day3BoundedImprovement,
    LocalBm25Experiment,
    SupportExpansionExperiment,
    evaluate_benchmark,
    load_benchmark,
    report_json,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=Path("benchmarks/v7_day3/benchmark.json"),
    )
    parser.add_argument(
        "--pipeline",
        choices=("current", "support-expansion", "day3-improvement", "bm25"),
        default="current",
    )
    parser.add_argument("--selection-k", type=int, default=5)
    parser.add_argument("--latency-repetitions", type=int, default=25)
    args = parser.parse_args()

    suite = load_benchmark(args.benchmark)
    retriever = {
        "current": CurrentSparseBaseline,
        "support-expansion": SupportExpansionExperiment,
        "day3-improvement": Day3BoundedImprovement,
        "bm25": LocalBm25Experiment,
    }[args.pipeline]()
    report = evaluate_benchmark(
        suite,
        retriever,
        selection_k=args.selection_k,
        latency_repetitions=args.latency_repetitions,
    )
    print(report_json(report), end="")


if __name__ == "__main__":
    main()
