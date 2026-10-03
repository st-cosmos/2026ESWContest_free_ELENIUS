"""구명조끼 디바이스 레지스트리 + 익수(MOB) 감지.

구명조끼 부착 장치(ESP8266)는 HTTP 로 다음을 보고한다.
  POST /api/wearing {device, worn}   ← 홀센서 착용/해제
  POST /api/ping    {device}         ← 착용 중 3초 주기 생존 신호
  POST /api/fall    {device, magnitude} ← IMU 낙상 감지

익수 판정(셋 중 하나):
  1) 낙상 신고 후 FALL_PING_TIMEOUT 동안 ping 없음      (낙상 + 신호 두절)
  2) 착용 중인데 SIGNAL_LOSS_TIMEOUT 동안 ping 없음     (수중 전파 차단 원리)
     → 가속도(낙상) 감지가 없으므로 바로 판정하지 않고 '경고 단계'를 거친다.
       단말에 경고음 + 모달을 SIGNAL_LOSS_WARNING_SEC 동안 띄우고,
       그 안에 모달을 터치해 끄면(dismiss_signal_warning) 정상 운용 유지,
       응답이 없으면 익수 판정. ping 이 다시 오면 경고는 자동 해제.
  3) 낙하 + 물 감지 플래그 수신 → 즉시 (mob_confirm)   (BLE 펌웨어 로컬 확정)

익수 판정 시 on_mob 콜백이 1회 호출되고(래치), 상황 확인(ack) 전까지 유지된다.
착용 상태가 실제로 바뀔 때(착용↔해제 전환)는 on_wearing 콜백이 호출된다
— 운항 중 버클 해제 경고(Runtime) 등에 사용.
신호 두절 경고가 시작/해제될 때는 on_signal_warning(device_id, active) 콜백이
호출된다 — 오버레이 메시지/로그용. 모달 자체는 UI 가 state 폴링으로 그린다.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime

from .config import FALL_PING_TIMEOUT, SIGNAL_LOSS_TIMEOUT, SIGNAL_LOSS_WARNING_SEC


def _now_str() -> str:
    return datetime.now().strftime("%H:%M:%S")


class DeviceRegistry:
    def __init__(self, on_mob=None, on_wearing=None, on_signal_warning=None):
        self._devices: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._on_mob = on_mob
        self._on_wearing = on_wearing  # (device_id, worn) — 전환 시에만 호출
        self._on_signal_warning = on_signal_warning  # (device_id, active)
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
                # 신호 두절 경고 단계 (낙상 없이 신호만 끊긴 경우)
                "warn_since_ts": None,    # 경고 시작 시각 (None = 경고 아님)
                "warn_since": None,       # 표시용 "HH:MM:SS"
                "warn_dismissed": False,  # 선장이 모달을 꺼서 정상 운용으로 간주 중
                "mob": False,          # 익수 래치
                "mob_cause": None,     # "fall" | "signal_loss" | "fall_water"
                "mob_at": None,
                "pings": deque(maxlen=50),
                "falls": deque(maxlen=20),
            }
        return self._devices[device_id]

    @staticmethod
    def _clear_warning(d: dict) -> bool:
        """경고 상태 초기화. 실제로 경고가 떠 있었으면 True."""
        was_active = d["warn_since_ts"] is not None
        d["warn_since_ts"] = None
        d["warn_since"] = None
        d["warn_dismissed"] = False
        return was_active

    def _notify_warning(self, device_id: str, active: bool) -> None:
        if self._on_signal_warning:
            try:
                self._on_signal_warning(device_id, active)
            except Exception as e:
                print(f"[lifejacket] on_signal_warning 콜백 오류: {e}")

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
            # 착용 상태가 바뀌면 진행 중이던 신호 두절 경고는 의미가 없다
            warn_cleared = self._clear_warning(d)
        if warn_cleared:
            self._notify_warning(device_id, False)
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
            # 신호가 돌아왔다 → 경고(또는 끈 뒤의 유예)는 끝. 다음 두절은 새로 경고
            warn_cleared = self._clear_warning(d)
        if warn_cleared:
            self._notify_warning(device_id, False)

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
            self._clear_warning(d)
            snap = self._snapshot_one(d, time.time())
        if self._on_mob:
            try:
                self._on_mob(snap)
            except Exception as e:
                print(f"[lifejacket] on_mob 콜백 오류: {e}")

    def dismiss_signal_warning(self, device_id: str | None = None) -> bool:
        """신호 두절 경고 모달을 터치해 끔 → 정상 운용 유지.

        해당 장치의 익수 카운트다운을 중단한다. 신호가 여전히 두절 상태라도
        다시 ping 이 수신될 때까지는 경고를 반복하지 않는다(선장이 확인한 상황 —
        예: 선실 안쪽 전파 음영). ping 이 돌아오면 유예가 풀려 다음 두절 때
        다시 경고한다. device_id 미지정 시 떠 있는 모든 경고를 끈다.
        실제로 끈 경고가 있었으면 True.
        """
        dismissed: list[str] = []
        with self._lock:
            targets = (
                [self._devices[device_id]]
                if device_id and device_id in self._devices
                else list(self._devices.values())
            )
            for d in targets:
                if d["warn_since_ts"] is None:
                    continue
                d["warn_since_ts"] = None
                d["warn_since"] = None
                d["warn_dismissed"] = True
                dismissed.append(d["device"])
        for dev in dismissed:
            self._notify_warning(dev, False)
        return bool(dismissed)

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
                self._clear_warning(d)

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
            warned: list[str] = []
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
                        # 가속도(낙상) 감지 + 신호 두절 → 경고 없이 즉시 익수 판정
                        cause = "fall"
                    elif (
                        d["worn"]
                        and d["last_ping_ts"] is not None
                        and now - d["last_ping_ts"] >= SIGNAL_LOSS_TIMEOUT
                    ):
                        # 낙상 감지 없이 신호만 두절 → 경고 단계
                        if d["warn_dismissed"]:
                            pass  # 선장이 확인한 두절 — ping 복귀 전까지 재경고 없음
                        elif d["warn_since_ts"] is None:
                            d["warn_since_ts"] = now
                            d["warn_since"] = _now_str()
                            warned.append(d["device"])
                        elif now - d["warn_since_ts"] >= SIGNAL_LOSS_WARNING_SEC:
                            cause = "signal_loss"
                    if cause:
                        d["mob"] = True
                        d["mob_cause"] = cause
                        d["mob_at"] = _now_str()
                        self._clear_warning(d)
                        fired.append(self._snapshot_one(d, now))
            for dev in warned:
                self._notify_warning(dev, True)
            for snap in fired:
                if self._on_mob:
                    try:
                        self._on_mob(snap)
                    except Exception as e:
                        print(f"[lifejacket] on_mob 콜백 오류: {e}")

    # ── 조회 ────────────────────────────────────────────────────────────
    @staticmethod
    def _warning_one(d: dict, now: float) -> dict | None:
        """진행 중인 신호 두절 경고 {since, elapsed_sec, remaining_sec, total_sec}."""
        if d["warn_since_ts"] is None:
            return None
        elapsed = now - d["warn_since_ts"]
        return {
            "since": d["warn_since"],
            "elapsed_sec": round(elapsed, 1),
            "remaining_sec": round(max(0.0, SIGNAL_LOSS_WARNING_SEC - elapsed), 1),
            "total_sec": SIGNAL_LOSS_WARNING_SEC,
        }

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
            "signal_warning": self._warning_one(d, now),
            "signal_warning_dismissed": d["warn_dismissed"],
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

    def signal_warnings(self) -> list[dict]:
        """진행 중인 신호 두절 경고 목록 — 남은 시간이 적은(급한) 순."""
        with self._lock:
            now = time.time()
            out = []
            for d in self._devices.values():
                w = self._warning_one(d, now)
                if w:
                    out.append({"device": d["device"], **w})
            out.sort(key=lambda w: w["remaining_sec"])
            return out

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
