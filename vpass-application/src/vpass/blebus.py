"""프로세스 공용 BLE asyncio 루프.

bleak 의 BlueZ(리눅스) 백엔드는 프로세스 전역 D-Bus 매니저를 "처음 사용한
asyncio 루프"에 바인딩한다. 구명조끼 광고 스캐너(jacketble)와 BLE 킬 스위치
(killswitch)가 각자 스레드에서 따로 루프를 돌리면, 두 번째 루프의 await 가
영원히 반환되지 않는 교착이 생긴다 — 에러도 없이 연결 시도가 멈춘 것처럼
보인다 (라즈베리파이 실기기에서 재현·확인, 2026-08-16). Windows(WinRT)
백엔드는 전역 매니저가 없어 이 문제가 드러나지 않는다.

그래서 BLE 를 쓰는 모든 코드는 이 모듈의 단일 백그라운드 루프에 코루틴을
제출해 실행한다.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from collections.abc import Coroutine

_lock = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None


def _ensure_loop() -> asyncio.AbstractEventLoop:
    global _loop
    with _lock:
        if _loop is None or _loop.is_closed():
            loop = asyncio.new_event_loop()
            thread = threading.Thread(
                target=loop.run_forever, name="ble-bus", daemon=True
            )
            thread.start()
            _loop = loop
    return _loop


def submit(coro: Coroutine) -> concurrent.futures.Future:
    """코루틴을 공용 BLE 루프에 제출한다 (스레드 안전, 논블로킹)."""
    return asyncio.run_coroutine_threadsafe(coro, _ensure_loop())


# ── 스캔 결과 공유 ──────────────────────────────────────────────────────
# bleak(BlueZ)는 주소 문자열로 연결하면 먼저 자체 스캔을 돌리는데, 같은
# 프로세스에서 이미 그 어댑터로 스캔 중이면 BlueZ 가 InProgress 로 거절해
# 연결이 영원히 안 된다 (2026-08-29 실측, 킬 스위치 + 조끼 스캐너 동시 사용).
# 스캐너 콜백이 본 BLEDevice 를 여기 남겨 두면 연결 쪽은 스캔 없이 바로 쓴다.
_devices: dict[str, object] = {}


def note_device(device) -> None:
    """스캐너 콜백에서 호출: 발견한 BLEDevice 를 주소로 보관 (최신으로 갱신)."""
    _devices[device.address.upper()] = device


def get_device(address: str, adapter: str | None = None):
    """보관된 BLEDevice. adapter 가 주어지면 그 어댑터에서 본 것만 돌려준다."""
    device = _devices.get(address.upper())
    if device is None:
        return None
    if adapter:
        path = getattr(device, "details", {}).get("path", "")
        if not path.startswith(f"/org/bluez/{adapter}/"):
            return None
    return device
