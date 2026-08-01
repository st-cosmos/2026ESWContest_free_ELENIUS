"""데모 관제 서버 연동 브리지 (선택적).

환경변수 `VPASS_DEMO_SERVER_URL` 이 설정된 경우에만 활성화된다.
V-PASS 단말이 데모 관제 서버와 주고받는 통신을 담당한다.

  단말 → 관제 서버
    - 텔레메트리(위치/침로/속력/승조원/출입항 상태) 주기 전송  → 선박 카드 실시간 표시
    - 신고(수동 SOS / 자동 익수)                              → 신고 접수 모달
    - 출입항 이벤트                                           → 출입항 자동 수집 로그
  관제 서버 → 단말
    - 관할 해양 기상                                          → V-PASS 기상 표시에 반영

모든 네트워크 호출은 짧은 타임아웃 + 예외 무시로 처리해, 관제 서버가
꺼져 있어도 V-PASS 본체 동작에는 전혀 영향을 주지 않는다.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 2.0


class DemoBridge:
    def __init__(self, base_url: str, vessel_payload_provider):
        self._base = base_url.rstrip("/")
        self._provider = vessel_payload_provider  # () -> dict | None
        self._cached_weather: dict | None = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

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
            try:
                self._sync_vessel()
                self._sync_weather()
            except Exception:
                pass
            time.sleep(3.0)

    # ── 내부 HTTP 헬퍼 ──────────────────────────────────────────────────
    def _post(self, path: str, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._base + path, data=data,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=TIMEOUT).close()
        except (urllib.error.URLError, OSError, ValueError):
            pass

    def _get(self, path: str) -> dict | None:
        try:
            with urllib.request.urlopen(self._base + path, timeout=TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
            return None

    # ── 주기 동기화 ─────────────────────────────────────────────────────
    def _sync_vessel(self) -> None:
        payload = self._provider()
        if payload and payload.get("vessel_id"):
            self._post("/api/ingest/vessel", payload)

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
