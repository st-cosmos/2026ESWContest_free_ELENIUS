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
export VPASS_DEMO_SERVER_URL=${VPASS_DEMO_SERVER_URL:-http://192.168.0.222:8100}
export DISPLAY=:0
nohup ~/.local/bin/uv run vpass > /tmp/vpass.log 2>&1 &
echo "vpass started (pid $!) — tail -f /tmp/vpass.log"
