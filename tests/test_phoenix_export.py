"""Tests for eval.phoenix_export module.

Test scenarios:
1. group_spans_by_trace groups correctly across mixed traces
2. extract_scenarios picks chat span + tool spans
3. extract_scenarios failure_only filters to ERROR-only traces
4. extract_scenarios skips traces without a chat.post_user_message root
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from eval.phoenix_export import (  # noqa: E402
    extract_scenarios,
    export_traces_to_scenarios,
    fetch_spans,
    group_spans_by_trace,
)


class TestGroupSpansByTrace(unittest.TestCase):
    """Test trace grouping functionality."""

    def test_groups_spans_by_trace_id(self) -> None:
        """Test that spans are correctly grouped by trace_id."""
        spans = [
            {
                "name": "chat.post_user_message",
                "context": {"trace_id": "trace-1"},
                "start_time": "2025-01-01T10:00:00Z",
                "attributes": {"input": "hello"},
            },
            {
                "name": "tool.search",
                "context": {"trace_id": "trace-1"},
                "start_time": "2025-01-01T10:00:01Z",
                "attributes": {},
            },
            {
                "name": "chat.post_user_message",
                "context": {"trace_id": "trace-2"},
                "start_time": "2025-01-01T10:00:02Z",
                "attributes": {"input": "world"},
            },
        ]

        result = group_spans_by_trace(spans)

        self.assertEqual(len(result), 2)
        self.assertIn("trace-1", result)
        self.assertIn("trace-2", result)
        self.assertEqual(len(result["trace-1"]), 2)
        self.assertEqual(len(result["trace-2"]), 1)

    def test_skips_spans_without_trace_id(self) -> None:
        """Test that spans without trace_id are skipped."""
        spans = [
            {
                "name": "chat.post_user_message",
                "context": {"trace_id": "trace-1"},
                "start_time": "2025-01-01T10:00:00Z",
                "attributes": {},
            },
            {
                "name": "orphan_span",
                "context": {},
                "start_time": "2025-01-01T10:00:01Z",
                "attributes": {},
            },
        ]

        result = group_spans_by_trace(spans)

        self.assertEqual(len(result), 1)
        self.assertIn("trace-1", result)

    def test_sorts_spans_by_start_time(self) -> None:
        """Test that spans within a trace are sorted by start_time."""
        spans = [
            {
                "name": "tool.search",
                "context": {"trace_id": "trace-1"},
                "start_time": "2025-01-01T10:00:02Z",
                "attributes": {},
            },
            {
                "name": "chat.post_user_message",
                "context": {"trace_id": "trace-1"},
                "start_time": "2025-01-01T10:00:00Z",
                "attributes": {},
            },
            {
                "name": "llm.call",
                "context": {"trace_id": "trace-1"},
                "start_time": "2025-01-01T10:00:01Z",
                "attributes": {},
            },
        ]

        result = group_spans_by_trace(spans)
        trace_spans = result["trace-1"]

        self.assertEqual(trace_spans[0]["name"], "chat.post_user_message")
        self.assertEqual(trace_spans[1]["name"], "llm.call")
        self.assertEqual(trace_spans[2]["name"], "tool.search")


class TestExtractScenarios(unittest.TestCase):
    """Test scenario extraction functionality."""

    def test_extracts_chat_span_and_tool_spans(self) -> None:
        """Test that scenarios correctly extract chat and tool spans."""
        spans = [
            {
                "name": "chat.post_user_message",
                "context": {"trace_id": "trace-1"},
                "start_time": "2025-01-01T10:00:00Z",
                "attributes": {"input": "search for python"},
            },
            {
                "name": "tool.search",
                "context": {"trace_id": "trace-1"},
                "start_time": "2025-01-01T10:00:01Z",
                "attributes": {"tool_ok": True},
            },
            {
                "name": "tool.retrieve",
                "context": {"trace_id": "trace-1"},
                "start_time": "2025-01-01T10:00:02Z",
                "attributes": {"tool_ok": True},
            },
            {
                "name": "llm.call",
                "context": {"trace_id": "trace-1"},
                "start_time": "2025-01-01T10:00:03Z",
                "attributes": {"status": "OK"},
            },
        ]

        scenarios = extract_scenarios(spans)

        self.assertEqual(len(scenarios), 1)
        scenario = scenarios[0]
        self.assertEqual(scenario["user_input"], "search for python")
        self.assertEqual(len(scenario["observed_actions"]), 2)
        self.assertEqual(scenario["observed_actions"][0]["name"], "search")
        self.assertEqual(scenario["observed_actions"][1]["name"], "retrieve")

    def test_failure_only_filters_to_error_traces(self) -> None:
        """Test that failure_only filters to traces with ERROR status."""
        spans = [
            {
                "name": "chat.post_user_message",
                "context": {"trace_id": "trace-ok"},
                "start_time": "2025-01-01T10:00:00Z",
                "attributes": {"input": "test ok"},
            },
            {
                "name": "llm.call",
                "context": {"trace_id": "trace-ok"},
                "start_time": "2025-01-01T10:00:01Z",
                "attributes": {"status": "OK"},
            },
            {
                "name": "chat.post_user_message",
                "context": {"trace_id": "trace-error"},
                "start_time": "2025-01-01T10:00:02Z",
                "attributes": {"input": "test error"},
            },
            {
                "name": "llm.call",
                "context": {"trace_id": "trace-error"},
                "start_time": "2025-01-01T10:00:03Z",
                "attributes": {"status": "ERROR"},
            },
        ]

        # Without failure_only
        all_scenarios = extract_scenarios(spans, failure_only=False)
        self.assertEqual(len(all_scenarios), 2)

        # With failure_only
        error_scenarios = extract_scenarios(spans, failure_only=True)
        self.assertEqual(len(error_scenarios), 1)
        self.assertEqual(error_scenarios[0]["id"], "phoenix-trace-er")

    def test_skips_traces_without_chat_root(self) -> None:
        """Test that traces without chat.post_user_message root are skipped."""
        spans = [
            {
                "name": "tool.search",
                "context": {"trace_id": "trace-1"},
                "start_time": "2025-01-01T10:00:00Z",
                "attributes": {},
            },
            {
                "name": "llm.call",
                "context": {"trace_id": "trace-1"},
                "start_time": "2025-01-01T10:00:01Z",
                "attributes": {"status": "OK"},
            },
            {
                "name": "chat.post_user_message",
                "context": {"trace_id": "trace-2"},
                "start_time": "2025-01-01T10:00:02Z",
                "attributes": {"input": "valid trace"},
            },
        ]

        scenarios = extract_scenarios(spans)

        # Only trace-2 should be included
        self.assertEqual(len(scenarios), 1)
        self.assertIn("trace-2", scenarios[0]["id"])

    def test_extracts_user_input_from_messages_attribute(self) -> None:
        """Test that user_input is extracted from messages attribute."""
        spans = [
            {
                "name": "chat.post_user_message",
                "context": {"trace_id": "trace-1"},
                "start_time": "2025-01-01T10:00:00Z",
                "attributes": {"messages": ["first message", "second message"]},
            },
        ]

        scenarios = extract_scenarios(spans)

        self.assertEqual(len(scenarios), 1)
        self.assertEqual(scenarios[0]["user_input"], "first message")

    def test_handles_missing_user_input(self) -> None:
        """Test that missing user_input defaults to empty string."""
        spans = [
            {
                "name": "chat.post_user_message",
                "context": {"trace_id": "trace-1"},
                "start_time": "2025-01-01T10:00:00Z",
                "attributes": {},
            },
        ]

        scenarios = extract_scenarios(spans)

        self.assertEqual(len(scenarios), 1)
        self.assertEqual(scenarios[0]["user_input"], "")

    def test_includes_tool_errors_in_observed_actions(self) -> None:
        """Test that tool errors are included in observed_actions."""
        spans = [
            {
                "name": "chat.post_user_message",
                "context": {"trace_id": "trace-1"},
                "start_time": "2025-01-01T10:00:00Z",
                "attributes": {"input": "test"},
            },
            {
                "name": "tool.search",
                "context": {"trace_id": "trace-1"},
                "start_time": "2025-01-01T10:00:01Z",
                "attributes": {"tool_error": "connection timeout"},
            },
        ]

        scenarios = extract_scenarios(spans)

        self.assertEqual(len(scenarios), 1)
        self.assertEqual(len(scenarios[0]["observed_actions"]), 1)
        self.assertEqual(scenarios[0]["observed_actions"][0]["tool_error"], "connection timeout")

    def test_llm_status_ok_by_default(self) -> None:
        """Test that llm_status is OK by default."""
        spans = [
            {
                "name": "chat.post_user_message",
                "context": {"trace_id": "trace-1"},
                "start_time": "2025-01-01T10:00:00Z",
                "attributes": {"input": "test"},
            },
        ]

        scenarios = extract_scenarios(spans)

        self.assertEqual(scenarios[0]["llm_status"], "OK")

    def test_llm_status_error_when_any_llm_call_fails(self) -> None:
        """Test that llm_status is ERROR when any llm.call has ERROR status."""
        spans = [
            {
                "name": "chat.post_user_message",
                "context": {"trace_id": "trace-1"},
                "start_time": "2025-01-01T10:00:00Z",
                "attributes": {"input": "test"},
            },
            {
                "name": "llm.call",
                "context": {"trace_id": "trace-1"},
                "start_time": "2025-01-01T10:00:01Z",
                "attributes": {"status": "OK"},
            },
            {
                "name": "llm.call",
                "context": {"trace_id": "trace-1"},
                "start_time": "2025-01-01T10:00:02Z",
                "attributes": {"status": "ERROR"},
            },
        ]

        scenarios = extract_scenarios(spans)

        self.assertEqual(scenarios[0]["llm_status"], "ERROR")


class TestExportTracesToScenarios(unittest.TestCase):
    """Test end-to-end export functionality."""

    @patch("eval.phoenix_export.fetch_spans")
    def test_end_to_end_export(self, mock_fetch: MagicMock) -> None:
        """Test end-to-end export with mocked fetch_spans."""
        mock_fetch.return_value = [
            {
                "name": "chat.post_user_message",
                "context": {"trace_id": "trace-1"},
                "start_time": "2025-01-01T10:00:00Z",
                "attributes": {"input": "hello world"},
            },
            {
                "name": "tool.search",
                "context": {"trace_id": "trace-1"},
                "start_time": "2025-01-01T10:00:01Z",
                "attributes": {"tool_ok": True},
            },
        ]

        output_file = Path("/tmp/test_scenarios.json")
        count = export_traces_to_scenarios(
            phoenix_url="http://localhost:6006",
            output_path=output_file,
            limit=100,
        )

        self.assertEqual(count, 1)
        self.assertTrue(output_file.exists())

        # Verify output content
        with open(output_file) as f:
            scenarios = json.load(f)
        self.assertEqual(len(scenarios), 1)
        self.assertEqual(scenarios[0]["user_input"], "hello world")
        self.assertEqual(scenarios[0]["source"], "phoenix-export")

        # Cleanup
        output_file.unlink()

    @patch("eval.phoenix_export.fetch_spans")
    def test_creates_output_directory(self, mock_fetch: MagicMock) -> None:
        """Test that export creates output directory if it doesn't exist."""
        mock_fetch.return_value = [
            {
                "name": "chat.post_user_message",
                "context": {"trace_id": "trace-1"},
                "start_time": "2025-01-01T10:00:00Z",
                "attributes": {"input": "test"},
            },
        ]

        output_file = Path("/tmp/test_phoenix_dir/scenarios.json")
        if output_file.parent.exists():
            import shutil
            shutil.rmtree(output_file.parent)

        count = export_traces_to_scenarios(
            phoenix_url="http://localhost:6006",
            output_path=output_file,
        )

        self.assertEqual(count, 1)
        self.assertTrue(output_file.exists())

        # Cleanup
        import shutil
        shutil.rmtree(output_file.parent)


