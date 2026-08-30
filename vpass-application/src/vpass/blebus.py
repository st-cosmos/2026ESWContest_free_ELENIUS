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
import os
import re
import subprocess
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


# ── 어댑터 이름 해석 ────────────────────────────────────────────────────
# 리눅스의 hciN 번호는 부팅마다 USB 동글과 내장(UART) 칩 중 먼저 잡히는
# 쪽이 hci0 이 되어 뒤바뀔 수 있다 (2026-08-30 파이 실측: 동글 hci0, 내장
# hci1). 그래서 환경변수는 번호 대신 버스 종류("usb"/"uart")나 어댑터
# BD 주소로도 받고, 쓸 때마다 /sys 를 봐서 실제 hciN 으로 바꾼다.
_SYS_BT = "/sys/class/bluetooth"
_MAC_RE = re.compile(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$", re.I)


def _adapter_bus(name: str) -> str:
    """hciN 의 버스 종류 — /sys/class/bluetooth/hciN 실경로에 usb 가 있으면 usb."""
    try:
        real = os.path.realpath(os.path.join(_SYS_BT, name))
    except OSError:
        return "unknown"
    return "usb" if "/usb" in real else "uart"


def _adapter_addresses() -> dict[str, str]:
    """{hciN: BD 주소}. sysfs 에는 주소가 없어 `hciconfig` 출력을 읽는다 (bluez 패키지,
    /usr/sbin — 파이 non-login 셸 PATH 에 없을 수 있어 직접 보탠다)."""
    env = dict(os.environ)
    env["PATH"] = env.get("PATH", "") + os.pathsep + "/usr/sbin" + os.pathsep + "/sbin"
    try:
        out = subprocess.run(
            ["hciconfig"], capture_output=True, text=True, timeout=3, env=env
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    result: dict[str, str] = {}
    current = None
    for line in out.splitlines():
        m = re.match(r"^(hci\d+):", line)
        if m:
            current = m.group(1)
            continue
        m = re.search(r"BD Address:\s*(([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})", line)
        if m and current:
            result[current] = m.group(1).upper()
    return result


def list_adapters() -> list[tuple[str, str, str]]:
    """(hciN, BD 주소, 버스) 목록. /sys 가 없는 플랫폼(윈도우 등)은 빈 목록."""
    try:
        names = sorted(n for n in os.listdir(_SYS_BT) if n.startswith("hci"))
    except OSError:
        return []
    addrs = _adapter_addresses()
    return [(name, addrs.get(name, ""), _adapter_bus(name)) for name in names]


def resolve_adapter(spec: str | None) -> str | None:
    """어댑터 지정 문자열을 실제 hciN 이름으로 바꾼다.

    spec: "hci1" (그대로), "usb"/"uart" (버스 종류), "AA:BB:CC:DD:EE:FF" (BD 주소).
    매칭되는 어댑터가 없으면 spec 을 그대로 돌려준다 — 이후 bleak 오류 메시지로
    드러나고 호출 쪽 재시도 루프가 다시 이 함수를 부른다 (핫플러그 대응).
    """
    if not spec:
        return None
    spec = spec.strip()
    if re.fullmatch(r"hci\d+", spec):
        return spec
    adapters = list_adapters()
    if _MAC_RE.match(spec):
        for name, addr, _bus in adapters:
            if addr == spec.upper():
                return name
        return spec
    if spec.lower() in ("usb", "uart"):
        for name, _addr, bus in adapters:
            if bus == spec.lower():
                return name
        return spec
    return spec


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
