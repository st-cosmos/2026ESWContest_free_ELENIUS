"""데모 관제 서버 런타임 — 매니저 생성/배선 + 시뮬레이션 루프."""

from __future__ import annotations

import threading
import time
from datetime import datetime

from . import config
from .portlog import PortLog
from .reports import ReportInbox
from .storage import JsonStore
from .vessels import STATUS_DEPARTED, STATUS_DOCKED, VesselRegistry
from .weather import WeatherManager

# 최초 실행 시 데모 선박 시드 (pencil 기획 시안 기준)
_SEED_VESSELS = [
    {"name": "제3007 통영호", "vessel_id": "경남-통영-12345", "region": "남해",
     "lat": 34.8021, "lon": 128.4234, "course": 245, "speed_kn": 12.4, "crew": 4, "status": STATUS_DEPARTED},
    {"name": "제501 대양호", "vessel_id": "부산-기장-00789", "region": "남해",
     "lat": 35.2147, "lon": 129.2240, "course": 118, "speed_kn": 9.7, "crew": 3, "status": STATUS_DEPARTED},
    {"name": "제7 삼성호", "vessel_id": "전남-여수-04412", "region": "서해",
     "lat": 34.7368, "lon": 127.7483, "course": 202, "speed_kn": 14.1, "crew": 5, "status": STATUS_DEPARTED},
    {"name": "명진 2호", "vessel_id": "강원-속초-11020", "region": "동해",
     "lat": 38.2067, "lon": 128.5983, "course": 0, "speed_kn": 0.0, "crew": 0, "status": STATUS_DOCKED},
    {"name": "해성호", "vessel_id": "인천-옹진-33019", "region": "중부",
     "lat": 37.4683, "lon": 126.6203, "course": 0, "speed_kn": 0.0, "crew": 0, "status": STATUS_DOCKED},
    {"name": "제주 은하호", "vessel_id": "제주-서귀포-77001", "region": "제주",
     "lat": 33.2433, "lon": 126.5517, "course": 0, "speed_kn": 0.0, "crew": 0, "status": STATUS_DOCKED},
]


class Runtime:
    def __init__(self):
        config.ensure_dirs()

        self.vessels_store = JsonStore(config.VESSELS_FILE, [])
        self.reports_store = JsonStore(config.REPORTS_FILE, [])
        self.portlog_store = JsonStore(config.PORTLOG_FILE, [])
        self.weather_store = JsonStore(config.WEATHER_FILE, {})

        self.vessels = VesselRegistry(self.vessels_store)
        self.reports = ReportInbox(self.reports_store)
        self.portlog = PortLog(self.portlog_store)
        self.weather = WeatherManager(self.weather_store)

        self._seed_vessels()

        self._running = False
        self._thread: threading.Thread | None = None

    def _seed_vessels(self) -> None:
        if not self.vessels_store.load():
            for v in _SEED_VESSELS:
                self.vessels.add(v)

    # ── 수명 주기 ────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while self._running:
            time.sleep(config.SIM_INTERVAL_SEC)
            try:
                self.vessels.simulate_step(config.SIM_INTERVAL_SEC)
            except Exception as e:  # 시뮬레이션 오류가 서버를 죽이지 않도록
                print(f"[sim] 오류: {e}")

    # ── 출입항 상태 전환 (수동 선박 데모 조작) ──────────────────────────
    def set_vessel_status(self, vessel_id: str, status: str) -> dict | None:
        result = self.vessels.set_status(vessel_id, status)
        if result and result["changed"]:
            v = result["vessel"]
            self.portlog.add(result["kind"], v["name"], v["vessel_id"])
        return result

    # ── V-PASS 수신 ─────────────────────────────────────────────────────
    def ingest_port(self, kind: str, vessel_name: str, vessel_id: str, time_str: str | None) -> dict:
        return self.portlog.add(kind, vessel_name, vessel_id, time_str)

    # ── 통합 상태 (대시보드 1초 폴링용) ─────────────────────────────────
    def state_snapshot(self) -> dict:
        return {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "vessels": self.vessels.list_public(),
            "stats": self.vessels.stats(),
            "reports": self.reports.list_public(),
            "report_alert": self.reports.pending_alert(),
            "unread_reports": self.reports.unread_count(),
            "port_log": self.portlog.list_public(),
            "weather": self.weather.all(),
            "regions": config.REGIONS,
            "conditions": config.CONDITIONS,
        }
