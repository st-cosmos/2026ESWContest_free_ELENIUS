"""선박 텔레메트리(GPS 위치/침로/속도) 제공자.

운영 환경(라즈베리파이)에서는 GPS 모듈(NMEA)을 붙일 자리이며,
개발/시연 환경에서는 통영 인근 해상을 항해하는 시뮬레이터가 동작한다.

- set_cruising(True)  → 순항 속도까지 가속하며 침로를 따라 이동
- set_cruising(False) → 감속 후 정지(정박)
킬 스위치가 작동하면 EngineController 가 set_cruising(False)를 호출한다.
"""

from __future__ import annotations

import math
import random
import threading
import time
from datetime import datetime

# 기본 위치: 통영 인근 (34°48.125'N 128°25.402'E)
HOME_LAT = 34 + 48.125 / 60
HOME_LON = 128 + 25.402 / 60
CRUISE_SPEED_KN = 12.4
BASE_COURSE_DEG = 245.0


def _fmt_minutes(value: float) -> tuple[int, float]:
    deg = int(value)
    minutes = (value - deg) * 60
    return deg, minutes


def format_position(lat: float, lon: float) -> str:
    """상태바 표기: 34°48.125'N 128°25.402'E"""
    lat_d, lat_m = _fmt_minutes(abs(lat))
    lon_d, lon_m = _fmt_minutes(abs(lon))
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"{lat_d}°{lat_m:06.3f}'{ns} {lon_d}°{lon_m:06.3f}'{ew}"


def format_position_compact(lat: float, lon: float) -> str:
    """운항 기록 표기: N34°48.125' E128°25.402'"""
    lat_d, lat_m = _fmt_minutes(abs(lat))
    lon_d, lon_m = _fmt_minutes(abs(lon))
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"{ns}{lat_d}°{lat_m:06.3f}' {ew}{lon_d}°{lon_m:06.3f}'"


class SimulatedTelemetry:
    def __init__(self):
        self.lat = HOME_LAT
        self.lon = HOME_LON
        self.course = BASE_COURSE_DEG
        self.speed_kn = 0.0
        self._target_speed = 0.0
        self.gps_ok = True
        self.comm_ok = True

        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

    # ── 제어 ────────────────────────────────────────────────────────────
    def set_cruising(self, cruising: bool) -> None:
        with self._lock:
            self._target_speed = CRUISE_SPEED_KN if cruising else 0.0

    def is_cruising_target(self) -> bool:
        with self._lock:
            return self._target_speed > 0

    # ── 시뮬레이션 루프 ─────────────────────────────────────────────────
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        last = time.time()
        while self._running:
            time.sleep(1.0)
            now = time.time()
            dt = now - last
            last = now
            with self._lock:
                # 가감속 (약 0.8 kn/s)
                diff = self._target_speed - self.speed_kn
                step = max(-0.8 * dt, min(0.8 * dt, diff))
                self.speed_kn = max(0.0, self.speed_kn + step)

                if self.speed_kn > 0.05:
                    # 침로를 살짝 흔들며 전진
                    self.course = (self.course + random.uniform(-1.5, 1.5)) % 360
                    dist_nm = self.speed_kn * dt / 3600.0  # 해리
                    dlat = dist_nm / 60.0 * math.cos(math.radians(self.course))
                    dlon = (
                        dist_nm / 60.0 * math.sin(math.radians(self.course))
                        / max(0.2, math.cos(math.radians(self.lat)))
                    )
                    self.lat += dlat
                    self.lon += dlon

    # ── 조회 ────────────────────────────────────────────────────────────
    def snapshot(self) -> dict:
        with self._lock:
            return {
                "lat": self.lat,
                "lon": self.lon,
                "position": format_position(self.lat, self.lon),
                "position_compact": format_position_compact(self.lat, self.lon),
                "course": round(self.course) % 360,
                "speed_kn": round(self.speed_kn, 1),
                "gps_ok": self.gps_ok,
                "comm_ok": self.comm_ok,
            }

    @staticmethod
    def now_full() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
