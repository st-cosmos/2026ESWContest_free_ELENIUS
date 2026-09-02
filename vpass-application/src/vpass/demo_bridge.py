"""데모 관제 서버 연동 브리지 (선택적).

환경변수/실행 옵션으로 데모 전송 계층이 설정된 경우에만 활성화된다.
V-PASS 단말이 데모 관제 서버와 주고받는 통신을 담당한다.

  단말 → 관제 서버
    - 텔레메트리(위치/침로/속력/승조원/출입항 상태) 주기 전송  → 선박 카드 실시간 표시
    - 신고(수동 SOS / 자동 익수)                              → 신고 접수 모달
    - 출입항 이벤트                                           → 출입항 자동 수집 로그
  관제 서버 → 단말
    - 관할 해양 기상                                          → V-PASS 기상 표시에 반영
    - 운항 시뮬레이터 좌표                                    → 실측 GPS 가 없을 때만 사용
    - 지오펜스 출입항 명령                                    → 자동 출항/입항 기록
    - 킬 스위치 원격 명령(kill/restore)                       → 엔진 차단/복구 + BLE 릴레이

모든 네트워크 호출은 짧은 타임아웃 + 예외 무시로 처리해, 관제 서버가
꺼져 있어도 V-PASS 본체 동작에는 전혀 영향을 주지 않는다.
"""

from __future__ import annotations

import threading
import time
import urllib.parse

from .demo_transport import DemoTransport


class DemoBridge:
    def __init__(self, transport: DemoTransport, vessel_payload_provider,
                 sim_feed=None, on_port_command=None, on_engine_command=None):
        self._transport = transport
        self._provider = vessel_payload_provider      # () -> dict | None
        self._sim_feed = sim_feed                     # RemoteSimFeed
        self._on_port_command = on_port_command       # (kind) -> None
        self._on_engine_command = on_engine_command   # (action) -> None
        self._last_command_seq: int | None = None
        self._last_engine_seq: int | None = None
        self._cached_weather: dict | None = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._sim_thread: threading.Thread | None = None

    # ── 수명 주기 ────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        # 시뮬레이터 좌표는 별도 스레드에서 1초 주기로 받아온다.
        # (선박/기상 동기화가 느려져도 지도 움직임은 그대로 따라가야 한다)
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._sim_thread = threading.Thread(target=self._sim_loop, daemon=True)
        self._thread.start()
        self._sim_thread.start()

    def stop(self) -> None:
        self._running = False
        for thread in (self._thread, self._sim_thread):
            if thread:
                thread.join(timeout=2)
        self._transport.close()

    def _loop(self) -> None:
        while self._running:
            try:
                self._sync_vessel()
                self._sync_weather()
            except Exception:
                pass
            time.sleep(3.0)

    def _sim_loop(self) -> None:
        while self._running:
            try:
                self._sync_sim()
            except Exception:
                pass
            time.sleep(1.0)

    # ── 내부 전송 헬퍼 ──────────────────────────────────────────────────
    def _post(self, path: str, payload: dict) -> None:
        self._transport.post(path, payload)

    def _get(self, path: str) -> dict | None:
        return self._transport.get(path)

    # ── 주기 동기화 ─────────────────────────────────────────────────────
    def _sync_vessel(self) -> None:
        payload = self._provider()
        if payload and payload.get("vessel_id"):
            self._post("/api/ingest/vessel", payload)

    def _sync_sim(self) -> None:
        """운항 시뮬레이터 좌표 + 지오펜스 출입항 명령을 받아온다."""
        if self._sim_feed is None:
            return
        data = self._get("/api/sim/terminal")
        if not data:
            self._sim_feed.set(None)
            return

        telemetry = data.get("telemetry") if data.get("active") else None
        if telemetry and telemetry.get("lat") is not None:
            # 시뮬레이터 배속을 함께 실어 보낸다(운항 기록 간격 보정용)
            telemetry = {**telemetry, "time_scale": float(data.get("time_scale") or 1.0)}
        else:
            telemetry = None
        self._sim_feed.set(telemetry)

        # 지오펜스 출입항 명령 — 접속 직후에 남아 있던 마지막 명령은 재실행하지 않는다
        command = data.get("command")
        seq = int(command.get("seq", 0)) if command else 0
        if self._last_command_seq is None:
            self._last_command_seq = seq
        elif command and seq > self._last_command_seq:
            self._last_command_seq = seq
            if self._on_port_command:
                self._on_port_command(command.get("kind", ""))

        # 킬 스위치 원격 명령 — 같은 방식의 seq 래치로 새 명령만 실행한다
        engine = data.get("engine_command")
        engine_seq = int(engine.get("seq", 0)) if engine else 0
        if self._last_engine_seq is None:
            self._last_engine_seq = engine_seq
        elif engine and engine_seq > self._last_engine_seq:
            self._last_engine_seq = engine_seq
            if self._on_engine_command:
                self._on_engine_command(engine.get("action", ""))

    def _sync_weather(self) -> None:
        payload = self._provider()
        region = (payload or {}).get("region")
        if not region:
            return
        weather = self._get(f"/api/weather/{urllib.parse.quote(region)}")
        if weather:
            with self._lock:
                self._cached_weather = weather

    # ── 외부 인터페이스 ─────────────────────────────────────────────────
    def cached_weather(self) -> dict | None:
        with self._lock:
            return dict(self._cached_weather) if self._cached_weather else None

    def push_report(self, report: dict, region: str | None = None) -> None:
        payload = dict(report)
        if region:
            payload["region"] = region
        threading.Thread(
            target=self._post, args=("/api/ingest/report", payload), daemon=True
        ).start()

    def push_port(self, kind: str, vessel_name: str, vessel_id: str, time_str: str) -> None:
        payload = {
            "kind": kind,
            "vessel_name": vessel_name,
            "vessel_id": vessel_id,
            "time": time_str,
        }
        threading.Thread(
            target=self._post, args=("/api/ingest/port", payload), daemon=True
        ).start()
