"""해양경찰청 관할별 해양 기상 관리.

관제 서버에서 관할(동해/서해/남해/중부/제주)마다 기상 상태를 설정하면,
V-PASS 단말이 해당 관할의 기상을 조회해 자동으로 반영한다.

풍향·풍속·해류는 **요구조자 표류 예측(drift.py)과 해양 벡터 필드(ocean.py)의
입력값**이므로 문자열이 아닌 개별 수치 필드로 보관한다.

  wind_dir        8방위 문자열 — 바람이 **불어오는** 방향 (기상 표준)
  wind_speed_ms   풍속 (m/s)
  gust_ms         순간최대풍속 (m/s)
  current_dir     해류가 **흘러가는** 방위 (0~359°)
  current_kn      유속 (kn)

`wind` 은 기존 표기("NE 4.2 m/s")를 쓰는 화면과의 호환을 위해 저장 시 자동
생성되는 파생 필드다. 직접 수정하지 않는다.
"""

from __future__ import annotations

import threading
from datetime import datetime

from .config import CONDITIONS, REGIONS

# 8방위 → 방위각(°). 풍향은 '불어오는 방향'이라 표류는 이 값의 반대로 작용한다.
WIND_DIRS: dict[str, int] = {
    "N": 0, "NE": 45, "E": 90, "SE": 135,
    "S": 180, "SW": 225, "W": 270, "NW": 315,
}

# 기상 상태별 부가 정보 기본값
_CONDITION_META = {
    "맑음": {"precip_prob": 0, "advisory": None},
    "구름조금": {"precip_prob": 10, "advisory": None},
    "흐림": {"precip_prob": 30, "advisory": None},
    "비": {"precip_prob": 80, "advisory": "호우주의보"},
    "안개": {"precip_prob": 20, "advisory": "해상 안개(가시거리 주의)"},
    "뇌우": {"precip_prob": 90, "advisory": "풍랑주의보"},
}

# 최초 시연용 관할별 기본 기상 (pencil 기획 시안과 동일)
_SEED = {
    "동해": {"condition": "맑음", "temp_c": 24, "wind_dir": "NE", "wind_speed_ms": 4.2,
             "gust_ms": 6.8, "current_dir": 55, "current_kn": 0.32,
             "wave_height_m": 0.8, "water_temp_c": 22.5},
    "서해": {"condition": "흐림", "temp_c": 22, "wind_dir": "NW", "wind_speed_ms": 5.1,
             "gust_ms": 8.4, "current_dir": 195, "current_kn": 0.61,
             "wave_height_m": 1.2, "water_temp_c": 21.0},
    "남해": {"condition": "구름조금", "temp_c": 26, "wind_dir": "SW", "wind_speed_ms": 4.2,
             "gust_ms": 6.8, "current_dir": 55, "current_kn": 0.32,
             "wave_height_m": 0.6, "water_temp_c": 24.5},
    "중부": {"condition": "비", "temp_c": 21, "wind_dir": "W", "wind_speed_ms": 6.0,
             "gust_ms": 9.5, "current_dir": 160, "current_kn": 0.48,
             "wave_height_m": 1.5, "water_temp_c": 20.5},
    "제주": {"condition": "안개", "temp_c": 25, "wind_dir": "S", "wind_speed_ms": 2.8,
             "gust_ms": 4.1, "current_dir": 80, "current_kn": 0.74,
             "wave_height_m": 1.0, "water_temp_c": 23.8},
}

# 관제사가 직접 수정할 수 있는 수치 필드와 허용 범위
NUMERIC_FIELDS: dict[str, tuple[float, float]] = {
    "temp_c": (-30.0, 50.0),
    "wind_speed_ms": (0.0, 60.0),
    "gust_ms": (0.0, 80.0),
    "current_dir": (0.0, 359.0),
    "current_kn": (0.0, 12.0),
    "wave_height_m": (0.0, 20.0),
    "water_temp_c": (-2.0, 40.0),
}


def _now_hm() -> str:
    return datetime.now().strftime("%H:%M")


def wind_bearing(wind_dir: str) -> int:
    """풍향 문자열 → 불어오는 방위각(°)."""
    return WIND_DIRS.get(str(wind_dir).upper(), 0)


def wind_push_bearing(wind_dir: str) -> int:
    """풍압이 물체를 밀어내는 방위각(°) — 불어오는 방향의 반대."""
    return (wind_bearing(wind_dir) + 180) % 360


