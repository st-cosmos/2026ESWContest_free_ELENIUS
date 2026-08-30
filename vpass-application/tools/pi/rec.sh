#!/bin/bash
# 라즈베리파이 화면 녹화 (Wayland/labwc → wf-recorder)
#
#   ~/rec.sh start [이름]   # 녹화 시작 → ~/Videos/<이름 또는 vpass>-YYYYmmdd-HHMMSS.mp4
#   ~/rec.sh stop           # 녹화 종료 (파일 마무리)
#   ~/rec.sh                # 토글 (녹화 중이면 stop, 아니면 start)
#   ~/rec.sh status
#
# Pi 4 하드웨어 H.264 인코더(h264_v4l2m2m)는 1080p 까지만 받아서 1920×1200 화면을
# 1728×1080(16:10 유지)으로 줄여 30fps 로 녹화한다. 소프트웨어 x264 는 이 해상도에서
# 3~4fps 밖에 안 나오므로 쓰지 않는다. 설치: sudo apt install wf-recorder
set -u
export WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-wayland-0}
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}

OUT_DIR=~/Videos
PID_FILE=/tmp/rec.pid
SCALE=${REC_SCALE:-1728:1080}
FPS=${REC_FPS:-30}
BITRATE=${REC_BITRATE:-6M}

running() { [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; }

start() {
  if running; then echo "이미 녹화 중 (pid $(cat "$PID_FILE"))"; return 1; fi
  command -v wf-recorder >/dev/null || { echo "wf-recorder 가 없습니다: sudo apt install wf-recorder"; return 1; }
  mkdir -p "$OUT_DIR"
  local name=${1:-vpass}
  local file="$OUT_DIR/$name-$(date +%Y%m%d-%H%M%S).mp4"
  nohup wf-recorder -y -c h264_v4l2m2m -x yuv420p -r "$FPS" -F "scale=$SCALE" -p "b=$BITRATE" \
    -f "$file" > /tmp/rec.log 2>&1 &
  echo $! > "$PID_FILE"
  sleep 1
  if running; then echo "녹화 시작: $file"; else echo "녹화 시작 실패:"; tail -5 /tmp/rec.log; return 1; fi
}

stop() {
  if ! running; then echo "녹화 중이 아님"; rm -f "$PID_FILE"; return 1; fi
  local pid; pid=$(cat "$PID_FILE")
  kill -INT "$pid"                       # SIGINT 로 끝내야 mp4 가 정상 마무리된다
  for _ in $(seq 1 50); do kill -0 "$pid" 2>/dev/null || break; sleep 0.2; done
  rm -f "$PID_FILE"
  local file; file=$(ls -t "$OUT_DIR"/*.mp4 2>/dev/null | head -1)
  echo "녹화 종료: $file ($(du -h "$file" 2>/dev/null | cut -f1))"
}

case "${1:-toggle}" in
  start)  start "${2:-}" ;;
  stop)   stop ;;
  status) if running; then echo "녹화 중 (pid $(cat "$PID_FILE"))"; else echo "녹화 중 아님"; fi ;;
  toggle) if running; then stop; else start; fi ;;
  *) echo "사용법: $0 [start [이름]|stop|status]"; exit 2 ;;
esac
