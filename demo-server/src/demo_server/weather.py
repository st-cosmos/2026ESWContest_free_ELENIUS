"""해양경찰청 관할별 해양 기상 관리.

관제 서버에서 관할(동해/서해/남해/중부/제주)마다 기상 상태를 설정하면,
V-PASS 단말이 해당 관할의 기상을 조회해 자동으로 반영한다.
"""

from __future__ import annotations

import threading
from datetime import datetime

from .config import CONDITIONS, REGIONS

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
    "동해": {"condition": "맑음", "temp_c": 24, "wind": "NE 4.2 m/s", "wave_height_m": 0.8, "water_temp_c": 22.5},
    "서해": {"condition": "흐림", "temp_c": 22, "wind": "NW 5.1 m/s", "wave_height_m": 1.2, "water_temp_c": 21.0},
    "남해": {"condition": "구름조금", "temp_c": 26, "wind": "SE 3.4 m/s", "wave_height_m": 0.6, "water_temp_c": 24.5},
    "중부": {"condition": "비", "temp_c": 21, "wind": "W 6.0 m/s", "wave_height_m": 1.5, "water_temp_c": 20.5},
    "제주": {"condition": "안개", "temp_c": 25, "wind": "S 2.8 m/s", "wave_height_m": 1.0, "water_temp_c": 23.8},
}


def _now_hm() -> str:
    return datetime.now().strftime("%H:%M")


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
                seeded[region] = base
            self._store.save(seeded)

    def all(self) -> dict:
        return self._store.load()

    def get(self, region: str) -> dict | None:
        return self._store.load().get(region)

    def set_condition(self, region: str, condition: str, extras: dict | None = None) -> dict | None:
        if region not in REGIONS or condition not in CONDITIONS:
            return None
        result = {}

        def _upd(data):
            entry = data.get(region, {})
            entry["condition"] = condition
            entry.update(_CONDITION_META.get(condition, {}))
            if extras:
                for key in ("temp_c", "wind", "wave_height_m", "water_temp_c"):
                    if extras.get(key) is not None:
                        entry[key] = extras[key]
            entry["updated_at"] = _now_hm()
            data[region] = entry
            result.update(entry)
            return data

        self._store.update(_upd)
        return result
