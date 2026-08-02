"""선박 텔레메트리(GPS 위치/침로/속도) 제공자.

운영 환경(라즈베리파이)에서는 NMEA GPS + QMC5883L 지자계를 사용하고,
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

from .compass import Qmc5883lReader
from .gps import NmeaGpsReader

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
                "source": "sim",
                "lat": self.lat,
                "lon": self.lon,
                "position": format_position(self.lat, self.lon),
                "position_compact": format_position_compact(self.lat, self.lon),
                "course": round(self.course) % 360,
                "speed_kn": round(self.speed_kn, 1),
                "altitude_m": None,
                "satellites": None,
                "gps_updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "gps_ok": self.gps_ok,
                "comm_ok": self.comm_ok,
            }

    @staticmethod
    def now_full() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class HardwareTelemetry:
    """실제 GPS/지자계 기반 텔레메트리.

    GPS는 위치/속도를 제공하고, 지자계가 신선한 값을 갖고 있으면 침로는 지자계
    heading을 우선 사용한다. 지자계 값이 없으면 GPS RMC의 course over ground를
    fallback으로 사용한다.
    """

    def __init__(
        self,
        gps_port: str,
        gps_baudrate: int,
        gps_stale_after_sec: float,
        compass_bus: int,
        compass_declination_deg: float,
        compass_x_offset: float,
        compass_y_offset: float,
        compass_x_scale: float,
        compass_y_scale: float,
        compass_heading_alpha: float,
        compass_stale_after_sec: float,
    ) -> None:
        self.gps = NmeaGpsReader(
            gps_port,
            gps_baudrate,
            stale_after_sec=gps_stale_after_sec,
        )
        self.compass = Qmc5883lReader(
            compass_bus,
            declination_deg=compass_declination_deg,
            x_offset=compass_x_offset,
            y_offset=compass_y_offset,
            x_scale=compass_x_scale,
            y_scale=compass_y_scale,
            heading_alpha=compass_heading_alpha,
            stale_after_sec=compass_stale_after_sec,
        )

    def start(self) -> None:
        self.gps.start()
        self.compass.start()

    def stop(self) -> None:
        self.compass.stop()
        self.gps.stop()

    def set_cruising(self, cruising: bool) -> None:
        """실제 하드웨어 모드에서는 운항 상태를 소프트웨어로 강제하지 않는다."""
        _ = cruising

    def is_cruising_target(self) -> bool:
        return False

    def snapshot(self) -> dict:
        gps = self.gps.snapshot()
        compass = self.compass.snapshot()

        lat = gps["latitude"] if gps["valid"] else None
        lon = gps["longitude"] if gps["valid"] else None
        heading = (
            compass["heading_deg"]
            if compass["fresh"]
            else gps["course_deg"]
        )
        course = round(heading) % 360 if heading is not None else None
        position = format_position(lat, lon) if lat is not None and lon is not None else "-"
        position_compact = (
            format_position_compact(lat, lon) if lat is not None and lon is not None else "-"
        )

        return {
            "source": "hardware",
            "lat": lat,
            "lon": lon,
            "position": position,
            "position_compact": position_compact,
            "course": course,
            "speed_kn": round(float(gps["speed_kn"] or 0.0), 1),
            "altitude_m": gps["altitude_m"],
            "satellites": gps["satellites"],
            "gps_updated_at": gps["updated_at"],
            "gps_ok": gps["fresh"],
            "comm_ok": bool(gps["connected"] or compass["connected"]),
            "gps_error": gps["error"],
            "compass_error": compass["error"],
        }


class RemoteSimFeed:
    """데모 관제 서버 운항 시뮬레이터가 내려주는 좌표 보관소.

    DemoBridge 가 주기적으로 갱신하고, TelemetryRouter 가 읽어 간다.
    갱신이 끊기면(서버 종료 등) 자동으로 무효 처리된다.
    """

    STALE_AFTER_SEC = 8.0

    def __init__(self):
        self._lock = threading.Lock()
        self._data: dict | None = None
        self._ts = 0.0

    def set(self, data: dict | None) -> None:
        with self._lock:
            self._data = data
            self._ts = time.time() if data else 0.0

    def snapshot(self) -> dict | None:
        with self._lock:
            if self._data is None or time.time() - self._ts > self.STALE_AFTER_SEC:
                return None
            return dict(self._data)


class TelemetryRouter:
    """좌표 출처를 선택한다.

      1) 실측 GPS 가 유효하면 언제나 실측값
      2) 실측이 없을 때만 데모 관제 서버 시뮬레이터 좌표
      3) 둘 다 없으면 내장 시뮬레이터

    실측 GPS 를 버리지 않으면서 시뮬레이터로 시연할 수 있게 하는 것이 목적이다.
    """

    def __init__(self, primary, remote: RemoteSimFeed):
        self._primary = primary
        self._remote = remote

    # 수명 주기/제어는 실제 제공자에게 위임한다
    def start(self) -> None:
        self._primary.start()

    def stop(self) -> None:
        self._primary.stop()

    def set_cruising(self, cruising: bool) -> None:
        self._primary.set_cruising(cruising)

    def is_cruising_target(self) -> bool:
        return self._primary.is_cruising_target()

    def snapshot(self) -> dict:
        base = self._primary.snapshot()
        if base["source"] == "hardware" and base["gps_ok"] and base["lat"] is not None:
            return base

        sim = self._remote.snapshot()
        if sim is None:
            return base

        lat, lon = float(sim["lat"]), float(sim["lon"])
        return {
            **base,
            "source": "demo_sim",
            "lat": lat,
            "lon": lon,
            "position": format_position(lat, lon),
            "position_compact": format_position_compact(lat, lon),
            "course": round(float(sim.get("course", base["course"] or 0))) % 360,
            "speed_kn": round(float(sim.get("speed_kn", 0.0)), 1),
            "gps_ok": True,
            "gps_updated_at": sim.get("updated_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        }


def create_telemetry():
    """환경에 맞는 텔레메트리 제공자를 생성한다."""
    from . import config

    provider = config.TELEMETRY_PROVIDER
    if provider not in {"auto", "sim", "hardware"}:
        print(f"[telemetry] unknown provider '{provider}', fallback to auto")
        provider = "auto"

    use_hardware = provider == "hardware" or (
        provider == "auto" and config.IS_RASPBERRY_PI
    )
    if not use_hardware:
        return SimulatedTelemetry()

    return HardwareTelemetry(
        gps_port=config.GPS_PORT,
        gps_baudrate=config.GPS_BAUDRATE,
        gps_stale_after_sec=config.GPS_STALE_AFTER_SEC,
        compass_bus=config.COMPASS_I2C_BUS,
        compass_declination_deg=config.COMPASS_DECLINATION_DEG,
        compass_x_offset=config.COMPASS_X_OFFSET,
        compass_y_offset=config.COMPASS_Y_OFFSET,
        compass_x_scale=config.COMPASS_X_SCALE,
        compass_y_scale=config.COMPASS_Y_SCALE,
        compass_heading_alpha=config.COMPASS_HEADING_ALPHA,
        compass_stale_after_sec=config.COMPASS_STALE_AFTER_SEC,
    )
