"""SOS / 비상 신고 관리.

- 수동 SOS: 상태바의 SOS 버튼 (2초 내 3회 클릭 판정은 UI 담당)
- 자동 SOS: 익수(MOB) 감지 시 자동 발보
신고 시 현재 위치·어선 정보가 해양경찰청에 전송된 것으로 처리한다(시뮬레이션).
"""

from __future__ import annotations

import threading
from datetime import datetime


class SosManager:
    def __init__(self, telemetry, vessel_store):
        self._telemetry = telemetry
        self._vessel_store = vessel_store
        self._lock = threading.Lock()
        self._active: dict | None = None
        self._history: list[dict] = []

    def trigger(self, cause: str, detail: str | None = None) -> dict:
        """cause: 'manual' | 'mob'"""
        tel = self._telemetry.snapshot()
        vessel = self._vessel_store.load() or {}
        report = {
            "cause": cause,
            "detail": detail,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "position": tel["position_compact"],
            "vessel_name": vessel.get("name", "미등록"),
            "vessel_id": vessel.get("vessel_id", "-"),
        }
        with self._lock:
            self._active = report
            self._history.append(report)
        return report

    def ack(self) -> None:
        with self._lock:
            self._active = None

    def active(self) -> dict | None:
        with self._lock:
            return dict(self._active) if self._active else None
