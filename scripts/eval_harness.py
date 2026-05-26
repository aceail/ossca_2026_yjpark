"""G009 v1 EvaluationHarness — 9차원 자동 메트릭 + EXAONE Witty 회귀.

30 골든 샘플로 시나리오 카드 생성 → 메트릭 → markdown + JSON 결과.
Strict 위반 시 exit 1 (CI fail).

Usage:
    python3 scripts/eval_harness.py [--model exaone3.5:7.8b] [--samples .omc/ultragoal/golden_samples_v1.json]
Outputs:
    .omc/ultragoal/eval_v1_results.md
    .omc/ultragoal/eval_v1_summary.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

SECOND_PERSON_RE = re.compile(r"(너는|너가|당신은|당신이|당신을|당신의)\s")

FORBIDDEN_GROUPS: dict[str, list[str]] = {
    "한국 가스라이팅": ["의지", "노력", "한심", "정상", "게으름", "정신 차려"],
    "정체성 결함": ["도태", "조졌", "어차피", "또 이런 식", "원래 그런"],
    "비교 수치심": ["다른 사람", "다른 애들", "남들은", "남들"],
    "한국형 트리거": ["효도", "체면", "부모 실망", "병역", "취업", "학벌", "부모 기대", "외모", "체중", "연애 실패"],
    "욕설": ["씨발", "좆", "존나"],
    "위로 무력화": ["괜찮아", "괜찮다", "괜찮을", "여유롭게", "천천히", "급하지 않", "지 않아도"],
}

TIME_RE = re.compile(r"\d+시\s*\d+분|\d+시간\s*\d+분|\d+분(?:\s|남|후|이$)|\d+시(?:\s|에|,|$)")
DECISIVE_ENDING_RE = re.compile(r"(켠다|쓴다|친다|보낸다|연다|연다\.?|시작한다|시작\.?$|읽는다|마신다|먹는다|건다|친다\.?|치자|편다|편다\.?|편다\.?$|올린다|넘긴다|기록한다)\s*[\.\!]?\s*$")
NON_HANGUL_ETC_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\u0400-\u04ff]")

SYSTEM_PROMPT_WITTY = """당신은 "내일의 너" 도구의 미래 자아 시뮬레이터입니다. 톤은 "팩트폭격 + 유쾌" — 위로하지 않고 사실과 결과를 두드리듯 직시하되, 미래 자아 1인칭 시점의 위트 있는 자기 풍자 포함.

# 절대 규칙

1. 1인칭 화법만. "너는"/"당신은" 금지.
2. 3단 구조 (총 80-150자):
   - fact: 구체 시각·분·숫자·누적 결과로 직시. 마감 정보가 있으면 분 단위까지 박는다.
   - feeling: 미래 자아가 마주할 구체 장면. 위로형 어휘 금지.
   - micro_action: 단호한 명령형 종결("켠다", "쓴다", "친다", "보낸다", "연다", "편다", "마신다", "기록한다" 등). 제안형 금지.
3. 유쾌 = 1인칭 자기 풍자만. 외부 비웃음/비교/정체성 결함 금지.
4. 위로 차단 금지 어구: "괜찮아/괜찮다/여유롭게/천천히/조금 ~이지만 ~/지 않아도".
5. 절대 금지어: 의지·노력·한심·정상·게으름·정신 차려·도태·조졌·다른 사람·다른 애들·남들·효도·체면·부모 실망·병역·취업·학벌·외모·체중·연애 실패·씨발·좆·존나.
6. 금지 톤: 도덕적 훈계, 공포 극대화, 외부 냉소, 제3자 비교.
7. recovery 모드: 사용자 입력이 "정서적 허기·번아웃·신체 통증·우울감"이면 팩트폭격 X, 차분한 인정 톤 + 작은 운동성.
8. soft_stop 모드: 자해·자살·"진짜 죽고 싶다·약통" 같은 명확한 위기 키워드가 있으면 시나리오 생성 X. {"card_type":"soft_stop","message":"지금 문장은 평소보다 강한 고통 신호로 읽힙니다. 오늘은 후회 시나리오 대신 부담 낮은 응답으로 전환할게요."}

# 출력 (JSON 한 줄, 코드 블록 금지)

