"""Hermes 챗 에이전트 액션/포맷 채점 메트릭.

score_action_extraction: 추출된 액션 vs 기대 액션 비교
score_response_format: JSON 타당성 + thinking leak 여부 검사
summarize_metrics: 샘플별 메트릭 집계
"""

from __future__ import annotations

import json
from datetime import datetime, timezone


def score_action_extraction(actual: list[dict], expected: list[dict]) -> dict:
    """Score actual vs expected actions.

    Match semantics per expected[i]:
      - title_contains: case-insensitive substring check on actual[i]['title']
      - deadline_starts_with: actual[i]['deadline'] startswith this prefix
        (actual deadline may be 'YYYY-MM-DDTHH:MM:SS+09:00'; compare on
        the date prefix before 'T')
      - folder_contains: substring check on actual[i]['folder_path']
      - status_equals: equality on actual[i]['status']
      - relative_deadline_offset: int — expected deadline is today+N (KST date)
      - type: actual[i]['type'] == expected[i]['type']

    Returns:
      {
        "count_match": bool,                # len(actual) == len(expected)
        "type_match_rate": float,           # frac of expected with type matched
        "field_match_rate": float,          # mean across expected of field match
        "tool_call_accuracy": float,        # 1.0 if all expected fields matched, else 0.0
        "passed": bool,                     # tool_call_accuracy == 1.0
      }
    """
    count_match = len(actual) == len(expected)

    if not expected:
        # If no expected actions, tool_call_accuracy is 1.0 only if actual is also empty
        tool_call_accuracy = 1.0 if not actual else 0.0
        return {
            "count_match": count_match,
            "type_match_rate": 1.0,
            "field_match_rate": 1.0,
            "tool_call_accuracy": tool_call_accuracy,
            "passed": tool_call_accuracy == 1.0,
        }

    type_matches = 0
    field_matches = []

    for exp in expected:
        # Find matching actual action by type and title
        matched_actual = None
        exp_type = exp.get("type")
        exp_title = exp.get("title", "")

        for act in actual:
            if act.get("type") == exp_type:
                # Check title_contains match
                if exp_title.lower() in act.get("title", "").lower():
                    matched_actual = act
                    break

        if not matched_actual:
            # No match found for this expected action
            field_matches.append(0.0)
            continue

        # Count type match
        if matched_actual.get("type") == exp_type:
            type_matches += 1

        # Count field matches for this expected action
        fields_checked = 0
        fields_matched = 0

        # title_contains
        if "title_contains" in exp:
            fields_checked += 1
            if exp["title_contains"].lower() in matched_actual.get("title", "").lower():
                fields_matched += 1

        # deadline_starts_with
        if "deadline_starts_with" in exp:
            fields_checked += 1
            actual_deadline = matched_actual.get("deadline")
            if actual_deadline:
                # Extract date prefix (before 'T')
                actual_date = actual_deadline.split("T")[0] if "T" in actual_deadline else actual_deadline
                if actual_date.startswith(exp["deadline_starts_with"]):
                    fields_matched += 1

        # folder_contains
        if "folder_contains" in exp:
            fields_checked += 1
            if exp["folder_contains"] in matched_actual.get("folder_path", ""):
                fields_matched += 1

        # status_equals
        if "status_equals" in exp:
            fields_checked += 1
            if matched_actual.get("status") == exp["status_equals"]:
                fields_matched += 1

        # relative_deadline_offset
        if "relative_deadline_offset" in exp:
            fields_checked += 1
            offset = exp["relative_deadline_offset"]
            expected_date = _date_from_offset(offset)
            actual_deadline = matched_actual.get("deadline")
            if actual_deadline:
                actual_date = actual_deadline.split("T")[0] if "T" in actual_deadline else actual_deadline
                if actual_date == expected_date:
                    fields_matched += 1

        # type
        if "type" in exp:
            fields_checked += 1
            if matched_actual.get("type") == exp["type"]:
                fields_matched += 1

        # If no fields to check, assume perfect match
        if fields_checked == 0:
            field_matches.append(1.0)
        else:
            field_matches.append(fields_matched / fields_checked)

    # Calculate rates
    type_match_rate = type_matches / len(expected) if expected else 1.0
    field_match_rate = sum(field_matches) / len(field_matches) if field_matches else 1.0

    # tool_call_accuracy: 1.0 only if all expected actions have 100% field match
    tool_call_accuracy = 1.0 if all(m == 1.0 for m in field_matches) and count_match else 0.0

    return {
        "count_match": count_match,
        "type_match_rate": type_match_rate,
        "field_match_rate": field_match_rate,
        "tool_call_accuracy": tool_call_accuracy,
        "passed": tool_call_accuracy == 1.0,
    }


