"""엔진 제어(시동 잠금 + 비상 킬 스위치).

물리 출력은 릴레이 1개로 본다:
  출력 ON(차단) = 시동 잠금(locked) 또는 비상 정지(killed)

라즈베리파이에서는 gpiozero 로 GPIO 핀을 구동하고,
그 외 환경에서는 상태만 유지하는 시뮬레이션으로 동작한다.
"""

from __future__ import annotations

import threading

from .config import IS_RASPBERRY_PI, KILLSWITCH_GPIO_PIN


class _GpioOutput:
    """gpiozero 기반 릴레이 출력. 실패 시 조용히 시뮬레이션으로 대체."""

    def __init__(self, pin: int):
        self._device = None
        try:
            from gpiozero import DigitalOutputDevice  # type: ignore

            self._device = DigitalOutputDevice(pin, initial_value=True)
        except Exception as e:
            print(f"[killswitch] GPIO 사용 불가, 시뮬레이션 모드로 동작: {e}")

    @property
    def available(self) -> bool:
        return self._device is not None

    def set(self, cut_engine: bool) -> None:
        if self._device is None:
            return
        if cut_engine:
            self._device.on()
        else:
            self._device.off()


class EngineController:
    def __init__(self):
        self._lock = threading.Lock()
        self.locked = True    # 시동 잠금(선원 승선 전)
        self.killed = False   # 비상 정지(익수 감지 등)
        self.kill_reason: str | None = None
        self._gpio = _GpioOutput(KILLSWITCH_GPIO_PIN) if IS_RASPBERRY_PI else None
        self._listeners: list = []
        self._apply()

    # 엔진 상태 변경을 구독(텔레메트리 시뮬레이터 연동용)
    def on_change(self, fn) -> None:
        self._listeners.append(fn)

    def _apply(self) -> None:
        engaged = self.locked or self.killed
        if self._gpio:
            self._gpio.set(engaged)
        for fn in list(self._listeners):
            try:
                fn(self.snapshot())
            except Exception:
                pass

    # ── 시동 잠금 ────────────────────────────────────────────────────────
    def unlock(self) -> None:
        with self._lock:
            self.locked = False
            self._apply()

    def lock(self) -> None:
        with self._lock:
            self.locked = True
            self._apply()

    # ── 비상 킬 스위치 ──────────────────────────────────────────────────
    def kill(self, reason: str) -> None:
        with self._lock:
            self.killed = True
            self.kill_reason = reason
            self._apply()

    def restore(self) -> None:
        with self._lock:
            self.killed = False
            self.kill_reason = None
            self._apply()

    def snapshot(self) -> dict:
        return {
            "locked": self.locked,
            "killed": self.killed,
            "kill_reason": self.kill_reason,
            "engaged": self.locked or self.killed,
            "gpio": bool(self._gpio and self._gpio.available),
        }
