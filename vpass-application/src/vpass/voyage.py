"""어선 운항(출항/입항) 관리.

- 속도로는 출입항을 판정하지 않는다. 출항/입항은
  데모 관제 서버의 지오펜스 통과 판정(또는 수동 확정)으로만 기록된다.
- 운항 중 항해 시간 기준 1분 간격으로 시각·좌표를 기록 (어선운항정보 기록 화면)
  운항 시뮬레이터가 배속으로 돌면 그 배속만큼 실제 기록 간격도 좁아진다
- 출항 기록지 화면의 '출항/입항 시간'도 여기서 제공
"""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime

from .config import MIN_TRACK_INTERVAL_SEC, TRACK_INTERVAL_SEC


class VoyageManager:
    def __init__(self, store, telemetry, overlay,
                 crew_provider=None, on_depart=None, on_arrive=None):
        self._store = store
        self._telemetry = telemetry
        self._overlay = overlay
        self._crew_provider = crew_provider
        self._on_depart = on_depart
        self._on_arrive = on_arrive

        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

        self._last_track_ts = 0.0
        self.last_report: dict | None = None  # 마지막 출입항 신고 내용

        # 재시작 시 진행 중이던 운항 복구
        if self._find_active() is not None:
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
        while self._running:
            time.sleep(1.0)
            try:
                self._step()
            except Exception as e:
                print(f"[voyage] 감시 루프 오류: {e}")

    def _step(self) -> None:
        """운항 중 주기적으로 좌표를 기록한다(기본 1분 간격).

        데모 관제 서버의 운항 시뮬레이터가 배속으로 돌 때는 그 배속만큼 간격을
        좁혀서, 기록이 '항해 시간 기준 1분 간격'이 되도록 맞춘다.

        출항/입항은 속도로 자동 판정하지 않는다. 저속으로 오래 정박해 있어도
        운항은 계속 유지되며, 지오펜스 판정이나 수동 신고로만 기록된다.
        """
        if self._find_active() is None:
            return

        tel = self._telemetry.snapshot()
        now = time.time()
        if now - self._last_track_ts >= self._track_interval(tel):
            self._last_track_ts = now
            self._append_point(tel)

    @staticmethod
    def _track_interval(tel: dict) -> float:
        """시뮬레이터 배속을 반영한 좌표 기록 간격(초)."""
        scale = float(tel.get("time_scale") or 1.0)
        # 정박 중에는(속력 0) 촘촘히 남길 이유가 없다
        if scale <= 1.0 or tel.get("speed_kn", 0.0) <= 0.1:
            return TRACK_INTERVAL_SEC
        return max(MIN_TRACK_INTERVAL_SEC, TRACK_INTERVAL_SEC / scale)

    # ── 출항 / 입항 ─────────────────────────────────────────────────────
    def start_voyage(self) -> dict:
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
            self._last_track_ts = time.time()

        message = "출항 신고가 해양경찰청에 접수되었습니다"
        self.last_report = {
            "type": "departure",
            "time": voyage["departed_at"],
            "message": message,
        }
        self._overlay.set(message, "#00FFA3")
        if self._on_depart:
            self._on_depart(voyage)
        return voyage

    def end_voyage(self) -> dict | None:
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
                        v["arrival_reported"] = True
                        v["points"].append(
                            {"ts": now.strftime("%Y-%m-%d %H:%M:%S"),
                             "coord": tel["position_compact"]}
                        )
                return voyages

            self._store.update(_update)

        message = "입항 신고가 해양경찰청에 접수되었습니다"
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
