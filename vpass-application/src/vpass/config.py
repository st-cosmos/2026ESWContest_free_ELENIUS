"""경로/플랫폼/동작 파라미터 설정.

윈도우(개발)와 라즈베리파이(운영) 양쪽에서 동작해야 하므로
환경 의존적인 값은 전부 여기서 결정한다.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

# ── 경로 ────────────────────────────────────────────────────────────────
# src/vpass/config.py → vpass-application/
APP_DIR = Path(__file__).resolve().parents[2]

DATA_DIR = Path(os.environ.get("VPASS_DATA_DIR", APP_DIR / "data"))
FACES_DIR = DATA_DIR / "faces"
UI_DIST_DIR = APP_DIR / "ui" / "dist"

USERS_FILE = DATA_DIR / "users.json"
BOARDING_LOGS_FILE = DATA_DIR / "boarding_logs.json"
VOYAGES_FILE = DATA_DIR / "voyages.json"
VESSEL_FILE = DATA_DIR / "vessel.json"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FACES_DIR.mkdir(parents=True, exist_ok=True)


# ── 플랫폼 감지 ──────────────────────────────────────────────────────────
def is_raspberry_pi() -> bool:
    if platform.system() != "Linux":
        return False
    model_path = Path("/proc/device-tree/model")
    try:
        return "raspberry pi" in model_path.read_text(errors="ignore").lower()
    except OSError:
        return platform.machine() in ("armv7l", "aarch64")


IS_RASPBERRY_PI = is_raspberry_pi()

# ── 카메라 ──────────────────────────────────────────────────────────────
CAMERA_INDEX = int(os.environ.get("VPASS_CAMERA_INDEX", "0"))

# ── 얼굴 인식 ────────────────────────────────────────────────────────────
FACE_SIZE = (200, 200)
MATCH_THRESHOLD = 52.0          # LBPH confidence (작을수록 유사)
REBOARD_MESSAGE_COOLDOWN = 6.0  # 같은 사람 중복 안내 최소 간격(초)

# ── 구명조끼 디바이스 / 익수 감지 ────────────────────────────────────────
PING_INTERVAL = 3.0        # 펌웨어 ping 주기(초)
FALL_PING_TIMEOUT = 5.0    # 낙상 후 이 시간 안에 ping 없으면 익수로 판단
SIGNAL_LOSS_TIMEOUT = 10.0 # 착용 중 신호 두절 시 익수로 판단(3회 연속 유실)

# ── 킬 스위치(GPIO) ──────────────────────────────────────────────────────
KILLSWITCH_GPIO_PIN = int(os.environ.get("VPASS_KILLSWITCH_PIN", "17"))

# ── 출항/입항 자동 감지 ──────────────────────────────────────────────────
DEPART_SPEED_KN = 3.0       # 이 속도 이상이면 출항으로 판단
DEPART_HOLD_SEC = 5.0       # 출항 판정 유지 시간
ARRIVE_SPEED_KN = 0.5       # 이 속도 미만이면 입항 후보
ARRIVE_HOLD_SEC = 15.0      # 입항 판정 유지 시간
MIN_VOYAGE_SEC = 60.0       # 출항 직후 오판 방지 최소 운항 시간
TRACK_INTERVAL_SEC = 60.0   # 운항 좌표 기록 간격(1분)
