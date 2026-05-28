"""Phoenix trace → scenarios exporter.

Query Phoenix's REST API to extract chat traces and convert them into scenarios.json.
Each trace becomes a scenario with user_input, observed_actions, and llm_status.

Public surface:
- fetch_spans(phoenix_url, project, limit) -> list[dict]
- group_spans_by_trace(spans) -> dict[str, list[dict]]
- extract_scenarios(spans, failure_only) -> list[dict]
- export_traces_to_scenarios(phoenix_url, output_path, *, limit, failure_only) -> int
- main() — CLI entry point
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def fetch_spans(
    phoenix_url: str = "http://localhost:6006",
    project: str = "default",
    limit: int = 100,
) -> list[dict]:
    """GET {phoenix_url}/v1/projects/{project}/spans?limit={limit}&sort=-start_time.

    Return list of span dicts. Raises RuntimeError on HTTP error.
    """
    url = f"{phoenix_url}/v1/projects/{project}/spans"
    params = {"limit": str(limit), "sort": "-start_time"}
    query_string = urllib.parse.urlencode(params)
    full_url = f"{url}?{query_string}"

    try:
        with urllib.request.urlopen(full_url, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            # Phoenix API returns {"data": [spans...]} or just [spans...]
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            return data
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        raise RuntimeError(f"Failed to fetch spans from {full_url}: {e}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON response from {full_url}: {e}") from e


def group_spans_by_trace(spans: list[dict]) -> dict[str, list[dict]]:
    """Group spans by context.trace_id.

    Returns {trace_id: [spans...]} sorted by start_time within each trace.
    """
    trace_map: dict[str, list[dict]] = {}

    for span in spans:
        # Extract trace_id from context (nested structure)
        context = span.get("context", {})
        trace_id = context.get("trace_id")

        if not trace_id:
            # Skip spans without trace_id
            continue

        if trace_id not in trace_map:
            trace_map[trace_id] = []
        trace_map[trace_id].append(span)

    # Sort spans within each trace by start_time
    for spans_in_trace in trace_map.values():
        spans_in_trace.sort(key=lambda s: s.get("start_time", ""))

    return trace_map


def extract_scenarios(
    spans: list[dict], failure_only: bool = False
) -> list[dict]:
    """Walk grouped span trees and extract scenarios.

    For each trace with a chat.post_user_message root, extract:
      - user_input: from input/messages attribute or chat span input (best-effort)
      - observed_actions: built from tool.* span attributes (name + tool_ok + tool_error)
      - llm_status: ERROR | OK based on llm.call span statuses
    Returns scenario dicts:
      {"id": f"phoenix-{trace_id[:8]}", "user_input": str,
       "observed_actions": [...], "source": "phoenix-export"}
    failure_only: if True, only include traces where at least one llm.call had ERROR status.
    """
    grouped = group_spans_by_trace(spans)
    scenarios: list[dict] = []

    for trace_id, trace_spans in grouped.items():
        # Find the root span (chat.post_user_message)
        root_span = None
        for span in trace_spans:
            span_name = span.get("name", "")
            if span_name == "chat.post_user_message":
                root_span = span
                break

        if not root_span:
            # Skip traces without a chat.post_user_message root
            continue

        # Extract user_input from root span
        user_input = None
        span_attributes = root_span.get("attributes", {})

        # Try input/messages attribute first
        if "input" in span_attributes:
            user_input = span_attributes["input"]
        elif "messages" in span_attributes:
            messages = span_attributes["messages"]
            if isinstance(messages, list) and messages:
                user_input = messages[0] if isinstance(messages[0], str) else str(messages[0])
        else:
            # Fallback: use span input field
            user_input = root_span.get("input")

        if not user_input:
            user_input = ""

        # Extract observed_actions from tool.* spans
        observed_actions: list[dict] = []
        for span in trace_spans:
            span_name = span.get("name", "")
            if span_name.startswith("tool."):
                tool_name = span_name[5:]  # Remove "tool." prefix
                span_attrs = span.get("attributes", {})
                action: dict = {"name": tool_name}

                if "tool_ok" in span_attrs:
                    action["tool_ok"] = span_attrs["tool_ok"]
                if "tool_error" in span_attrs:
                    action["tool_error"] = span_attrs["tool_error"]

                observed_actions.append(action)

        # Determine llm_status: ERROR if any llm.call has error, else OK
        llm_status = "OK"
        for span in trace_spans:
            span_name = span.get("name", "")
            if span_name == "llm.call":
                span_attrs = span.get("attributes", {})
                status_attr = span_attrs.get("status", "")
                if status_attr == "ERROR":
                    llm_status = "ERROR"
                    break

        # Filter by failure_only if requested
        if failure_only and llm_status != "ERROR":
            continue

        # Create scenario
        scenario: dict = {
            "id": f"phoenix-{trace_id[:8]}",
            "user_input": user_input,
            "observed_actions": observed_actions,
            "llm_status": llm_status,
            "source": "phoenix-export",
        }
        scenarios.append(scenario)

    return scenarios


def export_traces_to_scenarios(
    phoenix_url: str,
    output_path: str | Path,
    *,
    limit: int = 100,
    failure_only: bool = False,
) -> int:
    """End-to-end: fetch_spans -> group_spans_by_trace -> extract_scenarios -> json.dump.

    Returns number of scenarios written.
    """
    # Fetch spans from Phoenix
    spans = fetch_spans(phoenix_url=phoenix_url, limit=limit)

    # Extract scenarios
    scenarios = extract_scenarios(spans, failure_only=failure_only)

    # Write to output file
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(scenarios, f, indent=2)

    return len(scenarios)


def main() -> None:
    """argparse entry: python -m eval.phoenix_export --url ... --output ... --limit N --failure-only"""
    parser = argparse.ArgumentParser(
        description="Export Phoenix traces to scenarios.json"
    )
    parser.add_argument(
        "--url",
        default="http://localhost:6006",
        help="Phoenix server URL (default: http://localhost:6006)",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output path for scenarios.json",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Max spans to fetch (default: 100)",
    )
    parser.add_argument(
        "--failure-only",
        action="store_true",
        help="Only include traces with LLM errors",
    )

    args = parser.parse_args()

    try:
        count = export_traces_to_scenarios(
            phoenix_url=args.url,
            output_path=args.output,
            limit=args.limit,
            failure_only=args.failure_only,
        )
        print(f"Exported {count} scenarios to {args.output}")
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
