#!/bin/bash
# V-PASS 서버 종료 (uv 부모 + python 자식)
pkill -f 'uv run vpass' 2>/dev/null
pkill -f '[.]venv/bin/vpass' 2>/dev/null
sleep 2
if pgrep -f '[.]venv/bin/vpass' >/dev/null; then pkill -9 -f '[.]venv/bin/vpass'; sleep 1; fi
echo "vpass stopped (remaining: $(pgrep -fc '[.]venv/bin/vpass'))"
