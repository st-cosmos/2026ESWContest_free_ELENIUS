#!/bin/bash
# V-PASS 서버 시작 (라즈베리파이) — USB 블루투스 동글 사용, 로그 /tmp/vpass.log
# 파이 홈에 복사해 두고 `~/vpass-start.sh` 로 실행한다.
# 인자는 vpass 에 그대로 전달된다:
#   ~/vpass-start.sh --reset-all   # 선원·얼굴·어선 정보까지 전부 지우고 최초 구동
#   ~/vpass-start.sh --reset       # 운항·승선 기록만 초기화
cd ~/workspace/smart-vpass-system/vpass-application || exit 1
"$(dirname "$0")/vpass-stop.sh" >/dev/null
export PYTHONUNBUFFERED=1                 # nohup 리다이렉트 시 로그 버퍼링 방지
export VPASS_BLE_ADAPTER=usb              # hciN 번호는 부팅마다 바뀔 수 있어 버스 종류로 지정
export VPASS_KILLSWITCH_BLE=1
export VPASS_KILLSWITCH_BLE_ADAPTER=usb
export VPASS_KILLSWITCH_BLE_ADDRESS=${VPASS_KILLSWITCH_BLE_ADDRESS:-D4:05:92:E7:B3:4A}
export DISPLAY=:0

# ── bluetoothd 자동 재시작 보강 ───────────────────────────────────────────
# 파이 OS 기본 설정은 bluetoothd 가 10초 안에 5번 죽으면 재시작을 포기한다. 그러면
# 다음 D-Bus 요청이 깨울 때까지(실측 ~25초) 블루투스가 꺼져 조끼 신호 두절 경고가
# 오경보로 울린다 (2026-11-05 — BlueZ 5.82 제조사 데이터 패턴 버그, jacketble.py 참고).
# 어떤 이유로 죽든 1초 뒤 횟수 제한 없이 다시 띄우도록 systemd drop-in 을 깔아 둔다.
# 최초 1회만 sudo 비밀번호를 묻고, 이후에는 내용이 같으면 건너뛴다.
BT_GUARD=/etc/systemd/system/bluetooth.service.d/vpass-restart.conf
BT_GUARD_CONF='# V-PASS (tools/pi/vpass-start.sh 가 설치): bluetoothd 가 죽어도 항상 1초 뒤 재시작
[Unit]
StartLimitIntervalSec=0

[Service]
Restart=always
RestartSec=1'
if [ "$(cat "$BT_GUARD" 2>/dev/null)" = "$BT_GUARD_CONF" ]; then
  echo "bluetooth: 자동 재시작 설정 확인됨"
else
  SUDO=""
  if sudo -n true 2>/dev/null; then
    SUDO="sudo -n"
  elif [ -t 0 ]; then
    echo "bluetooth: 자동 재시작 설정을 설치합니다 (최초 1회 sudo 비밀번호 필요)"
    SUDO="sudo"
  fi
  if [ -n "$SUDO" ] && $SUDO mkdir -p "${BT_GUARD%/*}" \
     && printf '%s\n' "$BT_GUARD_CONF" | $SUDO tee "$BT_GUARD" >/dev/null \
     && $SUDO systemctl daemon-reload; then
    # 이미 재시작 한도에 걸려 꺼져 있었다면 풀고 다시 띄운다 (실행 중이면 무시됨)
    $SUDO systemctl reset-failed bluetooth 2>/dev/null
    $SUDO systemctl start bluetooth 2>/dev/null
    echo "bluetooth: 자동 재시작 설정 설치됨 ($BT_GUARD)"
  else
    echo "bluetooth: [경고] 자동 재시작 설정 미설치 — 터미널에서 ~/vpass-start.sh 를 실행해 sudo 비밀번호를 한 번 입력하세요"
  fi
fi

# ── 효과음 출력 고정 ──────────────────────────────────────────────────────
# 효과음은 키오스크 chromium 이 PipeWire "기본 출력"으로 재생한다. 기본 출력이
# 모니터가 안 꽂힌 HDMI 포트나 사라진 장치로 남아 있거나 볼륨이 0 근처면 소리가
# 조용히 안 나므로(2026-11-02 증상), 시작할 때 모니터(HDMI) 출력으로 맞추고
# 볼륨을 올려 둔다. 볼륨은 VPASS_AUDIO_VOLUME(0~1, 기본 0.7)으로 조정.
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
AUDIO_VOLUME=${VPASS_AUDIO_VOLUME:-0.7}
if command -v wpctl >/dev/null 2>&1; then
  sink=$(wpctl status 2>/dev/null | sed -n '/Sinks:/,/Sources:/p' | grep -i 'HDMI'          | grep -oE '[0-9]+\.' | head -1 | tr -d .)
  if [ -n "$sink" ]; then
    wpctl set-default "$sink"
    wpctl set-volume "$sink" "$AUDIO_VOLUME"
    wpctl set-mute "$sink" 0
    echo "audio: HDMI sink $sink, volume $AUDIO_VOLUME"
  else
    wpctl set-volume @DEFAULT_AUDIO_SINK@ "$AUDIO_VOLUME" 2>/dev/null
    echo "audio: HDMI 출력 장치 없음(모니터 꺼짐/미연결?) — 기본 출력 그대로, volume $AUDIO_VOLUME"
  fi
fi

# ── 데모 관제 서버 주소 자동 탐색 ─────────────────────────────────────────
# PC IP 는 네트워크(집 공유기 / 핫스팟)마다 달라서 고정값을 쓰면 연동이 끊긴다.
#   1) VPASS_DEMO_SERVER_URL 이 지정돼 있으면 그대로 사용
#   2) 후보 목록(VPASS_DEMO_SERVER_CANDIDATES)에서 /api/state 가 응답하는 첫 주소
#   3) 같은 서브넷 전체를 8100 포트로 빠르게 스캔
#   4) 못 찾으면 연동 없이 시작 (V-PASS 본체 동작에는 영향 없음)
DEMO_PORT=${VPASS_DEMO_SERVER_PORT:-8100}
CANDIDATES=${VPASS_DEMO_SERVER_CANDIDATES:-"10.213.122.84 192.168.0.222 172.26.94.84 10.75.209.84"}

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

# --kiosk: chromium 을 자동재생 허용 플래그와 함께 띄운다. 수동으로 연 chromium 은
# 화면을 한 번 터치하기 전까지 효과음이 차단된다.
nohup ~/.local/bin/uv run vpass --kiosk "$@" > /tmp/vpass.log 2>&1 &
echo "vpass started (pid $!) - tail -f /tmp/vpass.log"
