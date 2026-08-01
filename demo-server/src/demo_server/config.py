"""경로/환경 설정.

V-PASS 애플리케이션과 동일한 구성 방식(윈도우 개발 / 리눅스 운영 공용).
"""

from __future__ import annotations

import os
from pathlib import Path

# src/demo_server/config.py → demo-server/
APP_DIR = Path(__file__).resolve().parents[2]

DATA_DIR = Path(os.environ.get("DEMO_DATA_DIR", APP_DIR / "data"))
UI_DIST_DIR = APP_DIR / "ui" / "dist"

VESSELS_FILE = DATA_DIR / "vessels.json"
REPORTS_FILE = DATA_DIR / "reports.json"
PORTLOG_FILE = DATA_DIR / "portlog.json"
WEATHER_FILE = DATA_DIR / "weather.json"

# 관할 해양경찰청 (5개)
REGIONS = ["동해", "서해", "남해", "중부", "제주"]

# 기상 상태 종류
CONDITIONS = ["맑음", "구름조금", "흐림", "비", "안개", "뇌우"]

# V-PASS 라이브 선박이 이 시간(초) 동안 갱신되지 않으면 오프라인으로 표시
LIVE_TIMEOUT_SEC = 15.0

# 출항 중 선박 위치 시뮬레이션 간격(초)
SIM_INTERVAL_SEC = 1.0

DEFAULT_PORT = int(os.environ.get("DEMO_PORT", "8100"))


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
