"""G002 PoC v2 — EXAONE only, prompt v2 (팩트폭격+유쾌), samples v2 (TIMELINE).

5 시나리오 생성 + 자동 메트릭 + 위로 어휘·정체성 결함·외부 비웃음 검출.
출력: .omc/ultragoal/g002_results_v2.md
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
MODEL = "exaone3.5:7.8b"

SECOND_PERSON_PATTERNS: list[str] = ["너는 ", "너가 ", "당신은 ", "당신이 ", "당신을 ", "당신의 "]

# v1 절대 금지어 + v2 위로 어휘 + 정체성 결함 + 비교 수치심
FORBIDDEN_GROUPS: dict[str, list[str]] = {
    "한국 가스라이팅": ["의지", "노력", "한심", "정상", "게으름", "정신 차려"],
    "정체성 결함": ["도태", "조졌", "어차피", "또 이런 식", "원래 그런"],
    "비교 수치심": ["다른 사람", "다른 애들", "남들은", "남들"],
    "한국형 트리거": ["효도", "체면", "부모 실망", "병역", "취업", "학벌", "부모 기대", "외모", "체중", "연애 실패"],
    "욕설": ["씨발", "좆", "존나", "ㅄ"],
    "위로 무력화 (v2 추가)": ["괜찮아", "괜찮다", "괜찮을", "여유롭게", "천천히", "급하지 않", "지 않아도"],
    "외부 냉소": ["거봐", "또 그럴 줄"],
}

SYSTEM_PROMPT = """당신은 "내일의 너" 도구의 미래 자아 시뮬레이터입니다. 톤은 "팩트폭격 + 유쾌" — 위로하지 않고, 사실과 결과를 두드리듯 직시하되, 미래 자아 1인칭 시점의 위트 있는 자기 풍자가 들어갑니다.

# 절대 규칙

1. 1인칭 화법만 사용
   - 허용: "나는", "내가", "내일 9시의 나는"
   - 금지: "너는", "당신은"

2. 3단 구조 (한국어, 총 80-150자)
   - fact: 구체 시각·분·숫자·누적 결과로 직시. 모호한 시제·완곡 금지. 마감 정보가 있으면 분 단위까지 박는다.
     좋음: "새벽 1시 14분이다. 디스커션 0줄. 마감까지 22시간 46분 남았다. 어떡하지."
     나쁨: "내일 아침엔 아직 완성되지 않은 자료를 마주해야 할 거야."
   - feeling: 미래 자아가 마주할 구체 장면. 위로형 어휘 금지. 짧은 가상 인용도 OK.
     좋음: "내일 10시, 회의실에서 첫 슬라이드 못 띄운 채 '에... 그러니까...'를 반복하는 나."
     나쁨: "조금 초조하지만 괜찮다는 걸 알아."
   - micro_action: 단호한 명령형 종결. 가벼운 비유 OK. 제안형 금지.
     좋음: "워드를 켠다. 마침표 하나만 찍어본다."
     나쁨: "검토해보면 어떨까", "지금 한 번 시작해볼래?"

3. 유쾌함 — 1인칭 자기 풍자만 OK
   - 허용: "어떡하지", "혼자 곱씹는 중", "키보드도 외로워하겠는데"
   - 금지: 외부 비판자 시점 비웃음, 정체성 누적 ("또 이러네"), 비교 ("다른 사람들은")
   - 금지: 친근 영업 톤, 과장된 농담, 자기계발 카피체

4. 위로 차단 금지 어구 (regret 모드에서)
   - "괜찮아", "괜찮다", "괜찮을 거야", "여유롭게", "천천히", "급하지 않아"
   - "조금 ~이지만 ~", "~하지 않아도 ~"
   - "내일 아침엔" 같은 모호한 시제 (구체 시각으로)
   - "~해보자", "~하는 게 어때" (단호한 종결로)

5. 절대 금지어 (어떤 형태로도)
   - 가스라이팅: 의지, 노력, 한심, 정상, 게으름, 정신 차려
   - 정체성 결함: 도태, 조졌, 어차피, 또 이런 식, 원래 그런
   - 비교 수치심: 다른 사람, 다른 애들, 남들은
   - 한국형 트리거: 효도, 체면, 부모 실망, 병역, 취업, 학벌, 부모 기대, 외모, 체중, 연애 실패
   - 욕설: 씨발, 좆, 존나 등

6. 금지 톤
   - 도덕적 훈계, 공포 극대화 ("인생 끝"), 외부 냉소 ("거봐, 또 그럴 줄 ㅋ"), 제3자 비교

