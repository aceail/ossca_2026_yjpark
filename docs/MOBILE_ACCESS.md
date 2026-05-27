# 모바일에서 접근하기

내 PC가 backend·DB 호스트, 폰은 client. 같은 폰·집 와이파이면 LAN으로 즉시. 외부망에서 닿으려면 reverse tunnel 또는 mesh VPN 중 하나.

각 옵션의 보안·OSS·난이도 트레이드오프.

## 옵션 1 — LAN (집 와이파이 안)

**가장 빠름. 외부 의존성 0.** 집 안에서만 동작.

### Backend bind

```bash
# 기본은 127.0.0.1 → 외부 인터페이스에서 안 보임.
# 모바일에서 접근하려면 0.0.0.0 으로 listen.
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8001
```

### Frontend bind

Next.js dev는 기본 0.0.0.0:3000. PC의 IPv4 확인:

```bash
# macOS / Linux
ip -4 addr show | grep inet
# 또는
hostname -I
```

폰 브라우저: `http://192.168.x.y:3000`.

### CORS 보강

`backend/main.py`의 `allow_origins`에 `http://192.168.*.*:3000` 패턴 또는 명시 IP 추가.

### PWA install

폰 Chrome/Safari로 접속 → 메뉴 → "홈 화면에 추가". 단, **PWA는 HTTPS 필수**. LAN HTTP에서는 Service Worker 등록이 거부될 수 있다. 두 가지 우회:

- `localhost`는 예외 — 폰 자체에 backend를 띄우면 OK (Termux 등).
- `mkcert`로 자체 인증서 생성 (아래 보안 섹션).

## 옵션 2 — Tailscale (mesh VPN, 가장 균형)

**OSS 정도:** 클라이언트 OSS · 컨트롤 SaaS (개인 100명 무료) · 또는 **headscale** 셀프호스트로 100% OSS.

설치:

```bash
# macOS
brew install tailscale

# Linux
curl -fsSL https://tailscale.com/install.sh | sh

# Windows / iOS / Android — 공식 앱
```

`tailscale up` → 같은 계정으로 PC + 폰 로그인. 그러면 PC가 `pc-name.<tailnet>.ts.net` 같은 도메인으로 폰에서 접근 가능 (HTTPS 자동).

### 100% OSS — headscale 컨트롤 플레인

```bash
# headscale 서버 (VPS 1대 또는 자기 NAS)
docker run -d --name headscale -p 8080:8080 \
  -v /etc/headscale:/etc/headscale \
  headscale/headscale:latest

# 클라이언트는 표준 Tailscale 앱 그대로
tailscale up --login-server=https://your-headscale.example.com
```

## 옵션 3 — Cloudflare Tunnel

**OSS 정도:** 클라이언트(`cloudflared`) OSS · CF 의존.

도메인 필요 (CF에 등록 무료). 트래픽이 CF를 통과.

```bash
# cloudflared 설치 후
cloudflared tunnel login
cloudflared tunnel create naeil
cloudflared tunnel route dns naeil naeil.example.com
cloudflared tunnel run --url http://localhost:3000 naeil
```

폰에서 `https://naeil.example.com` 접속 — CF가 HTTPS 인증서 자동 발급.

## 옵션 4 — frp (Fast Reverse Proxy)

**OSS 정도:** 100% OSS. VPS 1대 필요.

설계: VPS에 `frps` 서버 + PC에 `frpc` 클라이언트.

```ini
# frps.ini (VPS)
[common]
bind_port = 7000
vhost_https_port = 443

# frpc.ini (PC)
[common]
server_addr = vps.example.com
server_port = 7000

[naeil-frontend]
type = https
local_ip = 127.0.0.1
local_port = 3000
custom_domains = naeil.example.com
```

VPS 도메인의 DNS A 레코드를 VPS IP로. 인증서는 nginx로 frps 앞단에 또는 CF 프록시.

## 옵션 5 — ngrok (데모 전용)

**OSS 정도:** SaaS. 무료 tier URL 매번 바뀜.

```bash
ngrok http 3000
```

운영엔 X. 시연·합의용으로만 추천.

## 보안 체크리스트

- **device token (P0-8)** — 모든 사용자별 API에 Bearer 헤더 필수. 외부 접근 시 동일 게이트.
- **HTTPS** — Tailscale·CF Tunnel·frp+nginx 모두 자동 또는 쉬움. LAN HTTP는 PWA 등록 불가.
- **token 누출** — ICS subscribe URL에는 device token이 query param으로 들어감. 외부 공개 금지.
- **VAPID push** — VAPID private key는 backend env에만. frontend는 public key만 받음.
- **방화벽** — backend port를 LAN/외부에 열 때 OS 방화벽 확인. iptables/ufw로 LAN 대역만 허용 권장.

## 자체 인증서 (mkcert로 LAN HTTPS)

```bash
# 1회 설치
brew install mkcert       # macOS
# Linux: 패키지 또는 https://github.com/FiloSottile/mkcert

mkcert -install
mkcert 192.168.0.10 localhost

# 결과: 192.168.0.10+1.pem + 192.168.0.10+1-key.pem
# backend는 uvicorn --ssl-keyfile / --ssl-certfile, frontend는 next.config 옵션 또는 reverse proxy로.
```

## 권장

- **데모·합의:** ngrok (5분 안)
- **본인 매일 사용 (집 + 카페):** Tailscale 클라이언트만
- **본인 매일 사용 (100% OSS 고집):** headscale + Tailscale 클라이언트
- **여러 사람 공유 (시연):** Cloudflare Tunnel + 도메인
- **자기 VPS 활용:** frp + nginx + Let's Encrypt
