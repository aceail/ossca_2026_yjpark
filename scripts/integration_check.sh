#!/usr/bin/env bash
# Tomorrow's You — Integration smoke check
# 백엔드 띄우고 핵심 endpoint 5종을 curl로 두드림.
# Usage: bash scripts/integration_check.sh

set -euo pipefail
cd "$(dirname "$0")/.."

API="${API:-http://127.0.0.1:8001}"
PID=""

cleanup() { [ -n "$PID" ] && kill "$PID" 2>/dev/null || true; }
trap cleanup EXIT

if ! curl -s --max-time 1 "$API/api/personas" >/dev/null 2>&1; then
  echo "[backend] starting uvicorn..."
  uvicorn backend.main:app --host 127.0.0.1 --port 8001 >/tmp/tomorrow_you_backend.log 2>&1 &
  PID=$!
  for i in 1 2 3 4 5 6 7 8 9 10; do
    sleep 1
    if curl -s --max-time 1 "$API/api/personas" >/dev/null 2>&1; then
      echo "[backend] ready (try $i)"
      break
    fi
  done
fi

echo
echo "=== GET /api/personas ==="
curl -s "$API/api/personas" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'  personas: {len(d) if isinstance(d, list) else len(d.get(\"personas\", []))} found')" 2>&1 | head -3

echo
echo "=== POST /api/users ==="
UID=$(curl -s -X POST "$API/api/users" -H 'Content-Type: application/json' -d '{}' | python3 -c "import json,sys; print(json.load(sys.stdin).get('user_id',''))")
echo "  user_id: $UID"
[ -z "$UID" ] && { echo "FAIL: no user_id"; exit 1; }

echo
echo "=== POST /api/sessions ==="
SID=$(curl -s -X POST "$API/api/sessions" -H 'Content-Type: application/json' \
  -d "{\"user_id\":\"$UID\",\"avoidance_input\":\"내일 발표 PPT 0장. 새벽 1시.\",\"timeline_hint\":\"현재 01:14, 마감 10:00 (8h 46m)\"}" \
  | python3 -c "import json,sys; print(json.load(sys.stdin).get('session_id',''))")
echo "  session_id: $SID"

echo
echo "=== GET /api/sessions/$SID/probe ==="
curl -s "$API/api/sessions/$SID/probe" | head -c 200
echo

echo
echo "=== POST /api/sessions/$SID/scenario (EXAONE 호출, ~5s) ==="
curl -s --max-time 90 -X POST "$API/api/sessions/$SID/scenario" -H 'Content-Type: application/json' -d '{}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); s=d.get('sentences', {}); print(f'  card_type: {d.get(\"card_type\")}'); [print(f'  {k}: {v}') for k,v in s.items() if v]"

echo
echo "=== Integration smoke OK ==="
