#!/usr/bin/env python3
"""Benchmark LLM performance for featcat tasks.

Usage:
    python scripts/benchmark_llm.py [--model MODEL] [--task TASK] [--runs N]

Measures latency, JSON parse success rate, and output quality for each plugin task.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.table import Table

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature
from featcat.config import load_settings
from featcat.llm import create_llm

console = Console()


def setup_test_catalog(db_path: str) -> LocalBackend:
    """Create a test catalog with sample features."""
    db = LocalBackend(db_path)
    db.init_db()

    source = DataSource(name="user_behavior_30d", path="/data/user_behavior.parquet")
    db.add_source(source)

    features = [
        ("session_count", "int64", {"mean": 15.2, "std": 8.3, "null_ratio": 0.02, "min": 0, "max": 120}),
        ("data_usage_mb", "float64", {"mean": 2048.5, "std": 1500.2, "null_ratio": 0.01, "min": 0, "max": 50000}),
        ("complaint_count", "int64", {"mean": 0.8, "std": 1.2, "null_ratio": 0.0, "min": 0, "max": 15}),
        ("monthly_revenue", "float64", {"mean": 250000.0, "std": 180000.0, "null_ratio": 0.05, "min": 0, "max": 2e6}),
        ("churn_label", "int64", {"mean": 0.12, "std": 0.32, "null_ratio": 0.0, "min": 0, "max": 1}),
    ]

    for col, dtype, stats in features:
        db.upsert_feature(
            Feature(
                name=f"user_behavior_30d.{col}",
                data_source_id=source.id,
                column_name=col,
                dtype=dtype,
                stats=stats,
                tags=["behavior", "30d"],
            )
        )
    return db


def benchmark_task(db: LocalBackend, llm, task: str, runs: int) -> dict:
    """Run a single task multiple times and collect metrics."""
    results = {"task": task, "runs": runs, "latencies": [], "json_success": 0, "errors": []}

    for i in range(runs):
        start = time.time()
        try:
            if task == "autodoc":
                from featcat.plugins.autodoc import AutodocPlugin

                plugin = AutodocPlugin()
                result = plugin.execute(db, llm, feature_name="user_behavior_30d.session_count")

            elif task == "discovery":
                from featcat.plugins.discovery import DiscoveryPlugin

                plugin = DiscoveryPlugin()
                result = plugin.execute(db, llm, use_case="churn prediction for telecom subscribers")

            elif task == "nl_query":
                from featcat.plugins.nl_query import NLQueryPlugin

                plugin = NLQueryPlugin()
                result = plugin.execute(db, llm, query="features related to user engagement")

            elif task == "monitoring":
                from featcat.plugins.monitoring import MonitoringPlugin

                # First set baselines
                db.save_baseline(
                    db.list_features()[0].id,
                    db.list_features()[0].stats,
                )
                plugin = MonitoringPlugin()
                result = plugin.execute(db, llm, action="check", use_llm=True)

            elapsed = time.time() - start
            results["latencies"].append(elapsed)

            if result.status in ("success", "partial"):
                results["json_success"] += 1
            else:
                results["errors"].append(f"Run {i + 1}: {result.errors}")

        except Exception as e:
            elapsed = time.time() - start
            results["latencies"].append(elapsed)
            results["errors"].append(f"Run {i + 1}: {e}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Benchmark LLM performance for featcat")
    parser.add_argument("--model", default=None, help="Model name (default: from config)")
    parser.add_argument("--task", default="all", choices=["autodoc", "discovery", "nl_query", "monitoring", "all"])
    parser.add_argument("--runs", type=int, default=3, help="Number of runs per task")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    settings = load_settings()
    model = args.model or settings.llm_model

    console.print("\n[bold]featcat LLM Benchmark[/bold]")
    console.print(f"  Model: {model}")
    console.print(f"  Backend: {settings.llm_backend}")
    console.print(f"  Runs per task: {args.runs}\n")

    # Create LLM
    try:
        llm = create_llm(
            backend=settings.llm_backend,
            model=model,
            base_url=settings.ollama_url if settings.llm_backend == "ollama" else settings.llamacpp_url,
            timeout=settings.llm_timeout,
            max_retries=settings.llm_max_retries,
        )
        if not llm.health_check():
            console.print("[red]LLM not reachable. Is Ollama running?[/red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]Failed to create LLM: {e}[/red]")
        sys.exit(1)

    # Setup test catalog
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        db = setup_test_catalog(str(Path(tmp) / "benchmark.db"))

        tasks = ["autodoc", "discovery", "nl_query"] if args.task == "all" else [args.task]
        all_results = []

        for task in tasks:
            console.print(f"[blue]Running {task}...[/blue]")
            result = benchmark_task(db, llm, task, args.runs)
            all_results.append(result)

        db.close()

    # Display results
    if args.json:
        print(json.dumps(all_results, indent=2, default=str))
        return

    table = Table(title="Benchmark Results")
    table.add_column("Task", style="cyan")
    table.add_column("Avg Latency", justify="right")
    table.add_column("Min", justify="right")
    table.add_column("Max", justify="right")
    table.add_column("JSON Success", justify="right")
    table.add_column("Errors")

    for r in all_results:
        lats = r["latencies"]
        avg = sum(lats) / len(lats) if lats else 0
        mn = min(lats) if lats else 0
        mx = max(lats) if lats else 0
        success_rate = f"{r['json_success']}/{r['runs']}"
        error_count = str(len(r["errors"])) if r["errors"] else "-"

        table.add_row(
            r["task"],
            f"{avg:.1f}s",
            f"{mn:.1f}s",
            f"{mx:.1f}s",
            success_rate,
            error_count,
        )

    console.print(table)

    if any(r["errors"] for r in all_results):
        console.print("\n[yellow]Errors:[/yellow]")
        for r in all_results:
            for err in r["errors"]:
                console.print(f"  [{r['task']}] {err}")


if __name__ == "__main__":
    main()
