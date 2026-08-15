"""신고 수신함.

V-PASS 단말에서 접수되는 신고를 저장/조회한다.
- cause == 'manual' : 수동 신고 (선내 SOS 버튼)
- cause == 'mob'    : 자동 신고 (익수 감지 — 물에 빠졌을 때만 발생)

'alerted' 플래그로 '최초 접수 알림 모달'에 아직 노출되지 않은 신규 신고를 구분한다.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class ReportInbox:
    def __init__(self, store):
        self._store = store
        self._lock = threading.Lock()

    def add(self, payload: dict) -> dict:
        cause = payload.get("cause")
        if cause not in ("manual", "mob"):
            cause = "manual"
        report = {
            "id": uuid.uuid4().hex[:12],
            "cause": cause,
            "detail": payload.get("detail"),
            "time": payload.get("time") or _now(),
            "position": payload.get("position", "-"),
            "vessel_name": payload.get("vessel_name", "미상"),
            "vessel_id": payload.get("vessel_id", "-"),
            "region": payload.get("region"),
            "status": "new",          # new | dispatched | closed
            "alerted": False,          # 최초 접수 알림 모달 노출 여부
            "created_at": _now(),
        }
        self._store.update(lambda rs: [report] + rs)
        return report

    def list_public(self) -> list[dict]:
        return self._store.load()

    def pending_alert(self) -> dict | None:
        """아직 최초 접수 알림으로 노출되지 않은 가장 최근 신고."""
        for r in self._store.load():
            if not r.get("alerted"):
                return r
        return None

    def _patch(self, report_id: str, changes: dict) -> dict | None:
        found = {}

        def _upd(rs):
            for r in rs:
                if r["id"] == report_id:
                    r.update(changes)
                    found.update(r)
            return rs

        self._store.update(_upd)
        return found or None

    def mark_alerted(self, report_id: str) -> dict | None:
        return self._patch(report_id, {"alerted": True})

    def dispatch(self, report_id: str) -> dict | None:
        return self._patch(report_id, {"status": "dispatched", "alerted": True})

    def close(self, report_id: str) -> dict | None:
        return self._patch(report_id, {"status": "closed", "alerted": True})

    def unread_count(self) -> int:
        return sum(1 for r in self._store.load() if r.get("status") == "new")

    def active(self) -> list[dict]:
        """아직 종료되지 않은 신고 (new · dispatched)."""
        return [r for r in self._store.load() if r.get("status") != "closed"]

    def get(self, report_id: str) -> dict | None:
        for r in self._store.load():
            if r.get("id") == report_id:
                return r
        return None
