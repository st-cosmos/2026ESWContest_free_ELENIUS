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
SIMULATOR_FILE = DATA_DIR / "simulator.json"

# 관할 해양경찰청 (5개)
REGIONS = ["동해", "서해", "남해", "중부", "제주"]

# 기상 상태 종류
CONDITIONS = ["맑음", "구름조금", "흐림", "비", "안개", "뇌우"]

# V-PASS 라이브 선박이 이 시간(초) 동안 갱신되지 않으면 오프라인으로 표시
LIVE_TIMEOUT_SEC = 15.0

# 출항 중 선박 위치 시뮬레이션 간격(초)
SIM_INTERVAL_SEC = 1.0

# 운항 시뮬레이터 이동 간격(초) — 지도 위 움직임이 부드럽게 보이도록 더 촘촘히 돈다
SIM_TICK_SEC = 0.2

DEFAULT_PORT = int(os.environ.get("DEMO_PORT", "8100"))

# ── V-PASS 단말 LoRa 수신 (선택) ────────────────────────────────────────
# E220-900T22D 같은 투명 UART LoRa 모듈을 관제 서버에 연결한 경우 켠다.
LORA_ENABLED = (
    os.environ.get("DEMO_LORA", "0").strip().lower()
    not in ("0", "false", "off", "")
)
LORA_PORT = os.environ.get("DEMO_LORA_PORT", "/dev/ttyUSB0").strip()
LORA_BAUDRATE = int(os.environ.get("DEMO_LORA_BAUDRATE", "9600"))
LORA_TIMEOUT_SEC = float(os.environ.get("DEMO_LORA_TIMEOUT", "2.5"))

# ── 국립해양조사원(KHOA) 공공데이터 연동 (선택) ──────────────────────────
# data.go.kr 에서 활용 신청 후 발급받은 인증키를 넣으면 실측/예측 해류·바람을
# 가져와 벡터 필드와 표류 예측에 사용한다. 미설정 시 관제사가 설정한 값으로
# 계산하므로 시연은 그대로 동작한다. (docs/api-list.md 참고)
KHOA_API_KEY = os.environ.get("DEMO_KHOA_API_KEY", "").strip()

# 오퍼레이션 경로는 활용 승인 후 확정되므로 환경변수로 덮어쓸 수 있게 둔다.
_KHOA_BASE = os.environ.get("DEMO_KHOA_BASE", "http://www.khoa.go.kr/api/oceangrid")
KHOA_ROMS_URL = os.environ.get("DEMO_KHOA_ROMS_URL", f"{_KHOA_BASE}/romsCurrent/search.do")
KHOA_CURRENT_URL = os.environ.get("DEMO_KHOA_CURRENT_URL", f"{_KHOA_BASE}/tidalCurrent/search.do")
KHOA_WIND_URL = os.environ.get("DEMO_KHOA_WIND_URL", f"{_KHOA_BASE}/tideObsWind/search.do")
KHOA_BUOY_URL = os.environ.get("DEMO_KHOA_BUOY_URL", f"{_KHOA_BASE}/buoyObs/search.do")

# 관할 기상에 실측값을 반영하는 주기(초)
KHOA_SYNC_INTERVAL_SEC = float(os.environ.get("DEMO_KHOA_SYNC_SEC", "600"))

# ── 요구조자 표류 예측 (Leeway) ─────────────────────────────────────────
# 표류 = 해류 100% + 풍속의 LEEWAY_RATIO (SAR 경험식 근사, 시연용)
LEEWAY_RATIO = float(os.environ.get("DEMO_LEEWAY_RATIO", "0.03"))
# 경과 1시간당 누적되는 위치 오차 반경(해리) — 확률 구간 확산 계수.
# 0.28 이면 60분 95% 반경이 약 1.27 km 로, 해경 초기 탐색 구역 규모와 비슷하다.
DRIFT_SPREAD_NM_PER_HOUR = float(os.environ.get("DEMO_DRIFT_SPREAD_NM", "0.28"))
# 탐색 우선 구역(부채꼴) 반각(°)
DRIFT_SECTOR_HALF_ANGLE = float(os.environ.get("DEMO_DRIFT_SECTOR_DEG", "28"))


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
