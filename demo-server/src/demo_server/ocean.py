"""해양 벡터 필드 — 해류·풍향/풍속을 지도에 시각화하기 위한 격자 데이터.

Windy 처럼 흐름을 보여주기 위해, 지도 영역(bbox)을 격자로 나눠 각 점의
방위·세기를 만들어 UI(OceanField 캔버스)로 내려보낸다.

출처 우선순위
  1) 국립해양조사원 ROMS 예측 유향/유속 격자 (인증키 설정 시)
  2) 관제사가 관할 기상에서 설정한 해류·풍향·풍속 값

2)의 경우 값이 하나뿐이라 격자 전체가 같은 방향이 되어 지도가 죽어 보인다.
그래서 기준 벡터에 **좌표에 따라 완만하게 변하는 편차**를 더해 실제 해역처럼
흐름이 휘어지게 만든다. 편차는 좌표와 기준값만으로 결정되는 결정적(deterministic)
함수이므로, 관제사가 값을 바꾸지 않는 한 격자는 흔들리지 않는다.
(움직임은 UI 가 이 격자 위에서 입자를 흘려 표현한다.)
"""

from __future__ import annotations

import math
import threading
import time

from . import config
from .khoa import KhoaClient
from .weather import wind_push_bearing

# 관할별 대표 좌표 — 신고 위치의 관할을 추정할 때 사용
REGION_CENTERS: dict[str, tuple[float, float]] = {
    "동해": (38.20, 128.60),
    "서해": (35.50, 126.30),
    "남해": (34.70, 128.20),
    "중부": (37.40, 126.60),
    "제주": (33.30, 126.50),
}

# 기본 관측 영역 (통영 인근 — 운항 시뮬레이터 홈 해역)
DEFAULT_BBOX = {"min_lat": 34.60, "max_lat": 35.05, "min_lon": 128.15, "max_lon": 128.80}

DEFAULT_COLS = 26
DEFAULT_ROWS = 18
MAX_POINTS = 1600

CACHE_TTL = 20.0


def region_for(lat: float, lon: float) -> str:
    """좌표에서 가장 가까운 지방해양경찰청 관할을 고른다."""
    best, best_dist = "남해", float("inf")
    for region, (rlat, rlon) in REGION_CENTERS.items():
        dist = (lat - rlat) ** 2 + ((lon - rlon) * math.cos(math.radians(lat))) ** 2
        if dist < best_dist:
            best, best_dist = region, dist
    return best


def _swirl(u: float, v: float, seed: float) -> tuple[float, float]:
    """격자 좌표(0~1)에 따른 방위 편차(°)와 세기 배율.

    서로 다른 파장의 사인파를 겹쳐 소용돌이처럼 완만히 휘어지는 흐름을 만든다.
    """
    phase = seed * math.tau
    angle = (
        26.0 * math.sin(math.tau * (u * 1.7 + v * 0.9) + phase)
        + 14.0 * math.sin(math.tau * (u * 0.6 - v * 2.3) + phase * 1.7)
        + 7.0 * math.sin(math.tau * (u * 3.1 + v * 2.7) + phase * 0.4)
    )
    scale = (
        1.0
        + 0.30 * math.sin(math.tau * (u * 1.1 - v * 1.4) + phase * 1.3)
        + 0.14 * math.sin(math.tau * (u * 2.6 + v * 0.7) + phase * 2.1)
    )
    return angle, max(0.15, scale)


