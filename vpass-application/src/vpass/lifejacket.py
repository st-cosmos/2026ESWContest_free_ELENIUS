"""구명조끼 디바이스 레지스트리 + 익수(MOB) 감지.

구명조끼 부착 장치(ESP8266)는 HTTP 로 다음을 보고한다.
  POST /api/wearing {device, worn}   ← 홀센서 착용/해제
  POST /api/ping    {device}         ← 착용 중 3초 주기 생존 신호
  POST /api/fall    {device, magnitude} ← IMU 낙상 감지

익수 판정(셋 중 하나):
  1) 낙상 신고 후 FALL_PING_TIMEOUT 동안 ping 없음      (낙상 + 신호 두절)
  2) 착용 중인데 SIGNAL_LOSS_TIMEOUT 동안 ping 없음     (수중 전파 차단 원리)
  3) 낙하 + 물 감지 플래그 수신 → 즉시 (mob_confirm)   (BLE 펌웨어 로컬 확정)

익수 판정 시 on_mob 콜백이 1회 호출되고(래치), 상황 확인(ack) 전까지 유지된다.
착용 상태가 실제로 바뀔 때(착용↔해제 전환)는 on_wearing 콜백이 호출된다
— 운항 중 버클 해제 경고(Runtime) 등에 사용.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime

from .config import FALL_PING_TIMEOUT, SIGNAL_LOSS_TIMEOUT


def _now_str() -> str:
    return datetime.now().strftime("%H:%M:%S")


class DeviceRegistry:
    def __init__(self, on_mob=None, on_wearing=None):
        self._devices: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._on_mob = on_mob
        self._on_wearing = on_wearing  # (device_id, worn) — 전환 시에만 호출
        self._running = False
        self._thread: threading.Thread | None = None

    def _get(self, device_id: str) -> dict:
        if device_id not in self._devices:
            self._devices[device_id] = {
                "device": device_id,
                "worn": False,
                "worn_since": None,
                "last_ping_ts": None,
                "last_ping": "-",
                "last_fall_ts": None,
                "last_fall": "-",
                "fall_magnitude": None,
                "mob": False,          # 익수 래치
                "mob_cause": None,     # "fall" | "signal_loss" | "fall_water"
                "mob_at": None,
                "pings": deque(maxlen=50),
                "falls": deque(maxlen=20),
            }
        return self._devices[device_id]

    # ── 디바이스 이벤트 수신 ────────────────────────────────────────────
    def set_wearing(self, device_id: str, worn: bool) -> None:
        with self._lock:
            d = self._get(device_id)
            changed = d["worn"] != worn
            d["worn"] = worn
            d["worn_since"] = time.time() if worn else None
            if worn:
                # 착용 직후 유예를 위해 ping 기준 시각을 현재로 초기화
                d["last_ping_ts"] = time.time()
            else:
                # 정상 탈의: 낙상/신호 추적 초기화 (익수 래치는 유지)
                d["last_fall_ts"] = None
        # 실제 전환일 때만 알림 — 펌웨어가 같은 상태를 재전송해도 중복 호출 없음
        if changed and self._on_wearing:
            try:
                self._on_wearing(device_id, worn)
            except Exception as e:
                print(f"[lifejacket] on_wearing 콜백 오류: {e}")

    def ping(self, device_id: str) -> None:
        with self._lock:
            d = self._get(device_id)
            now = time.time()
            t = _now_str()
            d["last_ping_ts"] = now
            d["last_ping"] = t
            d["pings"].append({"time": t})
            # 낙상 후에도 ping 이 계속 수신되면(5초 경과) 생존으로 보고 낙상 해제
            if d["last_fall_ts"] is not None and not d["mob"]:
                if now - d["last_fall_ts"] > FALL_PING_TIMEOUT:
                    d["last_fall_ts"] = None

    def fall(self, device_id: str, magnitude: float) -> None:
        with self._lock:
            d = self._get(device_id)
            t = _now_str()
            d["last_fall_ts"] = time.time()
            d["last_fall"] = t
            d["fall_magnitude"] = round(magnitude, 2)
            d["falls"].append({"time": t, "magnitude": round(magnitude, 2)})

    def mob_confirm(self, device_id: str, cause: str = "fall_water") -> None:
        """장치가 스스로 익수를 확정해 보고한 경우(낙하 + 물 감지) 즉시 래치.

        타임아웃을 기다리지 않는다 — 이 신호가 도달했다는 것 자체가 입수 전후의
        마지막 송신 기회를 살린 것이므로. 이미 래치돼 있으면 무시(중복 발보 방지).
        """
        with self._lock:
            d = self._get(device_id)
            if d["mob"]:
                return
            d["mob"] = True
            d["mob_cause"] = cause
            d["mob_at"] = _now_str()
            snap = self._snapshot_one(d, time.time())
        if self._on_mob:
            try:
                self._on_mob(snap)
            except Exception as e:
                print(f"[lifejacket] on_mob 콜백 오류: {e}")

    def ack(self, device_id: str | None = None) -> None:
        """상황 확인: 익수 래치 해제 (device_id 미지정 시 전체)."""
        with self._lock:
            targets = (
                [self._devices[device_id]]
                if device_id and device_id in self._devices
                else self._devices.values()
            )
            for d in targets:
                d["mob"] = False
                d["mob_cause"] = None
                d["mob_at"] = None
                d["last_fall_ts"] = None

    # ── 익수 감시 루프 ──────────────────────────────────────────────────
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
            time.sleep(0.5)
            fired: list[dict] = []
            with self._lock:
                now = time.time()
                for d in self._devices.values():
                    if d["mob"]:
                        continue
                    cause = None
                    ref = d["last_ping_ts"] or d["last_fall_ts"]
                    if (
                        d["last_fall_ts"] is not None
                        and ref is not None
                        and now - ref >= FALL_PING_TIMEOUT
                    ):
                        cause = "fall"
                    elif (
                        d["worn"]
                        and d["last_ping_ts"] is not None
                        and now - d["last_ping_ts"] >= SIGNAL_LOSS_TIMEOUT
                    ):
                        cause = "signal_loss"
                    if cause:
                        d["mob"] = True
                        d["mob_cause"] = cause
                        d["mob_at"] = _now_str()
                        fired.append(self._snapshot_one(d, now))
            for snap in fired:
                if self._on_mob:
                    try:
                        self._on_mob(snap)
                    except Exception as e:
                        print(f"[lifejacket] on_mob 콜백 오류: {e}")

    # ── 조회 ────────────────────────────────────────────────────────────
    def _snapshot_one(self, d: dict, now: float) -> dict:
        since = None if d["last_ping_ts"] is None else round(now - d["last_ping_ts"], 1)
        return {
            "device": d["device"],
            "worn": d["worn"],
            "last_ping": d["last_ping"],
            "seconds_since_ping": since,
            "signal_ok": since is not None and since < SIGNAL_LOSS_TIMEOUT / 2,
            "last_fall": d["last_fall"],
            "fall_magnitude": d["fall_magnitude"],
            "fall_pending": d["last_fall_ts"] is not None and not d["mob"],
            "mob": d["mob"],
            "mob_cause": d["mob_cause"],
            "mob_at": d["mob_at"],
            "pings": list(d["pings"])[-10:],
            "falls": list(d["falls"])[-5:],
        }

    def snapshot(self) -> list[dict]:
        with self._lock:
            now = time.time()
            return [self._snapshot_one(d, now) for d in self._devices.values()]

    def worn_count(self) -> int:
        with self._lock:
            return sum(1 for d in self._devices.values() if d["worn"])

    def is_worn(self, device_id: str | None) -> bool | None:
        """장치 미배정(None)이면 None, 아니면 착용 여부."""
        if not device_id:
            return None
        with self._lock:
            d = self._devices.get(device_id)
            return bool(d and d["worn"])

    def worn_devices(self) -> list[dict]:
        """착용 중인 장치 목록 [{device, worn_since}] — 승선 시 동적 매칭용."""
        with self._lock:
            return [
                {"device": d["device"], "worn_since": d["worn_since"]}
                for d in self._devices.values()
                if d["worn"]
            ]

    def any_mob(self) -> bool:
        with self._lock:
            return any(d["mob"] for d in self._devices.values())
