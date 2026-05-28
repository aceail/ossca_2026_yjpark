"""Sprint 29 evaluation harness CLI.

Provides three main commands:
1. export-phoenix: Extract traces from Phoenix and convert to evaluation scenarios
2. run-scenarios: Run chat agent against a curated scenario set
3. score-only: Score actual output against expected output

Usage:
    python -m eval.cli export-phoenix --url http://localhost:6006 --output eval/scenarios/phoenix.json [--limit 100] [--failure-only]
    python -m eval.cli run-scenarios eval/scenarios/sprint29.json [--db PATH] [--json-summary]
    python -m eval.cli score-only --actual-json FILE --expected-json FILE
"""

import argparse
import json
import sys
from pathlib import Path


def cmd_export_phoenix(args):
    """Export traces from Phoenix REST API to scenario JSON."""
    from eval.phoenix_export import export_traces_to_scenarios

    n = export_traces_to_scenarios(
        args.url,
        args.output,
        limit=args.limit,
        failure_only=args.failure_only,
    )
    print(f"exported {n} scenarios → {args.output}")


def cmd_run_scenarios(args):
    """Run chat evaluation against a scenario file."""
    from eval.runner_sprint29 import run_chat_eval

    with open(args.scenarios, encoding="utf-8") as f:
        scenarios = json.load(f)

    result = run_chat_eval(scenarios, db_path=args.db)

    if args.json_summary:
        print(json.dumps(result["summary"], indent=2, ensure_ascii=False))
    else:
        s = result["summary"]
        print(
            f"n={s['n']} pass={s['pass_count']} "
            f"pass_rate={s['pass_rate']:.2f}"
        )


def cmd_score_only(args):
    """Score actual output against expected output."""
    from eval.metrics_hermes import score_action_extraction

    with open(args.actual_json, encoding="utf-8") as f:
        actual = json.load(f)

    with open(args.expected_json, encoding="utf-8") as f:
        expected = json.load(f)

    result = score_action_extraction(actual, expected)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def main():
    """Main entry point with subcommand dispatch."""
    p = argparse.ArgumentParser(
        description="Sprint 29 evaluation harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    sub = p.add_subparsers(dest="cmd", required=True, help="Available commands")

    # export-phoenix subcommand
    export_p = sub.add_parser(
        "export-phoenix",
        help="Export traces from Phoenix to scenario JSON",
    )
    export_p.add_argument(
        "--url",
        required=True,
        help="Phoenix server URL (e.g. http://localhost:6006)",
    )
    export_p.add_argument(
        "--output",
        required=True,
        help="Output JSON file path",
    )
    export_p.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of traces to export (default: 100)",
    )
    export_p.add_argument(
        "--failure-only",
        action="store_true",
        help="Export only failed traces",
    )
    export_p.set_defaults(func=cmd_export_phoenix)

    # run-scenarios subcommand
    run_p = sub.add_parser(
        "run-scenarios",
        help="Run chat evaluation against scenario file",
    )
    run_p.add_argument(
        "scenarios",
        help="Scenario JSON file path",
    )
    run_p.add_argument(
        "--db",
        help="SQLite database path (optional override)",
    )
    run_p.add_argument(
        "--json-summary",
        action="store_true",
        help="Output summary as JSON",
    )
    run_p.set_defaults(func=cmd_run_scenarios)

    # score-only subcommand
    score_p = sub.add_parser(
        "score-only",
        help="Score actual output against expected output",
    )
    score_p.add_argument(
        "--actual-json",
        required=True,
        help="Actual output JSON file",
    )
    score_p.add_argument(
        "--expected-json",
        required=True,
        help="Expected output JSON file",
    )
    score_p.set_defaults(func=cmd_score_only)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
