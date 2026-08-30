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

from . import blebus
from .config import (
    IS_RASPBERRY_PI,
    KILLSWITCH_BLE_ADAPTER,
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


# 워커의 명령 대기 타임아웃 표시용 (None 은 종료 신호로 이미 쓰인다)
_IDLE = object()


class _BleOutput:
    """ESP32-C3 BLE 릴레이 출력. 실패해도 앱 상태 머신은 계속 진행한다.

    비상 차단 지연을 줄이기 위해 연결을 미리 맺어 유지한다. 워커 스레드가
    유휴 시간에도 연결 상태를 점검해 끊기면 자동 재접속하고, 명령이 오면
    이미 열려 있는 연결에 write 만 한다.
    """

    def __init__(
        self,
        *,
        name: str,
        address: str | None,
        service_uuid: str,
        characteristic_uuid: str,
        timeout_sec: float,
        adapter: str | None = None,
    ):
        self.name = name
        self.address = address
        self.service_uuid = service_uuid
        self.characteristic_uuid = characteristic_uuid
        self.timeout_sec = timeout_sec
        self.adapter = adapter  # 리눅스(BlueZ) 어댑터 지정 ("usb"/"uart"/hciN/BD주소)
        self.last_command: str | None = None
        self.last_error: str | None = None
        self.link_connected = False
        self._commands: queue.Queue[str | None] = queue.Queue(maxsize=1)
        self._desired: str | None = None  # 마지막 요구 상태 — 재접속 후 재전송용
        self._available = importlib.util.find_spec("bleak") is not None

        if not self._available:
            self.last_error = "bleak 미설치"
            print("[killswitch] BLE 사용 불가: bleak 패키지가 설치되어 있지 않습니다.")
            return

        # 자체 스레드+asyncio.run 대신 공용 BLE 루프에서 실행한다.
        # 구명조끼 광고 스캐너와 각자 루프를 돌리면 bleak/BlueZ 전역 매니저가
        # 첫 루프에 묶여 이쪽 연결 시도가 에러 없이 영원히 멈춘다 (blebus.py).
        self._future = blebus.submit(self._supervisor())

    @property
    def available(self) -> bool:
        return self._available

    def set(self, cut_engine: bool) -> None:
        if not self._available:
            return
        self._desired = "ON" if cut_engine else "OFF"
        self._enqueue(self._desired)

    def _enqueue(self, command: str) -> None:
        """최신 명령 하나만 남긴다 (이전 미전송 명령은 버림)."""
        try:
            while True:
                self._commands.get_nowait()
        except queue.Empty:
            pass
        try:
            self._commands.put_nowait(command)
        except queue.Full:
            pass

    async def _supervisor(self) -> None:
        while True:
            try:
                await self._run()
                return  # 종료 신호(None)로 정상 종료
            except Exception as e:
                self.last_error = str(e)
                print(f"[killswitch] BLE 워커 오류, 재시작: {e}")
                await asyncio.sleep(2.0)

    def _poll_command(self):
        """명령을 1초까지 기다린다. 타임아웃이면 _IDLE (연결 상태 점검 기회)."""
        try:
            return self._commands.get(timeout=1.0)
        except queue.Empty:
            return _IDLE

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        client = None
        try:
            while True:
                command = await loop.run_in_executor(None, self._poll_command)

                if command is _IDLE:
                    # 유휴: 연결이 없거나 끊겼으면 미리 다시 맺어 둔다
                    if client is None or not client.is_connected:
                        client = await self._reconnect(client)
                        # 재접속 직후 요구 상태를 다시 보낸다 — 장치가 리부팅하면
                        # fail-safe(ON, 차단)로 돌아가 있어 앱 상태와 어긋난 채
                        # 다음 상태 변화까지 방치된다 (2026-08-29 실측)
                        if client is not None and self._desired is not None:
                            self._enqueue(self._desired)
                    continue

                if command is None:
                    return  # 종료 신호

                for attempt in (1, 2):
                    try:
                        if client is None or not client.is_connected:
                            client = await self._reconnect(client)
                            if client is None:
                                raise RuntimeError(self.last_error or "BLE 연결 실패")
                        await client.write_gatt_char(
                            self.characteristic_uuid,
                            command.encode("utf-8"),
                            response=True,
                        )
                        self.last_command = command
                        self.last_error = None
                        break
                    except Exception as e:
                        self.last_error = str(e)
                        client = await self._drop(client)
                        if attempt == 2:
                            print(f"[killswitch] BLE 전송 실패({command}): {e}")
        finally:
            await self._drop(client)

    async def _drop(self, client):
        self.link_connected = False
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass
        return None

    async def _reconnect(self, client):
        """기존 연결을 정리하고 새로 접속한다. 실패 시 None (에러는 last_error)."""
        from bleak import BleakClient, BleakScanner  # type: ignore

        client = await self._drop(client)

        # BlueZ 어댑터 지정 — 매 접속마다 다시 해석한다 (hciN 번호는 부팅마다
        # 바뀔 수 있음, blebus.resolve_adapter). 다른 백엔드(윈도우 등)에서는
        # bleak 이 bluez kwargs 를 무시한다.
        adapter = blebus.resolve_adapter(self.adapter)
        scanner_kwargs = {"bluez": {"adapter": adapter}} if adapter else {}
        client_kwargs = {"bluez": {"adapter": adapter}} if adapter else {}

        try:
            target = self.address
            if not target:
                device = await BleakScanner.find_device_by_filter(
                    lambda d, ad: (
                        d.name == self.name
                        or self.service_uuid.lower()
                        in {uuid.lower() for uuid in (ad.service_uuids or [])}
                    ),
                    timeout=self.timeout_sec,
                    **scanner_kwargs,
                )
                if device is None:
                    raise RuntimeError(f"BLE 장치를 찾지 못했습니다: {self.name}")
                target = device.address

            # 조끼 스캐너가 같은 어댑터에서 이미 본 장치면 BLEDevice 로 넘겨 bleak 의
            # 자체 스캔(같은 프로세스 스캔과 충돌 → BlueZ InProgress)을 건너뛴다.
            known = blebus.get_device(target, adapter)
            new_client = BleakClient(
                known or target, timeout=self.timeout_sec, **client_kwargs
            )
            await new_client.connect()
            self.link_connected = True
            self.last_error = None
            print(f"[killswitch] BLE 연결 유지 시작: {target}")
            return new_client
        except Exception as e:
            self.last_error = f"BLE 연결 실패: {e}"
            await asyncio.sleep(2.0)  # 장치가 꺼져 있을 때 과도한 재시도 방지
            return None


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
                adapter=KILLSWITCH_BLE_ADAPTER,
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
            "ble_connected": bool(self._ble and self._ble.link_connected),
            "ble_last_command": self._ble.last_command if self._ble else None,
            "ble_error": self._ble.last_error if self._ble else None,
        }
