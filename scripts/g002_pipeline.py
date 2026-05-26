"""G002 PoC pipeline — 4 models x 5 avoidance samples = 20 scenario cards.

각 모델로 시나리오 카드를 생성하고 자동 메트릭(1인칭 위반·금지어·JSON·길이·30초 운동성)을 계산해 마크다운으로 정리한다.

Usage:
    python3 scripts/g002_pipeline.py [output_md]
Output: .omc/ultragoal/g002_results_v1.md (기본)
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

MODELS: list[str] = [
    "qwen3:1.7b",
    "exaone3.5:7.8b",
    "qwen3:8b",
    "qwen3:14b",
]

SECOND_PERSON_PATTERNS: list[str] = ["너는 ", "너가 ", "당신은 ", "당신이 ", "당신을 ", "당신의 "]

FORBIDDEN_WORDS: list[str] = [
    "의지", "노력", "한심", "정상", "게으름", "정신 차려",
    "효도", "체면", "부모 실망", "연인 비교",
    "병역", "취업", "학벌", "부모 기대",
    "외모", "체중", "연애 실패",
]

SYSTEM_PROMPT = """당신은 "내일의 너" 도구의 미래 자아 시뮬레이터입니다.
사용자의 회피 상황과 UserProfile이 주어지면, 30분~24시간 후 미래 자아가
1인칭 시점으로 자기 경험을 말하는 시나리오 카드를 생성합니다.

# 절대 규칙 — 모두 어겨선 안 됩니다

1. 1인칭 화법만 사용
   - 허용: "나는", "내가", "내일 아침의 나는"
   - 금지: "너는", "당신은", "당신이"
   - 미래 자아가 사용자 자신에게 말하는 자기-자기 대화 형식.

2. 3단 구조 엄수 (한국어, 총 80-150자)
   - fact 문장: 지금 미래 자아의 상태 (객관적 묘사)
   - feeling 문장: 미래 자아의 한 가지 감정 (자기 비난 금지)
   - micro_action 문장: 현재 사용자가 30초 이내에 할 수 있는 단 하나의 첫 동작

3. 절대 금지어 (어떤 활용형으로도 사용 금지)
   - 의지, 노력, 한심, 정상, 게으름, 정신 차려
   - 효도, 체면, 부모 실망, 연인 비교
   - 병역, 취업, 학벌, 부모 기대, 외모, 체중, 연애 실패

4. 금지 톤: 도덕적 훈계, 공포 극대화, 냉소적 비아냥. 사실+결과만 묘사.

# 출력은 반드시 다음 JSON 형식만 (코드 블록도 ``` 도 쓰지 말 것):

{"card_type":"regret","sentences":{"fact":"...","feeling":"...","micro_action":"..."}}

