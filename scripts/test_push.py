#!/usr/bin/env python3
"""Wave 6 보조: 임의 사용자에게 테스트 push 알림 1건 발송.

usage:
    python scripts/test_push.py <user_id> [메시지본문]
    python scripts/test_push.py <user_id> "발표자료 D-1. 폴더 그대로야."

전제:
    1. pywebpush 설치 (pip install --user pywebpush)
    2. NAEIL_VAPID_PUBLIC_KEY / NAEIL_VAPID_PRIVATE_KEY / NAEIL_VAPID_SUBJECT
       환경변수 설정 (scripts/gen_vapid.py 출력 따라)
    3. 사용자가 settings에서 "마감 알림 켜기" 토글 → PushSubscription 1건 이상
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.push import push_enabled, send_push_to_user


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: python scripts/test_push.py <user_id> [body]", file=sys.stderr)
        return 2

    user_id = argv[1]
    body = argv[2] if len(argv) >= 3 else "발표자료 D-1. 폴더 그대로야."

    if not push_enabled():
        print(
            "push disabled — pywebpush 미설치 또는 NAEIL_VAPID_* 환경변수 미설정.\n"
            "  pip install --user pywebpush\n"
            "  python scripts/gen_vapid.py  # 출력된 3 줄을 export",
            file=sys.stderr,
        )
        return 1

    db_path = os.environ.get("TOMORROW_YOU_DB", str(PROJECT_ROOT / "tomorrow_you.db"))
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        sent = send_push_to_user(
            conn,
            user_id=user_id,
            title="내일의 너",
            body=body,
            url="/chat",
        )
    finally:
        conn.close()

    if sent == 0:
        print(
            f"사용자 {user_id}의 활성 PushSubscription을 못 찾았어요. "
            "settings에서 '마감 알림 켜기'를 먼저 토글하세요.",
            file=sys.stderr,
        )
        return 1

    print(f"✓ {sent}개 디바이스로 발송: {body!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
