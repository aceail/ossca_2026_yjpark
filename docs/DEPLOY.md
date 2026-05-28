# 배포 가이드 (Sprint 23)

운영 환경에서 도는 "내일의 너". 3가지 시나리오:

## 1. 단일 머신 + Docker Compose (가장 추천)

전제: Linux/macOS + Docker 24+ + 16GB RAM (Ollama 모델 호스팅).

```bash
# 1. clone & cd
git clone https://github.com/aceail/ossca_2026_yjpark naeil && cd naeil

# 2. env 채우기
cp .env.example .env
cp frontend/.env.example frontend/.env.local
# (옵션) python scripts/gen_vapid.py 실행 후 3 줄 .env에 추가 + frontend/.env.local에 NEXT_PUBLIC_VAPID_PUBLIC_KEY

# 3. 컨테이너 빌드 + 기동
docker compose -f docker/local.compose.yml --env-file .env up -d --build

# 4. 모델 1회 다운로드 (컨테이너 안에서)
docker exec naeil-ollama ollama pull qwen3:8b

# 5. 접속
open http://localhost:3000
```

## 2. 베어메탈 + systemd (Docker 없이)

`naeil-backend.service`:

```ini
[Unit]
Description=Naeil backend (FastAPI)
After=network.target

[Service]
Type=simple
User=yj
WorkingDirectory=/home/yj/naeil
EnvironmentFile=/home/yj/naeil/.env
ExecStart=/usr/bin/python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8001
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

`naeil-frontend.service`:

```ini
[Unit]
Description=Naeil frontend (Next.js)
After=network.target naeil-backend.service

[Service]
Type=simple
User=yj
WorkingDirectory=/home/yj/naeil/frontend
ExecStart=/usr/bin/npm start
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

먼저 `npm run build` 1회. 그 다음 `sudo systemctl enable --now naeil-backend naeil-frontend`.

Ollama는 별도 systemd unit으로 또는 자체 daemon (`ollama serve`).

## 3. 외부 접근 (Tailscale 권장)

| 옵션 | 설정 |
|---|---|
| **Tailscale** | PC + 폰에 클라이언트 설치 → 같은 tailnet → `https://pc-name.<tailnet>.ts.net:3000` 자동 HTTPS. |
| **headscale + Tailscale** | 100% OSS 컨트롤 플레인 셀프호스트. |
| **Cloudflare Tunnel** | 도메인 + `cloudflared tunnel run --url http://localhost:3000`. CF가 HTTPS 자동. |
| **frp + nginx + Let's Encrypt** | 자기 VPS 1대 필요. 100% 자기 인프라. |

자세한 명령은 [`MOBILE_ACCESS.md`](MOBILE_ACCESS.md).

## 4. 운영 체크리스트

- [ ] **VAPID 키 발급** — `python scripts/gen_vapid.py`. backend env 3 줄 + frontend env 1 줄.
- [ ] **Fernet passphrase** — `.env`의 `TOMORROW_YOU_FERNET_PASSPHRASE` (평문 키 디스크 회피).
- [ ] **HTTPS** — PWA install·Push 알림 모두 HTTPS 필요. Tailscale·CF Tunnel·Let's Encrypt 중 하나.
- [ ] **DB 백업** — `tomorrow_you.db` (또는 `naeil_data` 볼륨) 매일 cron 백업 권장. SQLite는 `sqlite3 backup` 명령.
- [ ] **모델 사전 다운로드** — `ollama pull qwen3:8b` (function-calling). 옵션 `hermes3:8b`, `llama3.1:8b`.
- [ ] **백그라운드 loops 확인**: `docker logs naeil-backend` 또는 systemd journal에 `_folder_watch_loop`·`_followup_loop`·`_reflection_loop` 시작 로그 확인.

## 5. 로그·모니터링

- backend: stdout/stderr → docker logs 또는 journalctl
- 우리 코드는 print/logging 적게 — uvicorn access log + FastAPI HTTPException 위주
- 사용자별 활동: SQLite 직접 SELECT
  ```sql
  SELECT user_id, COUNT(*) AS msgs FROM ChatMessage
   JOIN ChatSession s ON s.id = chat_session_id
  GROUP BY user_id ORDER BY msgs DESC LIMIT 10;
  ```

## 6. 백업 복원

```bash
# 백업
sqlite3 tomorrow_you.db ".backup '/var/backups/naeil-$(date +%Y%m%d).db'"

# 복원
docker compose -f docker/local.compose.yml down
cp /var/backups/naeil-YYYYMMDD.db tomorrow_you.db
docker compose -f docker/local.compose.yml up -d
```

## 7. 보안

- LICENSE의 dual-use 제한 준수
- 외부 노출 시 device token 헤더는 capability — 누출 주의
- ICS feed URL에는 token이 query string으로 박혀 있음. 외부 공유 금지.
- VAPID private key는 backend env에만; 절대 frontend에 노출 X.
- 정기 보안 점검은 [`SECURITY.md`](../SECURITY.md) 참조.

## Tracing (Sprint 27)

The compose stack now includes a self-hosted Arize Phoenix container for
observability of the agent loop.

### Accessing the UI

After `docker compose -f docker/local.compose.yml up -d`:

- Phoenix UI: <http://localhost:6006> (bound to loopback only)
- Service identifier: `tomorrow-you-backend`

### Toggling tracing on/off

Set in `.env`:

```bash
TOMORROW_YOU_TRACING_ENABLED=true   # or false
```

Then restart backend: `docker compose -f docker/local.compose.yml up -d backend`.
Disabled mode incurs near-zero overhead (NoOpTracerProvider).

### Wiping trace history

```bash
docker compose -f docker/local.compose.yml down phoenix
docker volume rm $(docker volume ls -q | grep phoenix_data)
docker compose -f docker/local.compose.yml up -d phoenix
```

### What gets traced

Every chat round, tool dispatch, memory operation (recall/upsert/top_memories),
reflection cycle, daily briefing, and Ollama LLM call produces a span. See
`.claude/skills/tomorrow-you-tracing/SKILL.md` for the schema and conventions.

### Privacy note

Spans contain full user message text, model responses, and memory contents.
The Phoenix container holds this data on a local volume (`phoenix_data`) and
the UI is bound to `127.0.0.1` only — nothing leaves this host. If you share
this machine or deploy beyond local, add a redaction layer before relaxing
the bind.
