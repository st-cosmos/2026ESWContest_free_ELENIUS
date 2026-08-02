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

# ── 데모 관제 서버 연동 (선택) ──────────────────────────────────────────
# 설정 시 텔레메트리/신고/출입항을 데모 관제 서버로 전송하고 관할 기상을 받아온다.
# 미설정 시 V-PASS 는 기존과 동일하게 독립 동작한다.
DEMO_SERVER_URL = os.environ.get("VPASS_DEMO_SERVER_URL", "").strip() or None

# ── 카메라 ──────────────────────────────────────────────────────────────
CAMERA_INDEX = int(os.environ.get("VPASS_CAMERA_INDEX", "0"))
# 발열 저감: N 프레임마다 1회만 얼굴 검출 (1 = 매 프레임)
DETECT_EVERY_N_FRAMES = max(1, int(os.environ.get("VPASS_DETECT_EVERY_N_FRAMES", "3")))

# ── GPS / 지자계 ────────────────────────────────────────────────────────
# auto: 라즈베리파이에서는 실제 하드웨어, 그 외 개발 환경에서는 시뮬레이터
# hardware: NMEA GPS + QMC5883L 강제 사용
# sim: 개발/시연용 시뮬레이터 강제 사용
TELEMETRY_PROVIDER = os.environ.get("VPASS_TELEMETRY_PROVIDER", "auto").lower()
GPS_PORT = os.environ.get("VPASS_GPS_PORT", "/dev/serial0")
GPS_BAUDRATE = int(os.environ.get("VPASS_GPS_BAUDRATE", "9600"))
GPS_STALE_AFTER_SEC = float(os.environ.get("VPASS_GPS_STALE_AFTER_SEC", "10"))
COMPASS_I2C_BUS = int(os.environ.get("VPASS_COMPASS_I2C_BUS", "1"))
COMPASS_DECLINATION_DEG = float(os.environ.get("VPASS_COMPASS_DECLINATION_DEG", "0"))
COMPASS_X_OFFSET = float(os.environ.get("VPASS_COMPASS_X_OFFSET", "0"))
COMPASS_Y_OFFSET = float(os.environ.get("VPASS_COMPASS_Y_OFFSET", "0"))
COMPASS_X_SCALE = float(os.environ.get("VPASS_COMPASS_X_SCALE", "1"))
COMPASS_Y_SCALE = float(os.environ.get("VPASS_COMPASS_Y_SCALE", "1"))
COMPASS_HEADING_ALPHA = float(os.environ.get("VPASS_COMPASS_HEADING_ALPHA", "0.25"))
COMPASS_STALE_AFTER_SEC = float(os.environ.get("VPASS_COMPASS_STALE_AFTER_SEC", "5"))

# ── 얼굴 인식 ────────────────────────────────────────────────────────────
FACE_SIZE = (200, 200)
MATCH_THRESHOLD = 52.0          # LBPH confidence (작을수록 유사)
REBOARD_MESSAGE_COOLDOWN = 6.0  # 같은 사람 중복 안내 최소 간격(초)

# ── 구명조끼 시각 확인 (승선 등록 치팅 방지) ─────────────────────────────
# 모듈(홀센서) 신호만 믿으면 조끼를 입지 않고 버클만 채우는 치팅이 가능하다.
# 승선 등록 시 얼굴 아래 상체 ROI 의 HSV 색상 비율을 함께 검사한다.
# 임시 구현(jacketvision.py) — 추후 전용 객체 검출 모델 학습 후 교체 예정.
JACKET_VISION_ENABLED = (
    os.environ.get("VPASS_JACKET_VISION", "1").strip().lower() not in ("0", "false", "off")
)

# 구명조끼 색상 프리셋 (OpenCV HSV: H 0-179, S/V 0-255)
_JACKET_COLOR_PRESETS: dict[str, list[tuple]] = {
    "orange": [((5, 110, 100), (22, 255, 255))],
    "red": [((0, 110, 100), (5, 255, 255)), ((168, 110, 100), (179, 255, 255))],
    "yellow": [((22, 110, 110), (32, 255, 255))],
    "lime": [((32, 90, 110), (58, 255, 255))],  # 형광 연두(작업 조끼류)
}


def _jacket_color_ranges() -> list[tuple]:
    names = os.environ.get("VPASS_JACKET_COLORS", "orange,lime,red")
    ranges: list[tuple] = []
    for name in names.split(","):
        ranges.extend(_JACKET_COLOR_PRESETS.get(name.strip().lower(), []))
    return ranges or list(_JACKET_COLOR_PRESETS["orange"])


JACKET_COLOR_RANGES = _jacket_color_ranges()
# 상체 ROI 에서 구명조끼 색 픽셀 비율이 이 값 이상이면 착용으로 판정
JACKET_MIN_COLOR_RATIO = float(os.environ.get("VPASS_JACKET_MIN_RATIO", "0.4"))
# 상체 ROI 가 화면 밖으로 잘려 남은 면적이 이 비율 미만이면 판단 불가 처리
JACKET_ROI_MIN_VISIBLE = float(os.environ.get("VPASS_JACKET_ROI_MIN_VISIBLE", "0.35"))

# ── 구명조끼 디바이스 / 익수 감지 ────────────────────────────────────────
PING_INTERVAL = 3.0        # 펌웨어 ping 주기(초)
FALL_PING_TIMEOUT = 5.0    # 낙상 후 이 시간 안에 ping 없으면 익수로 판단
SIGNAL_LOSS_TIMEOUT = 10.0 # 착용 중 신호 두절 시 익수로 판단(3회 연속 유실)

# ── 킬 스위치(GPIO) ──────────────────────────────────────────────────────
KILLSWITCH_GPIO_PIN = int(os.environ.get("VPASS_KILLSWITCH_PIN", "17"))

# ── 운항 기록 ───────────────────────────────────────────────────────────
# 출항/입항은 속도로 자동 감지하지 않는다.
# 선장이 '출항 확정' / '입항 확정'을 눌렀을 때만 처리된다.
TRACK_INTERVAL_SEC = 60.0     # 운항 좌표 기록 간격(항해 시간 기준 1분)
# 시뮬레이터가 배속으로 돌면 그만큼 간격을 좁힌다(예: 30배속 → 2초마다 기록).
# 다만 이 값보다 촘촘해지지는 않는다.
MIN_TRACK_INTERVAL_SEC = 1.0