def nearest_wind_dir(bearing: float) -> str:
    """방위각 → 가장 가까운 8방위 문자열."""
    best, best_gap = "N", 999.0
    for name, deg in WIND_DIRS.items():
        gap = abs((bearing - deg + 180) % 360 - 180)
        if gap < best_gap:
            best, best_gap = name, gap
    return best


def _clamp(field: str, value) -> float | None:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    low, high = NUMERIC_FIELDS[field]
    return max(low, min(high, num))


def _decorate(entry: dict) -> dict:
    """파생 필드(wind 표기)를 최신화한다."""
    entry["wind"] = f"{entry.get('wind_dir', 'N')} {entry.get('wind_speed_ms', 0.0)} m/s"
    return entry


def _migrate(entry: dict, region: str) -> dict:
    """구버전 항목(wind 문자열만 있던 형태)을 새 필드 구조로 올린다."""
    seed = _SEED.get(region, {})
    if "wind_dir" not in entry:
        # "NE 4.2 m/s" → dir/speed 로 분해 (실패 시 시드값)
        parts = str(entry.get("wind", "")).split()
        entry["wind_dir"] = (
            parts[0].upper() if parts and parts[0].upper() in WIND_DIRS
            else seed.get("wind_dir", "N")
        )
        speed = None
        if len(parts) >= 2:
            speed = _clamp("wind_speed_ms", parts[1])
        entry["wind_speed_ms"] = (
            speed if speed is not None else seed.get("wind_speed_ms", 0.0)
        )
    for field in ("gust_ms", "current_dir", "current_kn"):
        if entry.get(field) is None:
            entry[field] = seed.get(field, 0.0)
    return _decorate(entry)


class WeatherManager:
    def __init__(self, store):
        self._store = store
        self._lock = threading.Lock()
        self._ensure_seed()

    def _ensure_seed(self) -> None:
        data = self._store.load()
        if not data:
            seeded = {}
            for region in REGIONS:
                base = dict(_SEED[region])
                base.update(_CONDITION_META.get(base["condition"], {}))
                base["updated_at"] = _now_hm()
                base["source"] = "시연 기본값"
                seeded[region] = _decorate(base)
            self._store.save(seeded)
            return
        # 기존 파일이 구버전 스키마면 올려 준다
        migrated = {region: _migrate(dict(entry), region) for region, entry in data.items()}
        if migrated != data:
            self._store.save(migrated)

    def all(self) -> dict:
        return self._store.load()

    def get(self, region: str) -> dict | None:
        return self._store.load().get(region)

    def set_condition(self, region: str, condition: str | None,
                      extras: dict | None = None) -> dict | None:
        """관할 기상을 수정한다.

        condition 을 주면 기상 상태와 부가 정보(강수확률/특보)를 함께 갱신하고,
        extras 로 풍향·풍속·해류 등 개별 수치를 수정할 수 있다.
        """
        if region not in REGIONS:
            return None
        if condition is not None and condition not in CONDITIONS:
            return None
        extras = extras or {}
        wind_dir = extras.get("wind_dir")
        if wind_dir is not None and str(wind_dir).upper() not in WIND_DIRS:
            return None

        result: dict = {}

        def _upd(data):
            entry = data.get(region) or dict(_SEED.get(region, {}))
            if condition is not None:
                entry["condition"] = condition
                entry.update(_CONDITION_META.get(condition, {}))
            if wind_dir is not None:
                entry["wind_dir"] = str(wind_dir).upper()
            for field in NUMERIC_FIELDS:
                if extras.get(field) is not None:
                    value = _clamp(field, extras[field])
                    if value is not None:
                        entry[field] = round(value, 2)
            entry["updated_at"] = _now_hm()
            entry["source"] = extras.get("source") or "관제사 설정"
            data[region] = _migrate(entry, region)
            result.update(data[region])
            return data

        self._store.update(_upd)
        return result

    def apply_observation(self, region: str, obs: dict) -> dict | None:
        """국립해양조사원 실측/예측값을 관할 기상에 반영한다 (khoa.py 전용).

        관제사가 방금 손으로 바꾼 값을 덮어써 시연을 방해하지 않도록,
        호출자가 override=False 로 두면 기존 값이 있으면 유지한다.
        """
        payload = {k: v for k, v in obs.items() if k in NUMERIC_FIELDS or k == "wind_dir"}
        if not payload:
            return None
        payload["source"] = obs.get("source", "국립해양조사원")
        return self.set_condition(region, None, extras=payload)
