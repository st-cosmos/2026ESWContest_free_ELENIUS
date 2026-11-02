#!/bin/bash
# V-PASS 서버 종료 (uv 부모 + python 자식)
# 키오스크 chromium 도 함께 내린다 — 살아 있으면 다음 --kiosk 실행이 기존 창에
# 탭만 열어 자동재생 플래그가 적용되지 않는다. ([c] 는 pkill 자신을 제외하는 꼼수)
pkill -f '[c]hromium.*--kiosk' 2>/dev/null
pkill -f 'uv run vpass' 2>/dev/null
pkill -f '[.]venv/bin/vpass' 2>/dev/null
sleep 2
if pgrep -f '[.]venv/bin/vpass' >/dev/null; then pkill -9 -f '[.]venv/bin/vpass'; sleep 1; fi
echo "vpass stopped (remaining: $(pgrep -fc '[.]venv/bin/vpass'))"
