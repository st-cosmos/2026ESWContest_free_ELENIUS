"""요구조자 표류 예측 (Leeway) — 생존 가능성·구조 효율을 높이는 탐색 구역 계산.

시연용 근사 모델이며 SAROPS/CANSARP 급 수치모델이 아니다. 근거는 다음과 같다.

  표류 벡터 = 해류 벡터(100%) + 풍압 벡터(풍속의 LEEWAY_RATIO, 기본 3%)
    · 사람은 수면에 거의 잠겨 있어 해류를 그대로 따라간다.
    · 노출된 상체가 받는 풍압(leeway)은 통상 풍속의 2~4% 로 본다.
    · 풍향은 '불어오는 방향'이므로 풍압은 그 반대 방향으로 작용한다.

  탐색 반경 = 경과 시간에 비례해 커지는 위치 오차의 확률 구간
    · 오차 반경이 2차원 정규분포를 따른다고 보면 거리는 Rayleigh 분포가 되고,
      포함 확률 p 의 반경은  r(p) = σ · sqrt(-2 · ln(1 - p)) 이다.
    · σ(t) = DRIFT_SPREAD_NM_PER_HOUR × 경과시간(h)
    · 기본값(0.28 nm/h)에서 60분 95% 반경은 약 1.27 km 로, 해경 초기 탐색
      구역 규모와 비슷하다.

  탐색 우선 구역 = 표류 방위 ± DRIFT_SECTOR_HALF_ANGLE 부채꼴
"""

from __future__ import annotations

import math

from . import config
from .geo import advance, format_position
from .weather import wind_push_bearing

MS_TO_KN = 1.94384
NM_TO_M = 1852.0

# 포함 확률 → Rayleigh 분포 계수 (r = σ·계수)
PROBABILITY_STEPS: tuple[tuple[int, float], ...] = (
    (50, math.sqrt(-2 * math.log(0.50))),   # 1.177
    (75, math.sqrt(-2 * math.log(0.25))),   # 1.665
    (95, math.sqrt(-2 * math.log(0.05))),   # 2.448
)

# 화면 타임라인에 노출하는 경과 시간(분)
TIME_STEPS_MIN: tuple[int, ...] = (10, 30, 60, 120)


def _vector(bearing_deg: float, magnitude: float) -> tuple[float, float]:
    """방위각(북=0, 시계방향)과 크기 → (북쪽 성분, 동쪽 성분)."""
    rad = math.radians(bearing_deg)
    return magnitude * math.cos(rad), magnitude * math.sin(rad)


def drift_vector(weather: dict) -> dict:
    """관할 기상(해류+바람) → 합성 표류 벡터.

    반환: {current_kn, current_dir, wind_kn, wind_dir(압류 방위), speed_kn, bearing}
    """
    current_kn = float(weather.get("current_kn") or 0.0)
    current_dir = float(weather.get("current_dir") or 0.0)
    wind_ms = float(weather.get("wind_speed_ms") or 0.0)
    push_bearing = wind_push_bearing(weather.get("wind_dir", "N"))
    leeway_kn = wind_ms * config.LEEWAY_RATIO * MS_TO_KN

    cn, ce = _vector(current_dir, current_kn)
    wn, we = _vector(push_bearing, leeway_kn)
    north, east = cn + wn, ce + we
    speed = math.hypot(north, east)
    bearing = math.degrees(math.atan2(east, north)) % 360 if speed > 1e-9 else current_dir

    return {
        "current_kn": round(current_kn, 2),
        "current_dir": round(current_dir),
        "leeway_kn": round(leeway_kn, 2),
        "leeway_dir": round(push_bearing),
        "leeway_ratio": config.LEEWAY_RATIO,
        "speed_kn": round(speed, 2),
        "bearing": round(bearing),
    }


def _rings(elapsed_h: float) -> list[dict]:
    sigma_nm = config.DRIFT_SPREAD_NM_PER_HOUR * elapsed_h
    rings = []
    for probability, factor in PROBABILITY_STEPS:
        radius_nm = sigma_nm * factor
        radius_m = radius_nm * NM_TO_M
        rings.append({
            "probability": probability,
            "radius_nm": round(radius_nm, 3),
            "radius_m": round(radius_m),
            "area_km2": round(math.pi * (radius_m / 1000.0) ** 2, 2),
        })
    return rings


def predict(lat: float, lon: float, weather: dict, elapsed_min: float) -> dict:
    """익수 지점과 경과 시간으로 예상 중심 위치·확률 반경·탐색 부채꼴을 계산한다."""
    elapsed_min = max(0.0, float(elapsed_min))
    elapsed_h = elapsed_min / 60.0
    vector = drift_vector(weather)

    distance_nm = vector["speed_kn"] * elapsed_h
    center_lat, center_lon = advance(
        lat, lon, vector["bearing"], vector["speed_kn"], elapsed_min * 60.0
    )
    rings = _rings(elapsed_h)

    return {
        "incident": {
            "lat": round(lat, 6), "lon": round(lon, 6),
            "position": format_position(lat, lon),
        },
        "center": {
            "lat": round(center_lat, 6), "lon": round(center_lon, 6),
            "position": format_position(center_lat, center_lon),
        },
        "elapsed_min": round(elapsed_min, 1),
        "drift": vector,
        "distance_nm": round(distance_nm, 3),
        "distance_m": round(distance_nm * NM_TO_M),
        "rings": rings,
        "sector": {
            "bearing": vector["bearing"],
            "half_angle": config.DRIFT_SECTOR_HALF_ANGLE,
            "radius_m": rings[-1]["radius_m"],
        },
        "model": {
            "leeway_ratio": config.LEEWAY_RATIO,
            "spread_nm_per_hour": config.DRIFT_SPREAD_NM_PER_HOUR,
            "note": "해류 100% + 풍속 3% 압류, 반경은 Rayleigh 확률 구간 (시연용 근사)",
        },
    }


def timeline(lat: float, lon: float, weather: dict,
             elapsed_min: float, steps: tuple[int, ...] = TIME_STEPS_MIN) -> list[dict]:
    """현재 경과 시간 + 예정 시간대별 탐색 구역 요약 (표 표시용)."""
    marks: list[float] = [elapsed_min] + [float(s) for s in steps if s > elapsed_min]
    out = []
    for minutes in marks:
        p = predict(lat, lon, weather, minutes)
        ring95 = p["rings"][-1]
        out.append({
            "elapsed_min": p["elapsed_min"],
            "current": abs(minutes - elapsed_min) < 1e-6,
            "center": p["center"],
            "distance_m": p["distance_m"],
            "rings": p["rings"],
            "radius_m": ring95["radius_m"],
            "area_km2": ring95["area_km2"],
        })
    return out


def survival_window_hours(water_temp_c: float | None) -> float | None:
    """수온별 기대 생존 시간(시간) — 미해안경비대 저체온 생존곡선 근사.

    구조 우선순위 판단을 돕는 참고값이며, 개인차가 크므로 화면에서도 '추정'으로
    표기한다. 수온을 모르면 None.
    """
    if water_temp_c is None:
        return None
    table = [(0, 0.75), (5, 1.5), (10, 3.0), (15, 6.0), (20, 12.0), (25, 24.0)]
    temp = float(water_temp_c)
    if temp <= table[0][0]:
        return table[0][1]
    for (t0, h0), (t1, h1) in zip(table, table[1:]):
        if temp <= t1:
            ratio = (temp - t0) / (t1 - t0)
            return round(h0 + (h1 - h0) * ratio, 1)
    return table[-1][1]
