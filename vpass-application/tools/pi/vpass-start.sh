#!/bin/bash
# V-PASS 서버 시작 (라즈베리파이) — USB 블루투스 동글 사용, 로그 /tmp/vpass.log
# 파이 홈에 복사해 두고 `~/vpass-start.sh` 로 실행한다.
cd ~/workspace/smart-vpass-system/vpass-application || exit 1
"$(dirname "$0")/vpass-stop.sh" >/dev/null
export PYTHONUNBUFFERED=1                 # nohup 리다이렉트 시 로그 버퍼링 방지
export VPASS_BLE_ADAPTER=usb              # hciN 번호는 부팅마다 바뀔 수 있어 버스 종류로 지정
export VPASS_KILLSWITCH_BLE=1
export VPASS_KILLSWITCH_BLE_ADAPTER=usb
export VPASS_KILLSWITCH_BLE_ADDRESS=${VPASS_KILLSWITCH_BLE_ADDRESS:-D4:05:92:E7:B3:4A}
export DISPLAY=:0

# ── 데모 관제 서버 주소 자동 탐색 ─────────────────────────────────────────
# PC IP 는 네트워크(집 공유기 / 핫스팟)마다 달라서 고정값을 쓰면 연동이 끊긴다.
#   1) VPASS_DEMO_SERVER_URL 이 지정돼 있으면 그대로 사용
#   2) 후보 목록(VPASS_DEMO_SERVER_CANDIDATES)에서 /api/state 가 응답하는 첫 주소
#   3) 같은 서브넷 전체를 8100 포트로 빠르게 스캔
#   4) 못 찾으면 연동 없이 시작 (V-PASS 본체 동작에는 영향 없음)
DEMO_PORT=${VPASS_DEMO_SERVER_PORT:-8100}
CANDIDATES=${VPASS_DEMO_SERVER_CANDIDATES:-"10.213.122.84 192.168.0.222"}

probe() { curl -s -m 1 -o /dev/null -w '%{http_code}' "http://$1:$DEMO_PORT/api/state" 2>/dev/null | grep -q '^200$'; }

find_demo_server() {
  local host
  for host in $CANDIDATES; do
    probe "$host" && { echo "$host"; return; }
  done
  # 서브넷 스캔: 기본 라우트의 /24 를 병렬로 찔러 본다 (약 2~3초)
  local subnet
  subnet=$(ip -4 route show default 2>/dev/null | awk '{print $3}' | head -1 | cut -d. -f1-3)
  [ -n "$subnet" ] || return
  seq 1 254 | sed "s/^/$subnet./" | xargs -P 64 -I{} sh -c \
    "curl -s -m 1 -o /dev/null -w '%{http_code} {}\n' http://{}:$DEMO_PORT/api/state 2>/dev/null" \
    | awk '$1==200 {print $2; exit}'
}

if [ -z "$VPASS_DEMO_SERVER_URL" ]; then
  host=$(find_demo_server)
  if [ -n "$host" ]; then
    export VPASS_DEMO_SERVER_URL="http://$host:$DEMO_PORT"
    echo "demo server: $VPASS_DEMO_SERVER_URL"
  else
    unset VPASS_DEMO_SERVER_URL
    echo "demo server: not found (8100 응답 없음) — 관제 연동 없이 시작"
  fi
else
  echo "demo server: $VPASS_DEMO_SERVER_URL (env)"
fi

nohup ~/.local/bin/uv run vpass > /tmp/vpass.log 2>&1 &
echo "vpass started (pid $!) - tail -f /tmp/vpass.log"