def score_response_format(content: str) -> dict:
    """Score response format: JSON validity and thinking leak.

    Returns {"json_valid": bool, "no_thinking_leak": bool, "passed": bool}.

    json_valid: content contains a parseable {...} block (use json.loads on
    the substring from first '{' to last '}').
    no_thinking_leak: content does NOT start (after stripping whitespace)
    with any of these prefixes: 'Okay', 'Let me', 'I need to', '<think>',
    'First, ', 'The user', 'Looking at'.
    passed: json_valid AND no_thinking_leak.
    """
    json_valid = False
    no_thinking_leak = True

    # Check JSON validity
    stripped = content.strip()
    try:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            json_str = stripped[start : end + 1]
            json.loads(json_str)
            json_valid = True
    except (json.JSONDecodeError, ValueError):
        json_valid = False

    # Check for thinking leak
    thinking_leak_prefixes = (
        "Okay",
        "Let me",
        "I need to",
        "<think>",
        "First, ",
        "The user",
        "Looking at",
    )
    if stripped and any(stripped.startswith(prefix) for prefix in thinking_leak_prefixes):
        no_thinking_leak = False

    passed = json_valid and no_thinking_leak

    return {
        "json_valid": json_valid,
        "no_thinking_leak": no_thinking_leak,
        "passed": passed,
    }


def summarize_metrics(per_sample: list[dict]) -> dict:
    """Aggregate per-sample dicts that have shape
    {"extraction": {...}, "format": {...}}.

    Returns:
      {
        "n": int,
        "pass_count": int,                    # samples with extraction.tool_call_accuracy == 1.0
        "pass_rate": float,
        "avg_field_match_rate": float,
        "format_compliance_rate": float,      # frac with both json_valid AND no_thinking_leak
      }
    """
    n = len(per_sample)
    if n == 0:
        return {
            "n": 0,
            "pass_count": 0,
            "pass_rate": 0.0,
            "avg_field_match_rate": 0.0,
            "format_compliance_rate": 0.0,
        }

    pass_count = 0
    field_match_rates = []
    format_compliant = 0

    for sample in per_sample:
        extraction = sample.get("extraction", {})
        format_score = sample.get("format", {})

        # Count passes (tool_call_accuracy == 1.0)
        if extraction.get("tool_call_accuracy") == 1.0:
            pass_count += 1

        # Collect field match rates
        field_match_rates.append(extraction.get("field_match_rate", 0.0))

        # Count format compliance (json_valid AND no_thinking_leak)
        if format_score.get("json_valid") and format_score.get("no_thinking_leak"):
            format_compliant += 1

    pass_rate = pass_count / n if n > 0 else 0.0
    avg_field_match_rate = sum(field_match_rates) / len(field_match_rates) if field_match_rates else 0.0
    format_compliance_rate = format_compliant / n if n > 0 else 0.0

    return {
        "n": n,
        "pass_count": pass_count,
        "pass_rate": pass_rate,
        "avg_field_match_rate": avg_field_match_rate,
        "format_compliance_rate": format_compliance_rate,
    }


def _date_from_offset(offset: int) -> str:
    """Return YYYY-MM-DD date for today + offset days (KST timezone)."""
    # Use KST (UTC+9) for date calculation
    kst = timezone(timezone.utc.utcoffset(None))
    try:
        from zoneinfo import ZoneInfo
        kst = ZoneInfo("Asia/Seoul")
    except ImportError:
        pass

    now = datetime.now(tz=kst)
    target = now.replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta
    target += timedelta(days=offset)
    return target.strftime("%Y-%m-%d")
