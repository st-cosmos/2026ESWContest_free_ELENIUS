"""위경도 좌표 표기 유틸 (V-PASS telemetry 표기와 호환)."""

from __future__ import annotations

import math
import re

# 도-분 표기 파서. V-PASS 는 "N34°48.125' E128°25.402'",
# 관제 서버는 "34°48.125'N 128°25.402'E" 로 만들기 때문에 두 순서를 모두 받는다.
_DM_SUFFIX = re.compile(r"(\d+)\s*°\s*([\d.]+)\s*'\s*([NSEW])", re.IGNORECASE)
_DM_PREFIX = re.compile(r"([NSEW])\s*(\d+)\s*°\s*([\d.]+)\s*'", re.IGNORECASE)


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


def parse_position(text: str | None) -> tuple[float, float] | None:
    """도-분 표기 문자열을 (lat, lon) 십진수로 되돌린다. 실패 시 None.

    두 표기가 섞여 들어오므로 접두("N34°48.125'")를 먼저 시도한다. 접미 패턴만
    쓰면 "N34°50.544' E128°36.004'" 에서 앞 좌표의 숫자와 뒤 좌표의 방위 문자가
    엉뚱하게 짝지어지기 때문이다. 위도 90°/경도 180° 초과는 잘못 짝지어진
    결과이므로 버리고 다음 패턴으로 넘어간다.
    """
    if not text:
        return None
    for pattern, order in ((_DM_PREFIX, "hdm"), (_DM_SUFFIX, "dmh")):
        found: dict[str, float] = {}
        for match in pattern.finditer(text):
            if order == "dmh":
                deg, minutes, hemi = match.group(1), match.group(2), match.group(3)
            else:
                hemi, deg, minutes = match.group(1), match.group(2), match.group(3)
            try:
                value = int(deg) + float(minutes) / 60.0
            except ValueError:
                continue
            hemi = hemi.upper()
            key = "lat" if hemi in ("N", "S") else "lon"
            if value > (90.0 if key == "lat" else 180.0):
                continue
            if hemi in ("S", "W"):
                value = -value
            found.setdefault(key, value)
        if "lat" in found and "lon" in found:
            return found["lat"], found["lon"]
    return None


def advance(lat: float, lon: float, course_deg: float, speed_kn: float, dt: float) -> tuple[float, float]:
    """침로/속력에 따라 dt(초)만큼 전진한 위경도를 계산."""
    dist_nm = speed_kn * dt / 3600.0
    dlat = dist_nm / 60.0 * math.cos(math.radians(course_deg))
    dlon = (
        dist_nm / 60.0 * math.sin(math.radians(course_deg))
        / max(0.2, math.cos(math.radians(lat)))
    )
    return lat + dlat, lon + dlon
