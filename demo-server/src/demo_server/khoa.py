"""국립해양조사원(KHOA) 공공데이터 연동.

`docs/api-list.md` 의 서비스 중 요구조자 표류 예측에 필요한 항목만 사용한다.

  ROMS 수치예측모델 (예측 유향/유속·수온)   data.go.kr 15142227  → 격자 해류장
  해수유동 관측소 실측 유향/유속             data.go.kr 15155531  → 실측 해류
  조류예보(시계열)                          data.go.kr 15156024  → 조류 예보
  조위관측소 실측 풍향/풍속                  data.go.kr 15142518  → 실측 바람
  해양관측부이 최신 관측데이터               data.go.kr 15155516  → 부이(해류·수온·바람)
  국가해양관측망 실측 파랑                   data.go.kr 15155994  → 파고

**인증키가 없으면 이 모듈은 아무 것도 하지 않는다.** 관제 서버는 관제사가 설정한
풍향·풍속·해류 값으로 벡터 필드와 표류 예측을 계산하므로(ocean.py), 키 미설정
상태에서도 시연은 그대로 동작한다.

응답 형식은 data.go.kr 표준(`response.body.items.item`)과 KHOA 오션그리드
(`result.data`) 두 가지를 모두 받아들이도록 방어적으로 파싱한다. 실제 오퍼레이션
경로는 data.go.kr 활용 승인 후 확정되므로 환경변수로 덮어쓸 수 있게 두었다.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config

TIMEOUT = 3.0
CACHE_TTL = 600.0  # 공공데이터는 10분 캐시 (호출 한도 보호)


def _first(mapping: dict, *keys):
    """응답 필드 이름이 서비스마다 달라 여러 후보를 순서대로 시도한다."""
    for key in keys:
        if key in mapping and mapping[key] not in (None, "", "-"):
            return mapping[key]
        upper = key.upper()
        if upper in mapping and mapping[upper] not in (None, "", "-"):
            return mapping[upper]
    return None


def _as_float(value) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _extract_rows(payload) -> list[dict]:
    """data.go.kr / KHOA 오션그리드 응답에서 레코드 목록을 꺼낸다."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []

    # KHOA 오션그리드: {"result": {"data": [...]}} 또는 {"result": {"data": {...}}}
    result = payload.get("result")
    if isinstance(result, dict):
        data = result.get("data")
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
        if isinstance(data, dict):
            return [data]

    # data.go.kr 표준: {"response": {"body": {"items": {"item": [...]}}}}
    body = (payload.get("response") or {}).get("body") if isinstance(payload.get("response"), dict) else None
    if isinstance(body, dict):
        items = body.get("items")
        if isinstance(items, dict):
            item = items.get("item")
            if isinstance(item, list):
                return [r for r in item if isinstance(r, dict)]
            if isinstance(item, dict):
                return [item]
        if isinstance(items, list):
            return [r for r in items if isinstance(r, dict)]
    return []


