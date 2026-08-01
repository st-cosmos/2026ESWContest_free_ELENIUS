"""어선 운항(출항/입항) 관리.

- 속도 기반 자동 출항/입항 감지 → 해양경찰청 자동 신고(시뮬레이션)
- 운항 중 1분 간격으로 시각·좌표를 기록 (어선운항정보 기록 화면)
- 출항 기록지 화면의 '자동 출항/입항 시간'도 여기서 제공
"""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime

from .config import (
    ARRIVE_HOLD_SEC,
    ARRIVE_SPEED_KN,
    DEPART_HOLD_SEC,
    DEPART_SPEED_KN,
    MIN_VOYAGE_SEC,
    TRACK_INTERVAL_SEC,
)


class VoyageManager:
    def __init__(self, store, telemetry, engine, overlay,
                 crew_provider=None, on_depart=None, on_arrive=None):
        self._store = store
        self._telemetry = telemetry
        self._engine = engine
        self._overlay = overlay
        self._crew_provider = crew_provider
        self._on_depart = on_depart
        self._on_arrive = on_arrive

        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

        self._depart_hold = 0.0
        self._arrive_hold = 0.0
        self._active_started_ts: float | None = None
        self._last_track_ts = 0.0
        self.last_report: dict | None = None  # 마지막 자동 신고 내용

        # 재시작 시 진행 중이던 운항 복구
        active = self._find_active()
        if active is not None:
            self._active_started_ts = time.time()
            self._last_track_ts = time.time()

    # ── 저장소 헬퍼 ─────────────────────────────────────────────────────
    def _find_active(self) -> dict | None:
        for v in self._store.load():
            if v.get("status") == "active":
                return v
        return None

    def active_voyage(self) -> dict | None:
        return self._find_active()

    # ── 감시 루프 ────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def _watch(self) -> None:
        tick = 1.0
        while self._running:
            time.sleep(tick)
            try:
                self._step(tick)
            except Exception as e:
                print(f"[voyage] 감시 루프 오류: {e}")

    def _step(self, dt: float) -> None:
        tel = self._telemetry.snapshot()
        speed = tel["speed_kn"]
        active = self._find_active()

        if active is None:
            # 출항 감지
            if speed >= DEPART_SPEED_KN:
                self._depart_hold += dt
                if self._depart_hold >= DEPART_HOLD_SEC:
                    self._depart_hold = 0.0
                    self.start_voyage(auto=True)
            else:
                self._depart_hold = 0.0
            return

        # 운항 중: 1분 간격 좌표 기록
        now = time.time()
        if now - self._last_track_ts >= TRACK_INTERVAL_SEC:
            self._last_track_ts = now
            self._append_point(tel)

        # 입항 감지 (킬 스위치로 멈춘 경우는 입항이 아님)
        age = now - (self._active_started_ts or now)
        engine = self._engine.snapshot()
        if (
            speed < ARRIVE_SPEED_KN
            and age >= MIN_VOYAGE_SEC
            and not engine["killed"]
        ):
            self._arrive_hold += dt
            if self._arrive_hold >= ARRIVE_HOLD_SEC:
                self._arrive_hold = 0.0
                self.end_voyage(auto=True)
        else:
            self._arrive_hold = 0.0

    # ── 출항 / 입항 ─────────────────────────────────────────────────────
    def start_voyage(self, auto: bool = False) -> dict:
        with self._lock:
            if self._find_active() is not None:
                return self._find_active()
            tel = self._telemetry.snapshot()
            now = datetime.now()
            voyage = {
                "id": uuid.uuid4().hex[:12],
                "date": now.strftime("%Y-%m-%d"),
                "departed_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                "arrived_at": None,
                "status": "active",
                "auto_departure": auto,
                "departure_reported": True,  # V-PASS 출항 신고
                "arrival_reported": False,
                # 출항 시점의 승선 명단을 운항 기록에 함께 보관한다
                "crew": self._crew_snapshot(),
                "points": [
                    {"ts": now.strftime("%Y-%m-%d %H:%M:%S"),
                     "coord": tel["position_compact"]}
                ],
            }
            self._store.update(lambda vs: vs + [voyage])
            self._active_started_ts = time.time()
            self._last_track_ts = time.time()

        message = (
            "출항 신고가 해양경찰청에 자동 접수되었습니다"
            if auto
            else "출항 확정 · 시동 잠금 해제 · 해양경찰청 출항 신고 접수"
        )
        self.last_report = {
            "type": "departure",
            "time": voyage["departed_at"],
            "message": message,
        }
        self._overlay.set(message, "#00FFA3")
        if self._on_depart:
            self._on_depart(voyage)
        return voyage

    def end_voyage(self, auto: bool = False) -> dict | None:
        with self._lock:
            active = self._find_active()
            if active is None:
                return None
            tel = self._telemetry.snapshot()
            now = datetime.now()

            def _update(voyages):
                for v in voyages:
                    if v["id"] == active["id"]:
                        v["arrived_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
                        v["status"] = "done"
                        v["auto_arrival"] = auto
                        v["arrival_reported"] = True
                        v["points"].append(
                            {"ts": now.strftime("%Y-%m-%d %H:%M:%S"),
                             "coord": tel["position_compact"]}
                        )
                return voyages

            self._store.update(_update)
            self._active_started_ts = None

        message = (
            "입항 신고가 해양경찰청에 자동 접수되었습니다"
            if auto
            else "입항 확정 · 해양경찰청 입항 신고 접수"
        )
        self.last_report = {
            "type": "arrival",
            "time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "message": message,
        }
        self._overlay.set(message, "#00FFA3")
        if self._on_arrive:
            self._on_arrive(active)
        return active

    def _append_point(self, tel: dict) -> None:
        active = self._find_active()
        if active is None:
            return

        def _update(voyages):
            for v in voyages:
                if v["id"] == active["id"]:
                    v["points"].append(
                        {"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                         "coord": tel["position_compact"]}
                    )
            return voyages

        self._store.update(_update)

    # ── 승선 명단 ────────────────────────────────────────────────────────
    def _crew_snapshot(self) -> list[dict]:
        if self._crew_provider is None:
            return []
        try:
            return list(self._crew_provider())
        except Exception:
            return []

    def sync_active_crew(self) -> None:
        """운항 중 추가 승선이 있으면 해당 운항의 명단을 최신화한다."""
        active = self._find_active()
        if active is None:
            return
        crew = self._crew_snapshot()

        def _update(voyages):
            for v in voyages:
                if v["id"] == active["id"]:
                    v["crew"] = crew
            return voyages

        self._store.update(_update)

    # ── 조회 ────────────────────────────────────────────────────────────
    def list_voyages(self) -> list[dict]:
        voyages = self._store.load()
        result = []
        for v in sorted(voyages, key=lambda v: v["departed_at"], reverse=True):
            result.append({
                "id": v["id"],
                "date": v["date"],
                "departed_at": v["departed_at"],
                "arrived_at": v.get("arrived_at"),
                "status": v.get("status"),
                "crew_count": len(v.get("crew", [])),
                "point_count": len(v.get("points", [])),
            })
        return result

    def get_voyage(self, voyage_id: str) -> dict | None:
        for v in self._store.load():
            if v["id"] == voyage_id:
                return v
        return None

    def latest_summary(self) -> dict | None:
        """출항 기록지/홈 화면용: 가장 최근 운항 요약."""
        voyages = self._store.load()
        if not voyages:
            return None
        v = sorted(voyages, key=lambda v: v["departed_at"], reverse=True)[0]
        return {
            "id": v["id"],
            "date": v["date"],
            "departed_at": v["departed_at"],
            "arrived_at": v.get("arrived_at"),
            "status": v.get("status"),
        }
