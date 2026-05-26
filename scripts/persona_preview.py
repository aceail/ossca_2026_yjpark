"""Persona Preview Generator — G011.

5 default 페르소나에 동일 가상 회피 입력을 주고 시나리오 카드를 생성.
G005 OnboardingFlow의 페르소나 선택 카드에 미리보기로 노출.

Usage:
    python3 scripts/persona_preview.py
Output: .omc/ultragoal/persona_previews_v1.json
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from persona import BUILTIN_PERSONAS  # noqa: E402

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "exaone3.5:7.8b"

SAMPLE_AVOIDANCE = "내일 10시 발표인데 슬라이드 0장. 새벽 1시 14분이야."
SAMPLE_TIMELINE = "현재 2026-05-27 01:14, 마감 2026-05-27 10:00 (8시간 46분 후)"
SAMPLE_PROFILE = "두려움앵커=팀 앞에서 멍청해 보일까봐, 회피유형=평가 회피"


def call_ollama(system_prompt: str, user_prompt: str, timeout: int = 60) -> tuple[str, float]:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"num_predict": 500, "temperature": 0.7, "top_p": 0.9},
    }
    req = urllib.request.Request(OLLAMA_URL, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode())
    return body.get("message", {}).get("content", ""), time.time() - t0


def extract_json(text: str) -> dict | None:
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    m = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def main() -> int:
    out_path = PROJECT_ROOT / ".omc" / "ultragoal" / "persona_previews_v1.json"
    user_prompt = (
        f"회피 상황: {SAMPLE_AVOIDANCE}\n"
        f"UserProfile: {SAMPLE_PROFILE}\n"
        f"TIMELINE: {SAMPLE_TIMELINE}\n"
        f"모드: regret\n\n"
        "JSON 한 줄로 출력. /no_think"
    )
    previews: dict[str, dict] = {}
    for spec in BUILTIN_PERSONAS:
        print(f"[{spec.name}] generating preview...", flush=True)
        raw, latency = call_ollama(spec.system_prompt, user_prompt)
        parsed = extract_json(raw) or {"card_type": "regret", "_raw": raw[:300]}
        previews[spec.name] = {
            "persona_name": spec.name,
            "perspective": spec.perspective,
            "tone_mode": spec.tone_mode,
            "avatar_icon": spec.avatar_icon,
            "avatar_color": spec.avatar_color,
            "greeting": spec.greeting,
            "preview_card": parsed,
            "latency_s": latency,
        }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "sample_avoidance": SAMPLE_AVOIDANCE,
        "sample_timeline": SAMPLE_TIMELINE,
        "model": MODEL,
        "previews": previews,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