class KhoaClient:
    """국립해양조사원 조회 클라이언트 (키 미설정 시 전부 None 반환)."""

    def __init__(self, api_key: str | None = None):
        self._key = (api_key or config.KHOA_API_KEY or "").strip() or None
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, object]] = {}

    @property
    def enabled(self) -> bool:
        return self._key is not None

    # ── HTTP ────────────────────────────────────────────────────────────
    def _get(self, url: str, params: dict) -> object | None:
        if not self.enabled:
            return None
        query = dict(params)
        query.setdefault("ServiceKey", self._key)
        query.setdefault("ResultType", "json")
        full = f"{url}?{urllib.parse.urlencode(query)}"

        cached = self._cached(full)
        if cached is not None:
            return cached
        try:
            with urllib.request.urlopen(full, timeout=TIMEOUT) as resp:
                payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as e:
            print(f"[khoa] 조회 실패 ({url}): {e}")
            return None
        self._store(full, payload)
        return payload

    def _cached(self, key: str) -> object | None:
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.time() - hit[0] < CACHE_TTL:
                return hit[1]
        return None

    def _store(self, key: str, payload: object) -> None:
        with self._lock:
            self._cache[key] = (time.time(), payload)

    # ── 개별 서비스 ──────────────────────────────────────────────────────
    def current_grid(self, lat: float, lon: float) -> list[dict] | None:
        """ROMS 예측 유향/유속 격자 → [{lat, lon, dir, kn}, ...]"""
        payload = self._get(config.KHOA_ROMS_URL, {
            "Lat": f"{lat:.4f}", "Lon": f"{lon:.4f}",
        })
        rows = _extract_rows(payload)
        grid: list[dict] = []
        for row in rows:
            row_lat = _as_float(_first(row, "lat", "latitude", "obs_lat"))
            row_lon = _as_float(_first(row, "lon", "longitude", "obs_lon"))
            bearing = _as_float(_first(row, "current_dir", "curr_dir", "dir", "cur_dir"))
            speed = _as_float(_first(row, "current_speed", "curr_speed", "speed", "cur_speed"))
            if None in (row_lat, row_lon, bearing, speed):
                continue
            grid.append({
                "lat": row_lat, "lon": row_lon,
                "dir": bearing % 360, "kn": _to_knots(speed),
            })
        return grid or None

    def current_observation(self, lat: float, lon: float) -> dict | None:
        """해수유동 관측소 실측 유향/유속 (가장 가까운 관측소 1건)."""
        payload = self._get(config.KHOA_CURRENT_URL, {
            "Lat": f"{lat:.4f}", "Lon": f"{lon:.4f}",
        })
        for row in _extract_rows(payload):
            bearing = _as_float(_first(row, "current_dir", "curr_dir", "dir"))
            speed = _as_float(_first(row, "current_speed", "curr_speed", "speed"))
            if bearing is None or speed is None:
                continue
            return {"current_dir": round(bearing % 360), "current_kn": round(_to_knots(speed), 2)}
        return None

    def wind_observation(self, lat: float, lon: float) -> dict | None:
        """조위관측소 실측 풍향/풍속."""
        from .weather import nearest_wind_dir

        payload = self._get(config.KHOA_WIND_URL, {
            "Lat": f"{lat:.4f}", "Lon": f"{lon:.4f}",
        })
        for row in _extract_rows(payload):
            bearing = _as_float(_first(row, "wind_dir", "wd", "dir"))
            speed = _as_float(_first(row, "wind_speed", "ws", "speed"))
            if bearing is None or speed is None:
                continue
            return {
                "wind_dir": nearest_wind_dir(bearing % 360),
                "wind_speed_ms": round(speed, 1),
                "gust_ms": round(_as_float(_first(row, "wind_gust", "gust")) or speed * 1.6, 1),
            }
        return None

    def sea_observation(self, lat: float, lon: float) -> dict | None:
        """부이/관측망 — 수온·파고."""
        payload = self._get(config.KHOA_BUOY_URL, {
            "Lat": f"{lat:.4f}", "Lon": f"{lon:.4f}",
        })
        for row in _extract_rows(payload):
            water = _as_float(_first(row, "water_temp", "wt", "temp"))
            wave = _as_float(_first(row, "wave_height", "wh", "sig_wave_height"))
            if water is None and wave is None:
                continue
            out: dict = {}
            if water is not None:
                out["water_temp_c"] = round(water, 1)
            if wave is not None:
                out["wave_height_m"] = round(wave, 1)
            return out
        return None

    def observe(self, lat: float, lon: float) -> dict | None:
        """한 지점의 해류·바람·수온·파고를 모아 온다 (실패한 항목은 생략)."""
        if not self.enabled:
            return None
        merged: dict = {}
        for fetch in (self.current_observation, self.wind_observation, self.sea_observation):
            try:
                part = fetch(lat, lon)
            except Exception as e:  # 공공데이터 응답 변형에 서버가 죽지 않게
                print(f"[khoa] {fetch.__name__} 파싱 오류: {e}")
                part = None
            if part:
                merged.update(part)
        if not merged:
            return None
        merged["source"] = "국립해양조사원"
        return merged


def _to_knots(speed: float) -> float:
    """유속 단위 보정 — KHOA 는 cm/s 로 주는 서비스가 있어 값 크기로 판별한다."""
    if speed > 25:      # 25 이상이면 cm/s 로 본다 (12kn 이상 해류는 없음)
        return speed * 0.0194384
    return speed
