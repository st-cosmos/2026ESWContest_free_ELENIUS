"""엔진 제어(시동 잠금 + 비상 킬 스위치).

물리 출력은 릴레이 1개로 본다:
  출력 ON(차단) = 시동 잠금(locked) 또는 비상 정지(killed)

라즈베리파이에서는 gpiozero 로 GPIO 핀을 구동하고,
그 외 환경에서는 상태만 유지하는 시뮬레이션으로 동작한다.
"""

from __future__ import annotations

import asyncio
import importlib.util
import queue
import threading

from .config import (
    IS_RASPBERRY_PI,
    KILLSWITCH_BLE_ADDRESS,
    KILLSWITCH_BLE_CHARACTERISTIC_UUID,
    KILLSWITCH_BLE_ENABLED,
    KILLSWITCH_BLE_NAME,
    KILLSWITCH_BLE_SERVICE_UUID,
    KILLSWITCH_BLE_TIMEOUT_SEC,
    KILLSWITCH_GPIO_PIN,
)


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


class _BleOutput:
    """ESP32-C3 BLE 릴레이 출력. 실패해도 앱 상태 머신은 계속 진행한다."""

    def __init__(
        self,
        *,
        name: str,
        address: str | None,
        service_uuid: str,
        characteristic_uuid: str,
        timeout_sec: float,
    ):
        self.name = name
        self.address = address
        self.service_uuid = service_uuid
        self.characteristic_uuid = characteristic_uuid
        self.timeout_sec = timeout_sec
        self.last_command: str | None = None
        self.last_error: str | None = None
        self._commands: queue.Queue[str | None] = queue.Queue(maxsize=1)
        self._available = importlib.util.find_spec("bleak") is not None
        self._thread: threading.Thread | None = None

        if not self._available:
            self.last_error = "bleak 미설치"
            print("[killswitch] BLE 사용 불가: bleak 패키지가 설치되어 있지 않습니다.")
            return

        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    @property
    def available(self) -> bool:
        return self._available

    def set(self, cut_engine: bool) -> None:
        if not self._available:
            return
        command = "ON" if cut_engine else "OFF"
        try:
            while True:
                self._commands.get_nowait()
        except queue.Empty:
            pass
        try:
            self._commands.put_nowait(command)
        except queue.Full:
            pass

    def _worker(self) -> None:
        while True:
            command = self._commands.get()
            if command is None:
                return
            try:
                asyncio.run(self._send(command))
                self.last_command = command
                self.last_error = None
            except Exception as e:
                self.last_error = str(e)
                print(f"[killswitch] BLE 전송 실패({command}): {e}")

    async def _send(self, command: str) -> None:
        from bleak import BleakClient, BleakScanner  # type: ignore

        target = self.address
        if not target:
            device = await BleakScanner.find_device_by_filter(
                lambda d, ad: (
                    d.name == self.name
                    or self.service_uuid.lower()
                    in {uuid.lower() for uuid in (ad.service_uuids or [])}
                ),
                timeout=self.timeout_sec,
            )
            if device is None:
                raise RuntimeError(f"BLE 장치를 찾지 못했습니다: {self.name}")
            target = device.address

        async with BleakClient(target, timeout=self.timeout_sec) as client:
            await client.write_gatt_char(
                self.characteristic_uuid,
                command.encode("utf-8"),
                response=True,
            )


class EngineController:
    def __init__(self):
        self._lock = threading.Lock()
        self.locked = True    # 시동 잠금(선원 승선 전)
        self.killed = False   # 비상 정지(익수 감지 등)
        self.kill_reason: str | None = None
        self._gpio = _GpioOutput(KILLSWITCH_GPIO_PIN) if IS_RASPBERRY_PI else None
        self._ble = (
            _BleOutput(
                name=KILLSWITCH_BLE_NAME,
                address=KILLSWITCH_BLE_ADDRESS,
                service_uuid=KILLSWITCH_BLE_SERVICE_UUID,
                characteristic_uuid=KILLSWITCH_BLE_CHARACTERISTIC_UUID,
                timeout_sec=KILLSWITCH_BLE_TIMEOUT_SEC,
            )
            if KILLSWITCH_BLE_ENABLED
            else None
        )
        self._listeners: list = []
        self._apply()

    # 엔진 상태 변경을 구독(텔레메트리 시뮬레이터 연동용)
    def on_change(self, fn) -> None:
        self._listeners.append(fn)

    def _apply(self) -> None:
        engaged = self.locked or self.killed
        if self._gpio:
            self._gpio.set(engaged)
        if self._ble:
            self._ble.set(engaged)
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
            "ble": bool(self._ble and self._ble.available),
            "ble_last_command": self._ble.last_command if self._ble else None,
            "ble_error": self._ble.last_error if self._ble else None,
        }