class TestFetchSpans(unittest.TestCase):
    """Test fetch_spans functionality."""

    @patch("eval.phoenix_export.urllib.request.urlopen")
    def test_fetch_spans_success(self, mock_urlopen: MagicMock) -> None:
        """Test successful span fetching."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            [
                {"name": "span1", "context": {"trace_id": "t1"}},
                {"name": "span2", "context": {"trace_id": "t2"}},
            ]
        ).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        spans = fetch_spans(phoenix_url="http://localhost:6006", limit=100)

        self.assertEqual(len(spans), 2)
        self.assertEqual(spans[0]["name"], "span1")

    @patch("eval.phoenix_export.urllib.request.urlopen")
    def test_fetch_spans_with_data_wrapper(self, mock_urlopen: MagicMock) -> None:
        """Test span fetching when response has {'data': [...]} wrapper."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {"data": [{"name": "span1"}]}
        ).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        spans = fetch_spans()

        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0]["name"], "span1")

    @patch("eval.phoenix_export.urllib.request.urlopen")
    def test_fetch_spans_http_error(self, mock_urlopen: MagicMock) -> None:
        """Test that HTTP errors raise RuntimeError."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "http://test", 404, "Not Found", {}, None
        )

        with self.assertRaises(RuntimeError):
            fetch_spans()


if __name__ == "__main__":
    unittest.main()