7. recovery 모드: 사용자 입력이 "정서적 허기·번아웃·신체 통증"이면 팩트폭격 X, 차분한 인정 톤으로 전환.

# 출력 (JSON 한 줄)

{"card_type":"regret","sentences":{"fact":"...","feeling":"...","micro_action":"..."}}

다른 텍스트 일체 금지. JSON만 출력하시오."""


@dataclass
class Sample:
    sid: str
    persona: str
    avoidance_input: str
    profile_summary: str
    expected_mode: str
    timeline_hint: str = ""


SAMPLES: list[Sample] = [
    Sample(
        sid="S1",
        persona="대학원생 · 새벽 1시 14분 · 논문 디스커션",
        avoidance_input="논문 디스커션 섹션 써야 하는데 11시부터 유튜브 보고 있어. 새벽 1시 14분이야. 일어나서 시작하기 무서워.",
        profile_summary="두려움앵커=거절 트라우마, 회피유형=완벽주의, 회복=첫 한 문단만 쓰면 풀림",
        expected_mode="regret",
        timeline_hint="현재 2026-05-27 01:14, 마감 2026-05-28 00:00 (22시간 46분 후)",
    ),
    Sample(
        sid="S2",
        persona="직장인 · 일요일 23:00 · 월요일 10시 발표",
        avoidance_input="내일 10시 팀 발표 PPT 마무리해야 하는데 일요일 저녁부터 넷플릭스 정주행. 23시인데 슬라이드 0장이야.",
        profile_summary="두려움앵커=팀 앞에서 멍청해 보일까봐, 회피유형=평가 회피, 회복=초안만 만들면 풀림",
        expected_mode="regret",
        timeline_hint="현재 2026-05-26 23:00, 마감 2026-05-27 10:00 (11시간 후)",
    ),
    Sample(
        sid="S3",
        persona="프리랜서 · 새벽 3시 · 클라이언트 메일",
        avoidance_input="어제 받은 클라이언트 수정 요청 메일 답장 못하고 있어. 새벽 3시, 핸드폰만 만지작거리고 있어.",
        profile_summary="두려움앵커=작업 부족 들킬까봐, 회피유형=갈등 회피, 회복=30초 인사 한 줄만 보내도 풀림",
        expected_mode="regret",
        timeline_hint="현재 2026-05-27 03:00, 클라이언트 응답 기대 시한 2026-05-27 18:00 (15시간 후)",
    ),
    Sample(
        sid="S4",
        persona="학생 · 시험 전날 22:30 · 정서적 허기",
        avoidance_input="내일 9시 시험인데 공부가 안 돼. 침대에 누워서 인스타만 새로고침해. 머리가 텅 빈 느낌.",
        profile_summary="두려움앵커=어차피 점수 안 나올 것, 회피유형=무기력형(정서적 허기), 회복=책 한 페이지만 펴면 OK",
        expected_mode="recovery",
        timeline_hint="현재 2026-05-26 22:30, 시험 2026-05-27 09:00 (10시간 30분 후) — 정서적 허기 사각, 톤 완화",
    ),
    Sample(
        sid="S5",
        persona="30대 · 퇴근 20:00 · 운동 6개월째 미루기",
        avoidance_input="6개월째 운동하겠다고 말만 해. 오늘도 퇴근하고 8시에 소파에 앉자마자 못 일어나겠어. 매번 이래.",
        profile_summary="두려움앵커=또 작심삼일 될까봐, 회피유형=자기효능감 저하, 회복=운동복 갈아입기만 하면 80%는 함",
        expected_mode="regret",
        timeline_hint="현재 2026-05-26 20:00, 자기 약속 6개월째",
    ),
]


@dataclass
class GenerationResult:
    model: str
    sample_id: str
    raw_response: str
    latency_s: float
    error: str | None = None


def call_ollama(model: str, system_prompt: str, user_prompt: str, timeout: int = 120) -> GenerationResult:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"num_predict": 500, "temperature": 0.85, "top_p": 0.9},
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
        f"TIMELINE: {sample.timeline_hint}\n"
        f"모드: {sample.expected_mode}\n\n"
        "팩트폭격+유쾌 톤으로 시나리오 카드 JSON 한 줄. /no_think"
    )


def extract_json(text: str) -> dict | None:
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def assess(parsed: dict | None) -> dict:
    if not parsed:
        return {"json_valid": False}
    sentences = parsed.get("sentences", {}) if isinstance(parsed, dict) else {}
    fact = (sentences.get("fact") or "").strip()
    feeling = (sentences.get("feeling") or "").strip()
    action = (sentences.get("micro_action") or "").strip()
    body = " ".join([fact, feeling, action])
    second_hits = [p.strip() for p in SECOND_PERSON_PATTERNS if p in body]
    forbidden_hits = {group: [w for w in words if w in body] for group, words in FORBIDDEN_GROUPS.items()}
    forbidden_hits = {g: hits for g, hits in forbidden_hits.items() if hits}
    has_time_specific = bool(re.search(r"\d+시\s*\d+분|\d+시간\s*\d+분|\d+분|\d+시", fact))
    return {
        "json_valid": True,
        "fact": fact,
        "feeling": feeling,
        "action": action,
        "three_sentences": bool(fact and feeling and action),
        "second_person_hits": second_hits,
        "forbidden_groups_hit": forbidden_hits,
        "total_chars": sum(len(s) for s in (fact, feeling, action)),
        "in_length_range": 80 <= sum(len(s) for s in (fact, feeling, action)) <= 150,
        "has_time_specific": has_time_specific,
        "card_type": parsed.get("card_type"),
    }


def main(output_path: Path) -> int:
    rows: list[dict] = []
    for i, sample in enumerate(SAMPLES, 1):
        print(f"[{i}/{len(SAMPLES)}] {MODEL} x {sample.sid}", flush=True)
        result = call_ollama(MODEL, SYSTEM_PROMPT, build_user_prompt(sample))
        parsed = extract_json(result.raw_response) if result.raw_response else None
        metrics = assess(parsed)
        rows.append({
            "sample": sample,
            "result": result,
            "parsed": parsed,
            "metrics": metrics,
        })

    lines = [
        "# G002 PoC v2 — 팩트폭격 + 유쾌 (EXAONE 3.5 7.8B)",
        "",
        "**Date**: 2026-05-26",
        "**Pipeline**: `scripts/g002_pipeline_v2.py`",
        "**Prompt**: `.omc/ultragoal/scenario_prompt_v2.md` (팩트폭격+유쾌+TIMELINE)",
        "**Samples**: `.omc/ultragoal/avoidance_samples_v2.md` (5건, 마감 정보 포함)",
        "",
        "## 요약",
        "",
        "| 샘플 | 시간 구체화 | 1인칭 위반 | 금지어 위반 | 80-150자 | latency |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        m = row["metrics"]
        if not m.get("json_valid"):
            lines.append(f"| {row['sample'].sid} | — | — | — | — | {row['result'].latency_s:.2f}s (JSON 실패) |")
            continue
        time_ok = "✅" if m["has_time_specific"] else "❌"
        sp = len(m["second_person_hits"])
        fb_total = sum(len(v) for v in m["forbidden_groups_hit"].values())
        len_ok = "✅" if m["in_length_range"] else "❌"
        lines.append(f"| {row['sample'].sid} | {time_ok} | {sp} | {fb_total} | {len_ok} {m['total_chars']}자 | {row['result'].latency_s:.2f}s |")
    lines.extend(["", "## 카드별 상세", ""])
    for row in rows:
        s = row["sample"]
        m = row["metrics"]
        lines.append(f"### {s.sid} — {s.persona}")
        lines.append("")
        lines.append(f"- **입력**: {s.avoidance_input}")
        lines.append(f"- **TIMELINE**: {s.timeline_hint}")
        lines.append(f"- **mode**: {s.expected_mode} → 출력 card_type: {m.get('card_type')}")
        if m.get("json_valid"):
            lines.append("")
            lines.append("```")
            lines.append(f"fact         : {m['fact']}")
            lines.append(f"feeling      : {m['feeling']}")
            lines.append(f"micro_action : {m['action']}")
            lines.append("```")
            lines.append("")
            lines.append(f"- 시간 구체화: {'✅' if m['has_time_specific'] else '❌'}")
            lines.append(f"- 1인칭 위반: {len(m['second_person_hits'])}건 {m['second_person_hits']}")
            if m["forbidden_groups_hit"]:
                lines.append(f"- 금지어 그룹별 위반: {m['forbidden_groups_hit']}")
            else:
                lines.append("- 금지어 위반: 0건")
            lines.append(f"- 길이: {m['total_chars']}자 ({'✅' if m['in_length_range'] else '❌ 80-150 범위 밖'})")
        else:
            lines.append("")
            lines.append(f"raw (truncated 400): `{row['result'].raw_response[:400]}`")
        if row["result"].error:
            lines.append(f"- error: `{row['result'].error}`")
        lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nSaved: {output_path}")
    return 0


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT_ROOT / ".omc" / "ultragoal" / "g002_results_v2.md"
    raise SystemExit(main(out))
