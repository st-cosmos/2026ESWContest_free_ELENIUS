"""데모 관제 서버 런타임 — 매니저 생성/배선 + 시뮬레이션 루프."""

from __future__ import annotations

import threading
import time
from datetime import datetime

from . import config, drift
from .geo import parse_position
from .khoa import KhoaClient
from .lora_bridge import LoraBridge
from .ocean import OceanField, region_for
from .portlog import PortLog
from .reports import ReportInbox
from .simulator import Simulator
from .storage import JsonStore
from .vessels import STATUS_DEPARTED, STATUS_DOCKED, VesselRegistry
from .weather import WIND_DIRS, WeatherManager

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
        self.simulator_store = JsonStore(config.SIMULATOR_FILE, {})

        self.vessels = VesselRegistry(self.vessels_store)
        self.reports = ReportInbox(self.reports_store)
        self.portlog = PortLog(self.portlog_store)
        self.weather = WeatherManager(self.weather_store)

        # 국립해양조사원 연동 + 해양 벡터 필드 (키 미설정 시 관제 설정값으로 계산)
        self.khoa = KhoaClient()
        self.ocean = OceanField(self.weather, self.khoa)

        # SOS 로 정지한 배는 표류만 반영한다 (해류 + 풍압)
        self.simulator = Simulator(
            self.simulator_store, drift_provider=self._sim_drift_vector
        )

        self._seed_vessels()

        # 킬 스위치 원격 명령 (메모리 유지 — 단말은 새 seq 만 실행한다)
        self.engine_command: dict | None = None
        self.engine_seq = 0
        self._engine_lock = threading.Lock()

        self._running = False
        self._thread: threading.Thread | None = None
        self.lora: LoraBridge | None = None
        if config.LORA_ENABLED:
            self.lora = LoraBridge(
                self,
                config.LORA_PORT,
                baudrate=config.LORA_BAUDRATE,
                timeout=config.LORA_TIMEOUT_SEC,
            )

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
        if self.lora:
            self.lora.start()

    def stop(self) -> None:
        self._running = False
        if self.lora:
            self.lora.stop()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        elapsed = 0.0
        while self._running:
            time.sleep(config.SIM_TICK_SEC)
            elapsed += config.SIM_TICK_SEC
            try:
                self.simulator.step(config.SIM_TICK_SEC)
                if elapsed >= config.SIM_INTERVAL_SEC:
                    self.vessels.simulate_step(elapsed)
                    self.ocean.sync_observations()
                    elapsed = 0.0
            except Exception as e:  # 시뮬레이션 오류가 서버를 죽이지 않도록
                print(f"[sim] 오류: {e}")

    # ── 표류 (해류 + 풍압) ───────────────────────────────────────────────
    def _sim_drift_region(self) -> str:
        """표류 계산에 쓸 관할.

        신고 관할 → 연결된 V-PASS 단말의 관할 → 좌표 기준 순으로 고른다.
        요구조자 예상 위치(신고 관할 기준)와 시뮬레이터 선박이 서로 다른 방향으로
        흘러가면 안 되므로, 신고가 있을 때는 반드시 같은 관할을 쓴다.
        """
        info = self.simulator.sos_info or {}
        report = self.reports.get(info.get("report_id", "")) if info else None
        if report and report.get("region"):
            return report["region"]
        terminal = self.linked_terminal()
        if terminal and terminal.get("region"):
            return terminal["region"]
        return region_for(self.simulator.lat, self.simulator.lon)

    def _sim_drift_vector(self) -> dict:
        """관할 기상(해류 + 풍압)으로 표류 벡터를 계산한다."""
        return drift.drift_vector(self.weather.get(self._sim_drift_region()) or {})

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

    def ingest_report(self, payload: dict) -> dict:
        """신고 접수 → 수신함에 저장하고 운항 시뮬레이터를 즉시 위치 고정한다.

        실제 단말에서는 킬 스위치가 작동해 배가 멈추므로, 시뮬레이터도 항로
        이동을 중단해야 관제 화면과 상태가 어긋나지 않는다.
        """
        report = self.reports.add(payload)
        self.simulator.lock_for_sos({
            "report_id": report["id"],
            "cause": report["cause"],
            "detail": report.get("detail"),
            "time": report["time"],
            "vessel_name": report.get("vessel_name"),
            "vessel_id": report.get("vessel_id"),
        })
        print(f"[sos] 신고 접수 → 시뮬레이터 위치 고정 ({report.get('vessel_name')})")
        return report

    def close_report(self, report_id: str) -> dict | None:
        """상황 종료 → 신고를 닫고, 남은 신고가 없으면 위치 고정을 해제한다."""
        report = self.reports.close(report_id)
        if report is None:
            return None
        if not self.reports.active():
            self.simulator.release_sos()
            print("[sos] 모든 신고 종료 → 시뮬레이터 위치 고정 해제")
        return report

    # ── 요구조자 예상 위치 (표류 예측) ──────────────────────────────────
    def _report_origin(self, report: dict) -> tuple[float, float]:
        """신고의 익수 지점 좌표. 좌표 문자열이 없으면 선박/시뮬레이터 위치로 폴백."""
        coords = parse_position(report.get("position"))
        if coords is not None:
            return coords
        vessel_id = report.get("vessel_id")
        for vessel in self.vessels.list_public():
            if vessel.get("vessel_id") == vessel_id:
                return float(vessel["lat"]), float(vessel["lon"])
        return self.simulator.lat, self.simulator.lon

    @staticmethod
    def _elapsed_minutes(report: dict) -> float:
        stamp = report.get("time") or report.get("created_at") or ""
        for fmt in ("%Y-%m-%d %H:%M:%S", "%H:%M:%S"):
            try:
                parsed = datetime.strptime(stamp, fmt)
            except ValueError:
                continue
            if fmt == "%H:%M:%S":
                today = datetime.now()
                parsed = parsed.replace(year=today.year, month=today.month, day=today.day)
            return max(0.0, (datetime.now() - parsed).total_seconds() / 60.0)
        return 0.0

    def report_boundary(self, report_id: str, minutes: float | None = None) -> dict | None:
        """신고 1건의 요구조자 예상 위치·확률 바운더리·시간별 탐색 구역.

        익수(mob) 신고에만 의미가 있다. 수동 SOS 는 선내에서 버튼을 누른 것이라
        물에 빠진 사람이 없으므로 표류할 요구조자도 없다. 이 경우 None 을 돌려
        호출자가 404 로 처리하게 한다.
        """
        report = next(
            (r for r in self.reports.list_public() if r.get("id") == report_id), None
        )
        if report is None or report.get("cause") != "mob":
            return None

        lat, lon = self._report_origin(report)
        region = report.get("region") or region_for(lat, lon)
        weather = self.weather.get(region) or {}
        elapsed = self._elapsed_minutes(report) if minutes is None else float(minutes)

        result = drift.predict(lat, lon, weather, elapsed)
        result.update({
            "report": report,
            "region": region,
            "weather": weather,
            "elapsed_actual_min": round(self._elapsed_minutes(report), 1),
            "timeline": drift.timeline(lat, lon, weather, elapsed),
            "survival_hours": drift.survival_window_hours(weather.get("water_temp_c")),
            "vessel": {
                "lat": self.simulator.lat,
                "lon": self.simulator.lon,
                "locked": self.simulator.sos_locked,
                "drift_kn": round(self.simulator.drift_kn, 2),
                "drift_m": round(self.simulator.drift_m),
            },
        })
        return result

    # ── 킬 스위치 원격 제어 (관제 → V-PASS 단말 → BLE 릴레이) ──────────
    def send_engine_command(self, action: str) -> dict | None:
        if action not in ("kill", "restore"):
            return None
        with self._engine_lock:
            self.engine_seq += 1
            self.engine_command = {
                "seq": self.engine_seq,
                "action": action,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            return dict(self.engine_command)

    def terminal_feed(self) -> dict:
        """시뮬레이터 좌표/출입항 명령에 킬 스위치 명령을 얹어 단말로 내려준다."""
        feed = self.simulator.terminal_feed()
        with self._engine_lock:
            feed["engine_command"] = dict(self.engine_command) if self.engine_command else None
        return feed

    # ── 운항 시뮬레이터 ─────────────────────────────────────────────────
    def linked_terminal(self) -> dict | None:
        """시뮬레이터가 좌표를 공급하는 V-PASS 단말(연결된 라이브 선박)."""
        vessels = [v for v in self.vessels.list_public() if v["source"] == "vpass"]
        if not vessels:
            return None
        return next((v for v in vessels if v["live"]), vessels[0])

    def simulator_snapshot(self) -> dict:
        snapshot = self.simulator.snapshot()
        snapshot["time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        snapshot["terminal"] = self.linked_terminal()
        with self._engine_lock:
            snapshot["engine_command"] = dict(self.engine_command) if self.engine_command else None
        return snapshot

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
            "wind_dirs": list(WIND_DIRS.keys()),
            # 진행 중인 SOS — 대시보드에서 요구조자 예상 위치로 유도한다
            "sos": {
                "locked": self.simulator.sos_locked,
                "info": dict(self.simulator.sos_info) if self.simulator.sos_info else None,
                "drift_kn": round(self.simulator.drift_kn, 2),
                "active_reports": len(self.reports.active()),
            },
            "ocean_source": "국립해양조사원" if self.khoa.enabled else "관제 설정값",
        }