class OceanField:
    def __init__(self, weather_manager, khoa: KhoaClient | None = None):
        self._weather = weather_manager
        self._khoa = khoa or KhoaClient()
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, dict]] = {}
        self._last_sync = 0.0

    # ── 관할 기상 → 기준 벡터 ────────────────────────────────────────────
    def base_vector(self, layer: str, region: str) -> dict:
        entry = self._weather.get(region) or {}
        if layer == "wind":
            return {
                "bearing": wind_push_bearing(entry.get("wind_dir", "N")),
                "speed": float(entry.get("wind_speed_ms") or 0.0),
                "unit": "m/s",
                "from_dir": entry.get("wind_dir", "N"),
                "gust": float(entry.get("gust_ms") or 0.0),
            }
        return {
            "bearing": float(entry.get("current_dir") or 0.0),
            "speed": float(entry.get("current_kn") or 0.0),
            "unit": "kn",
        }

    # ── 격자 생성 ────────────────────────────────────────────────────────
    def field(self, layer: str = "current", bbox: dict | None = None,
              cols: int = DEFAULT_COLS, rows: int = DEFAULT_ROWS,
              region: str | None = None) -> dict:
        layer = "wind" if layer == "wind" else "current"
        box = {**DEFAULT_BBOX, **(bbox or {})}
        cols = max(4, min(60, int(cols)))
        rows = max(4, min(40, int(rows)))
        while cols * rows > MAX_POINTS:
            cols, rows = max(4, cols - 2), max(4, rows - 2)

        center_lat = (box["min_lat"] + box["max_lat"]) / 2
        center_lon = (box["min_lon"] + box["max_lon"]) / 2
        region = region or region_for(center_lat, center_lon)

        base = self.base_vector(layer, region)
        # 캐시 키에 기준 벡터를 포함한다. 관제사가 풍향·해류를 바꾸면 키가 달라져
        # 캐시를 건너뛰므로 지도 흐름이 즉시 반영된다.
        key = (
            f"{layer}|{region}|{cols}x{rows}"
            f"|{box['min_lat']:.3f},{box['min_lon']:.3f},{box['max_lat']:.3f},{box['max_lon']:.3f}"
            f"|{base['bearing']:.1f},{base['speed']:.3f}"
        )
        cached = self._cached(key)
        if cached is not None:
            return cached
        grid = self._khoa_grid(layer, center_lat, center_lon)
        points, source = (
            (self._from_khoa(grid, box, cols, rows), "국립해양조사원 ROMS")
            if grid else (self._synthesize(base, box, cols, rows, region), "관제 설정값 기반 추정")
        )

        speeds = [p["speed"] for p in points] or [0.0]
        result = {
            "layer": layer,
            "region": region,
            "unit": base["unit"],
            "bbox": box,
            "cols": cols,
            "rows": rows,
            "base": base,
            "range": {"min": round(min(speeds), 3), "max": round(max(speeds), 3)},
            "source": source,
            "live": bool(grid),
            "updated_at": time.strftime("%H:%M:%S"),
            "points": points,
        }
        self._store(key, result)
        return result

    def _synthesize(self, base: dict, box: dict, cols: int, rows: int,
                    region: str) -> list[dict]:
        seed = (sum(ord(c) for c in region) % 97) / 97.0
        bearing, speed = base["bearing"], base["speed"]
        points: list[dict] = []
        for j in range(rows):
            v = j / max(1, rows - 1)
            lat = box["max_lat"] - (box["max_lat"] - box["min_lat"]) * v
            for i in range(cols):
                u = i / max(1, cols - 1)
                lon = box["min_lon"] + (box["max_lon"] - box["min_lon"]) * u
                offset, scale = _swirl(u, v, seed)
                points.append({
                    "lat": round(lat, 5),
                    "lon": round(lon, 5),
                    "dir": round((bearing + offset) % 360, 1),
                    "speed": round(speed * scale, 3),
                })
        return points

    def _from_khoa(self, grid: list[dict], box: dict, cols: int, rows: int) -> list[dict]:
        """관측 격자를 화면 격자에 최근접 보간한다."""
        points: list[dict] = []
        for j in range(rows):
            v = j / max(1, rows - 1)
            lat = box["max_lat"] - (box["max_lat"] - box["min_lat"]) * v
            for i in range(cols):
                u = i / max(1, cols - 1)
                lon = box["min_lon"] + (box["max_lon"] - box["min_lon"]) * u
                near = min(
                    grid,
                    key=lambda g: (g["lat"] - lat) ** 2
                    + ((g["lon"] - lon) * math.cos(math.radians(lat))) ** 2,
                )
                points.append({
                    "lat": round(lat, 5), "lon": round(lon, 5),
                    "dir": round(near["dir"], 1), "speed": round(near["kn"], 3),
                })
        return points

    def _khoa_grid(self, layer: str, lat: float, lon: float) -> list[dict] | None:
        if layer != "current" or not self._khoa.enabled:
            return None
        try:
            return self._khoa.current_grid(lat, lon)
        except Exception as e:
            print(f"[ocean] ROMS 격자 조회 실패: {e}")
            return None

    # ── 관할 기상에 실측값 반영 (주기 호출) ──────────────────────────────
    def sync_observations(self) -> None:
        """국립해양조사원 실측값을 관할 기상에 주기적으로 반영한다."""
        if not self._khoa.enabled:
            return
        now = time.time()
        if now - self._last_sync < config.KHOA_SYNC_INTERVAL_SEC:
            return
        self._last_sync = now
        for region, (lat, lon) in REGION_CENTERS.items():
            obs = self._khoa.observe(lat, lon)
            if obs:
                self._weather.apply_observation(region, obs)
                self._invalidate()

    def _invalidate(self) -> None:
        with self._lock:
            self._cache.clear()

    def _cached(self, key: str) -> dict | None:
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.time() - hit[0] < CACHE_TTL:
                return hit[1]
        return None

    def _store(self, key: str, value: dict) -> None:
        with self._lock:
            self._cache[key] = (time.time(), value)
