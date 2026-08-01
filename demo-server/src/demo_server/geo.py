"""위경도 좌표 표기 유틸 (V-PASS telemetry 표기와 호환)."""

from __future__ import annotations

import math


def _fmt_minutes(value: float) -> tuple[int, float]:
    deg = int(value)
    minutes = (value - deg) * 60
    return deg, minutes


def format_position(lat: float, lon: float) -> str:
    """상태 표기: 34°48.125'N 128°25.402'E"""
    lat_d, lat_m = _fmt_minutes(abs(lat))
    lon_d, lon_m = _fmt_minutes(abs(lon))
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"{lat_d}°{lat_m:06.3f}'{ns} {lon_d}°{lon_m:06.3f}'{ew}"


def advance(lat: float, lon: float, course_deg: float, speed_kn: float, dt: float) -> tuple[float, float]:
    """침로/속력에 따라 dt(초)만큼 전진한 위경도를 계산."""
    dist_nm = speed_kn * dt / 3600.0
    dlat = dist_nm / 60.0 * math.cos(math.radians(course_deg))
    dlon = (
        dist_nm / 60.0 * math.sin(math.radians(course_deg))
        / max(0.2, math.cos(math.radians(lat)))
    )
    return lat + dlat, lon + dlon