regret/recovery:
{"card_type":"regret","sentences":{"fact":"...","feeling":"...","micro_action":"..."}}

soft_stop:
{"card_type":"soft_stop","message":"..."}

JSON만 출력하시오. 다른 텍스트 일체 금지."""


@dataclass
class Sample:
    id: str
    persona_context: str
    category: str
    avoidance_input: str
    profile_summary: str
    timeline_hint: str
    expected_mode: str
    expected_card_type: str
    metric_overrides: dict = field(default_factory=dict)


@dataclass
class CardMetrics:
    json_valid: bool = False
    three_sentences: bool = False
    second_person_hits: list[str] = field(default_factory=list)
    forbidden_hits: dict[str, list[str]] = field(default_factory=dict)
    total_chars: int = 0
    in_length_range: bool = False
    has_time_specific: bool = False
    comfort_phrases: list[str] = field(default_factory=list)
    decisive_ending: bool = False
    non_hangul_hits: list[str] = field(default_factory=list)
    card_type: str | None = None
    raw_response: str = ""
    parsed: dict | None = None


def load_samples(path: Path) -> list[Sample]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        Sample(
            id=s["id"],
            persona_context=s["persona_context"],
            category=s["category"],
            avoidance_input=s["avoidance_input"],
            profile_summary=s["profile_summary"],
            timeline_hint=s["timeline_hint"],
            expected_mode=s["expected_mode"],
            expected_card_type=s["expected_card_type"],
            metric_overrides=s.get("metric_overrides", {}),
        )
        for s in data["samples"]
    ]


def call_ollama(model: str, system_prompt: str, user_prompt: str, timeout: int = 90) -> tuple[str, float, str | None]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"num_predict": 500, "temperature": 0.7, "top_p": 0.9},
    }
    req = urllib.request.Request(OLLAMA_URL, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
        return body.get("message", {}).get("content", ""), time.time() - t0, None
    except Exception as exc:
        return "", time.time() - t0, str(exc)


def build_user_prompt(s: Sample) -> str:
    return (
        f"회피 상황: {s.avoidance_input}\n"
        f"UserProfile: {s.profile_summary}\n"
        f"TIMELINE: {s.timeline_hint}\n"
        f"모드: {s.expected_mode}\n\n"
        "JSON 한 줄로 출력. /no_think"
    )


def extract_json(text: str) -> dict | None:
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    m = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def compute_metrics(s: Sample, raw: str) -> CardMetrics:
    metrics = CardMetrics(raw_response=raw)
    parsed = extract_json(raw)
    if not parsed:
        return metrics
    metrics.parsed = parsed
    metrics.json_valid = True
    metrics.card_type = parsed.get("card_type")
    if metrics.card_type == "soft_stop":
        return metrics
    sentences = parsed.get("sentences", {}) if isinstance(parsed, dict) else {}
    fact = (sentences.get("fact") or "").strip()
    feeling = (sentences.get("feeling") or "").strip()
    action = (sentences.get("micro_action") or "").strip()
    body = " ".join([fact, feeling, action])
    metrics.three_sentences = bool(fact and feeling and action)
    metrics.second_person_hits = [m.group(1) for m in SECOND_PERSON_RE.finditer(body)]
    for group, words in FORBIDDEN_GROUPS.items():
        hits = [w for w in words if w in body]
        if hits:
            metrics.forbidden_hits[group] = hits
    metrics.total_chars = sum(len(x) for x in (fact, feeling, action))
    metrics.in_length_range = 80 <= metrics.total_chars <= 150
    metrics.has_time_specific = bool(TIME_RE.search(fact))
    metrics.comfort_phrases = [k for grp, ws in FORBIDDEN_GROUPS.items() if grp == "위로 무력화" for k in ws if k in body]
    metrics.decisive_ending = bool(DECISIVE_ENDING_RE.search(action))
    metrics.non_hangul_hits = list(set(NON_HANGUL_ETC_RE.findall(body)))
    return metrics


def evaluate(sample: Sample, metrics: CardMetrics) -> dict:
    overrides = sample.metric_overrides or {}
    skipped = set(overrides.get("skip_dimensions", []))
    is_regret = sample.expected_mode == "regret"
    issues: list[str] = []
    if not metrics.json_valid:
        issues.append("D1: JSON invalid")
    if sample.expected_card_type == "soft_stop":
        if metrics.card_type != "soft_stop":
            issues.append(f"soft_stop expected, got '{metrics.card_type}'")
        return {"pass": not issues, "issues": issues, "metrics": metrics}
    if not metrics.three_sentences:
        issues.append("D2: 3-sentences missing")
    if 3 not in skipped and metrics.second_person_hits:
        issues.append(f"D3: 1인칭 위반 {metrics.second_person_hits}")
    if metrics.forbidden_hits:
        issues.append(f"D4: 금지어 {metrics.forbidden_hits}")
    if 5 not in skipped and not metrics.in_length_range:
        issues.append(f"D5: 길이 {metrics.total_chars}자")
    if is_regret and 6 not in skipped and not metrics.has_time_specific:
        issues.append("D6: 시간 구체화 부재")
    if is_regret and 7 not in skipped and metrics.comfort_phrases:
        issues.append(f"D7: 위로 어휘 {metrics.comfort_phrases}")
    if is_regret and 8 not in skipped and not metrics.decisive_ending:
        issues.append("D8: 단호 종결 부재")
    if metrics.non_hangul_hits:
        issues.append(f"D9: 외래 문자 {metrics.non_hangul_hits}")
    return {"pass": not issues, "issues": issues, "metrics": metrics}


def render_md(model: str, rows: list[dict]) -> str:
    total = len(rows)
    json_ok = sum(1 for r in rows if r["metrics"].json_valid)
    three_ok = sum(1 for r in rows if r["metrics"].three_sentences)
    sp_total = sum(len(r["metrics"].second_person_hits) for r in rows)
    fb_cards = sum(1 for r in rows if r["metrics"].forbidden_hits)
    len_ok = sum(1 for r in rows if r["metrics"].in_length_range)
    regret_rows = [r for r in rows if r["sample"].expected_mode == "regret"]
    time_ok = sum(1 for r in regret_rows if r["metrics"].has_time_specific)
    comfort_cards = sum(1 for r in regret_rows if r["metrics"].comfort_phrases)
    decisive_ok = sum(1 for r in regret_rows if r["metrics"].decisive_ending)
    non_hangul_cards = sum(1 for r in rows if r["metrics"].non_hangul_hits)
    avg_lat = sum(r["latency"] for r in rows) / total if total else 0.0
    pass_count = sum(1 for r in rows if r["eval"]["pass"])

    lines = [
        f"# G009 v1 EvaluationHarness Results — {model}",
        "",
        f"**Date**: 2026-05-26  **Total**: {total}  **Pass**: {pass_count}/{total}  **Avg latency**: {avg_lat:.2f}s",
        "",
        "## 9 차원 메트릭 요약",
        "",
        "| # | 차원 | 통과 | 임계 | 판정 |",
        "|---|---|---|---|---|",
        f"| 1 | JSON 유효성 | {json_ok}/{total} | 30/30 | {'✅' if json_ok==total else '❌'} |",
        f"| 2 | 3문장 완비 | {three_ok}/{total} | 30/30 | {'✅' if three_ok==total else '❌'} |",
        f"| 3 | 1인칭 위반 (낮을수록 좋음) | {sp_total}건 | 0 | {'✅' if sp_total==0 else '❌'} |",
        f"| 4 | 금지어 위반 카드 (낮을수록 좋음) | {fb_cards}건 | 0 | {'✅' if fb_cards==0 else '❌'} |",
        f"| 5 | 길이 80-150자 | {len_ok}/{total} | ≥80%({int(total*0.8)}) | {'✅' if len_ok>=int(total*0.8) else '❌'} |",
        f"| 6 | 시간 구체화 (regret only) | {time_ok}/{len(regret_rows)} | ≥90%({int(len(regret_rows)*0.9)}) | {'✅' if time_ok>=int(len(regret_rows)*0.9) else '❌'} |",
        f"| 7 | 위로 어휘 (낮을수록 좋음, regret only) | {comfort_cards}건 | 0 | {'✅' if comfort_cards==0 else '❌'} |",
        f"| 8 | 단호 종결 (regret only) | {decisive_ok}/{len(regret_rows)} | ≥80%({int(len(regret_rows)*0.8)}) | {'✅' if decisive_ok>=int(len(regret_rows)*0.8) else '❌'} |",
        f"| 9 | 외래 문자 누출 카드 (낮을수록 좋음) | {non_hangul_cards}건 | 0 | {'✅' if non_hangul_cards==0 else '❌'} |",
        "",
        "## 실패 카드 상세",
        "",
    ]
    failures = [r for r in rows if not r["eval"]["pass"]]
    if not failures:
        lines.append("_없음 — 모든 카드가 통과했습니다._")
    for r in failures:
        s, m = r["sample"], r["metrics"]
        lines.append(f"### ❌ {s.id} — {s.persona_context} / {s.category} ({s.expected_mode})")
        lines.append(f"- issues: {r['eval']['issues']}")
        if m.parsed:
            sents = m.parsed.get("sentences", {})
            lines.append(f"- fact: {sents.get('fact','')}")
            lines.append(f"- feeling: {sents.get('feeling','')}")
            lines.append(f"- micro_action: {sents.get('micro_action','')}")
        else:
            lines.append(f"- raw (truncated): `{m.raw_response[:300]}`")
        lines.append("")
    return "\n".join(lines)


def build_summary(model: str, rows: list[dict]) -> dict:
    total = len(rows)
    return {
        "model": model,
        "date": "2026-05-26",
        "total": total,
        "pass_count": sum(1 for r in rows if r["eval"]["pass"]),
        "metrics": {
            "json_valid": sum(1 for r in rows if r["metrics"].json_valid),
            "three_sentences": sum(1 for r in rows if r["metrics"].three_sentences),
            "second_person_violations": sum(len(r["metrics"].second_person_hits) for r in rows),
            "forbidden_cards": sum(1 for r in rows if r["metrics"].forbidden_hits),
            "in_length_range": sum(1 for r in rows if r["metrics"].in_length_range),
            "time_specific_regret": sum(1 for r in rows if r["sample"].expected_mode == "regret" and r["metrics"].has_time_specific),
            "regret_total": sum(1 for r in rows if r["sample"].expected_mode == "regret"),
            "comfort_cards_regret": sum(1 for r in rows if r["sample"].expected_mode == "regret" and r["metrics"].comfort_phrases),
            "decisive_ending_regret": sum(1 for r in rows if r["sample"].expected_mode == "regret" and r["metrics"].decisive_ending),
            "non_hangul_cards": sum(1 for r in rows if r["metrics"].non_hangul_hits),
        },
        "avg_latency_s": sum(r["latency"] for r in rows) / total if total else 0.0,
        "failures": [
            {"id": r["sample"].id, "issues": r["eval"]["issues"]} for r in rows if not r["eval"]["pass"]
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="exaone3.5:7.8b")
    parser.add_argument("--samples", default=str(PROJECT_ROOT / ".omc" / "ultragoal" / "golden_samples_v1.json"))
    parser.add_argument("--out-md", default=str(PROJECT_ROOT / ".omc" / "ultragoal" / "eval_v1_results.md"))
    parser.add_argument("--out-json", default=str(PROJECT_ROOT / ".omc" / "ultragoal" / "eval_v1_summary.json"))
    parser.add_argument("--strict", action="store_true", help="CI mode: exit 1 if strict violations")
    args = parser.parse_args()

    samples = load_samples(Path(args.samples))
    rows: list[dict] = []
    for i, s in enumerate(samples, 1):
        print(f"[{i}/{len(samples)}] {s.id}", flush=True)
        raw, latency, err = call_ollama(args.model, SYSTEM_PROMPT_WITTY, build_user_prompt(s))
        metrics = compute_metrics(s, raw)
        ev = evaluate(s, metrics)
        rows.append({"sample": s, "metrics": metrics, "latency": latency, "error": err, "eval": ev})

    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text(render_md(args.model, rows), encoding="utf-8")
    Path(args.out_json).write_text(json.dumps(build_summary(args.model, rows), indent=2, ensure_ascii=False), encoding="utf-8")

    summary = build_summary(args.model, rows)
    fails = len(summary["failures"])
    print(f"\nPass: {summary['pass_count']}/{summary['total']}  Failures: {fails}")
    print(f"Saved: {args.out_md}")
    print(f"Saved: {args.out_json}")

    if args.strict and fails > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