다른 텍스트 일체 금지. JSON만 출력하시오."""


@dataclass
class Sample:
    sid: str
    persona: str
    avoidance_input: str
    profile_summary: str
    expected_mode: str
    forbidden_topics: list[str] = field(default_factory=list)


SAMPLES: list[Sample] = [
    Sample(
        sid="S1",
        persona="대학원생 · 새벽 1시 · 논문 미루기",
        avoidance_input="논문 디스커션 섹션 써야 하는데 11시부터 유튜브 보고 있어. 새벽 1시야. 일어나서 시작하기 무서워.",
        profile_summary="두려움앵커=다시 거절당할까봐, 미루기유형=완벽주의 회피, 회복=첫 한 문단만 쓰면 풀림",
        expected_mode="regret",
        forbidden_topics=["부모 기대"],
    ),
    Sample(
        sid="S2",
        persona="직장인 · 일요일 저녁 · 월요일 발표",
        avoidance_input="내일 발표 PPT 마무리해야 하는데 일요일 저녁부터 넷플릭스 정주행 중. 11시인데 한 장도 안 만졌어.",
        profile_summary="두려움앵커=팀 앞에서 멍청해 보일까봐, 미루기유형=평가 회피, 회복=초안만 만들면 풀림",
        expected_mode="regret",
        forbidden_topics=["연인 비교"],
    ),
    Sample(
        sid="S3",
        persona="프리랜서 · 새벽 3시 · 클라이언트 메일",
        avoidance_input="클라이언트가 어제 보낸 수정 요청 메일 답장 못하고 있어. 새벽 3시, 그냥 핸드폰만 만지작거리고 있어.",
        profile_summary="두려움앵커=내 작업이 부족하다고 들킬까봐, 미루기유형=갈등 회피, 회복=30초 인사 한 줄만 보내도 풀림",
        expected_mode="regret",
        forbidden_topics=[],
    ),
    Sample(
        sid="S4",
        persona="학생 · 시험 전날 · 정서적 허기",
        avoidance_input="시험인데 공부가 안 돼. 아무것도 안 하고 침대에 누워서 인스타만 계속 새로고침해. 머리가 텅 빈 느낌.",
        profile_summary="두려움앵커=어차피 점수 잘 안 나올 것, 미루기유형=무기력형(정서적 허기), 회복=책 한 페이지만 펴면 OK",
        expected_mode="recovery",
        forbidden_topics=["학벌"],
    ),
    Sample(
        sid="S5",
        persona="30대 · 운동 미루기 · 일상 반복 회피",
        avoidance_input="6개월째 운동하겠다고 말만 해. 오늘도 퇴근하고 소파에 앉자마자 못 일어나겠어. 매번 이래.",
        profile_summary="두려움앵커=또 작심삼일 될까봐, 미루기유형=자기효능감 저하, 회복=운동복으로 갈아입기만 하면 80%는 함",
        expected_mode="regret",
        forbidden_topics=["외모", "체중"],
    ),
]


@dataclass
class GenerationResult:
    model: str
    sample_id: str
    raw_response: str
    latency_s: float
    error: str | None = None


def call_ollama(model: str, system_prompt: str, user_prompt: str, timeout: int = 240) -> GenerationResult:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"num_predict": 600, "temperature": 0.7, "top_p": 0.9},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL, data=data, headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        latency = time.time() - t0
        content = body.get("message", {}).get("content", "")
        return GenerationResult(model=model, sample_id="", raw_response=content, latency_s=latency)
    except Exception as exc:
        return GenerationResult(model=model, sample_id="", raw_response="", latency_s=time.time() - t0, error=str(exc))


def build_user_prompt(sample: Sample) -> str:
    return (
        f"회피 상황: {sample.avoidance_input}\n"
        f"UserProfile: {sample.profile_summary}\n"
        f"모드: {sample.expected_mode}\n"
        f"사용자 금지 주제: {', '.join(sample.forbidden_topics) if sample.forbidden_topics else '없음'}\n\n"
        "위 정보로 시나리오 카드를 JSON 한 줄로 출력하시오. /no_think"
    )


def strip_think_blocks(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def extract_json(text: str) -> dict | None:
    cleaned = strip_think_blocks(text)
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


@dataclass
class Metrics:
    json_valid: bool
    has_three_sentences: bool
    second_person_hits: list[str]
    forbidden_hits: list[str]
    total_chars: int
    in_length_range: bool
    has_micro_action: bool
    card_type: str | None


def assess(parsed: dict | None) -> Metrics:
    if not parsed:
        return Metrics(False, False, [], [], 0, False, False, None)
    sentences = parsed.get("sentences", {}) if isinstance(parsed, dict) else {}
    fact = (sentences.get("fact") or "").strip()
    feeling = (sentences.get("feeling") or "").strip()
    action = (sentences.get("micro_action") or "").strip()
    body = " ".join([fact, feeling, action])
    second_hits = [p.strip() for p in SECOND_PERSON_PATTERNS if p in body]
    forbidden_hits = [w for w in FORBIDDEN_WORDS if w in body]
    total = sum(len(s) for s in (fact, feeling, action))
    return Metrics(
        json_valid=True,
        has_three_sentences=bool(fact and feeling and action),
        second_person_hits=second_hits,
        forbidden_hits=forbidden_hits,
        total_chars=total,
        in_length_range=80 <= total <= 150,
        has_micro_action=bool(action),
        card_type=parsed.get("card_type"),
    )


def render_md(rows: list[dict]) -> str:
    lines = [
        "# G002 PoC Results v1 — 시나리오 카드 정량 평가",
        "",
        "**Date**: 2026-05-26",
        "**Pipeline**: `scripts/g002_pipeline.py`",
        f"**Models**: {len(MODELS)} ({', '.join(MODELS)})",
        f"**Samples**: {len(SAMPLES)} (대학원생·직장인·프리랜서·학생·30대 운동)",
        f"**Total scenarios**: {len(rows)}",
        "",
        "## 자동 메트릭 요약 (모델별)",
        "",
        "| 모델 | JSON valid | 3문장 완비 | 1인칭 위반 (낮을수록 좋음) | 금지어 위반 (낮을수록 좋음) | 80-150자 준수 | 평균 latency(s) |",
        "|---|---|---|---|---|---|---|",
    ]
    by_model: dict[str, list[dict]] = {}
    for row in rows:
        by_model.setdefault(row["model"], []).append(row)
    for model, model_rows in by_model.items():
        n = len(model_rows)
        json_ok = sum(1 for r in model_rows if r["metrics"].json_valid)
        three_ok = sum(1 for r in model_rows if r["metrics"].has_three_sentences)
        sp_total = sum(len(r["metrics"].second_person_hits) for r in model_rows)
        fb_total = sum(len(r["metrics"].forbidden_hits) for r in model_rows)
        len_ok = sum(1 for r in model_rows if r["metrics"].in_length_range)
        avg_lat = sum(r["latency"] for r in model_rows) / n if n else 0.0
        lines.append(
            f"| `{model}` | {json_ok}/{n} | {three_ok}/{n} | {sp_total} | {fb_total} | {len_ok}/{n} | {avg_lat:.2f} |"
        )
    lines.extend(["", "## 카드별 상세", ""])
    for row in rows:
        m = row["metrics"]
        lines.append(f"### `{row['model']}` × {row['sample_id']} — {row['persona']}")
        lines.append("")
        lines.append(f"- **입력**: {row['avoidance_input']}")
        lines.append(f"- **latency**: {row['latency']:.2f}s | **chars**: {m.total_chars} | **card_type**: {m.card_type}")
        lines.append(
            f"- **메트릭**: JSON {'✅' if m.json_valid else '❌'} | 3문장 {'✅' if m.has_three_sentences else '❌'} | "
            f"1인칭위반 {len(m.second_person_hits)}건 {m.second_person_hits} | "
            f"금지어 {len(m.forbidden_hits)}건 {m.forbidden_hits} | "
            f"길이 {'✅' if m.in_length_range else '❌'}"
        )
        if row["parsed"]:
            sents = row["parsed"].get("sentences", {})
            lines.append("")
            lines.append("```")
            lines.append(f"fact         : {sents.get('fact','')}")
            lines.append(f"feeling      : {sents.get('feeling','')}")
            lines.append(f"micro_action : {sents.get('micro_action','')}")
            lines.append("```")
        else:
            lines.append("")
            lines.append(f"raw (truncated 400): `{row['raw'][:400]}`")
        if row.get("error"):
            lines.append(f"- **error**: `{row['error']}`")
        lines.append("")
    return "\n".join(lines)


def main(output_path: Path) -> int:
    rows: list[dict] = []
    total = len(MODELS) * len(SAMPLES)
    done = 0
    for model in MODELS:
        for sample in SAMPLES:
            done += 1
            print(f"[{done}/{total}] {model} x {sample.sid}", flush=True)
            user_prompt = build_user_prompt(sample)
            result = call_ollama(model, SYSTEM_PROMPT, user_prompt)
            parsed = extract_json(result.raw_response) if result.raw_response else None
            metrics = assess(parsed)
            rows.append({
                "model": model,
                "sample_id": sample.sid,
                "persona": sample.persona,
                "avoidance_input": sample.avoidance_input,
                "raw": result.raw_response,
                "parsed": parsed,
                "metrics": metrics,
                "latency": result.latency_s,
                "error": result.error,
            })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_md(rows), encoding="utf-8")
    print(f"\nSaved: {output_path}")
    return 0


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT_ROOT / ".omc" / "ultragoal" / "g002_results_v1.md"
    raise SystemExit(main(out))
