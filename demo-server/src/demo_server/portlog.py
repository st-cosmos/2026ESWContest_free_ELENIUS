"""출입항 자동 수집 로그.

선박이 출항/입항할 때 자동으로 수집되는 정보:
선박명, 선박식별번호, 출입항 시간, 구분(출항/입항).
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class PortLog:
    def __init__(self, store):
        self._store = store
        self._lock = threading.Lock()

    def add(self, kind: str, vessel_name: str, vessel_id: str, time_str: str | None = None) -> dict:
        if kind not in ("departure", "arrival"):
            kind = "departure"
        entry = {
            "id": uuid.uuid4().hex[:12],
            "kind": kind,
            "vessel_name": vessel_name,
            "vessel_id": vessel_id,
            "time": time_str or _now(),
        }
        self._store.update(lambda es: [entry] + es)
        return entry

    def list_public(self, limit: int = 50) -> list[dict]:
        return self._store.load()[:limit]
