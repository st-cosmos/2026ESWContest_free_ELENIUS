"""BLE 구명조끼 수신기 — nRF52840 펌웨어의 광고 패킷을 스캔해 DeviceRegistry 로 연결.

구명조끼 장치(firmware/, E73-2G4M08S1C)는 연결 없이 non-connectable 광고의
Manufacturer Specific Data(회사 ID 0xFFFF)에 상태를 실어 브로드캐스트한다.
페이로드 9바이트 (firmware/src/jacket_adv.h 와 반드시 일치):

  [0] 'V'  [1] 'J'   매직
  [2] 버전 (1)
  [3] 장치 번호       → "jacket-<n>" 장치 ID 로 매핑 (ESP 버전과 동일 체계)
  [4] 플래그          b0 착용, b1 물 감지, b2 낙하 래치, b3 저전압, b4 스트로브
  [5] 시퀀스          1초마다 증가 (BlueZ 중복 필터 무력화 겸용)
  [6] 낙하 카운터     이벤트마다 증가 — 증가분을 보고 새 낙하를 식별
  [7] 낙하 크기       0.1 g 단위
  [8] 배터리          VDD [mV] / 20

HTTP → 레지스트리 매핑과 동일한 의미로 변환한다:
  착용 광고 수신      = ping (생존 신호). 신호 두절 판정은 기존
                        SIGNAL_LOSS_TIMEOUT 로직을 그대로 사용
  worn 플래그 전환    = set_wearing (승선 게이트/탈의 경고)
  낙하 카운터 증가    = fall (이후 두절 시 FALL_PING_TIMEOUT 로 익수 판정)

bleak 미설치·블루투스 어댑터 부재 시에는 상태만 남기고 조용히 비활성화된다
— 기존 HTTP 경로(/api/wearing 등)와 SimJacket 은 그대로 병행 동작한다.
"""

from __future__ import annotations

import asyncio
import threading
import time

from . import blebus
from .config import BLE_ADAPTER, BLE_COMPANY_ID, BLE_ENABLED, JACKET_BATT_WARN_MV

MAGIC = b"VJ"
PROTO_VERSION = 1

FLAG_WORN = 0x01
FLAG_WATER = 0x02
FLAG_FALL = 0x04
FLAG_LOW_BATT = 0x08
FLAG_STROBE = 0x10

# 같은 장치의 ping 을 레지스트리에 넣는 최소 간격(초) — 광고는 이보다 촘촘하다
PING_MIN_INTERVAL = 1.0


class BleJacketScanner:
    def __init__(self, registry, on_low_batt=None):
        self._registry = registry
        # (device_id, batt_mv) — 착용 중 배터리 교체요망 감지 시 1회 호출
        self._on_low_batt = on_low_batt
        self._future = None
        self._running = False
        # 장치별 마지막 상태 {id: {worn, fall_count, last_ping, batt_mv, ...}}
        self._seen: dict[str, dict] = {}
        self._lock = threading.Lock()
        self.status = "off" if not BLE_ENABLED else "starting"

    # ── 수명 주기 ────────────────────────────────────────────────────────
    # BLE 코루틴은 blebus 의 공용 루프에서 실행한다. 스캐너와 킬 스위치가
    # 각자 루프를 돌리면 bleak/BlueZ 전역 매니저가 첫 루프에 묶여 두 번째
    # 루프가 교착된다 (blebus.py 참고).
    def start(self) -> None:
        if not BLE_ENABLED or self._running:
            return
        self._running = True
        self._future = blebus.submit(self._run())

    def stop(self) -> None:
        # 루프를 세우지 않고 플래그만 내린다 — 스캔 루프(0.5초 폴링)가
        # 스스로 스캐너를 정리(await scanner.stop())하고 끝난다.
        self._running = False
        if self._future:
            try:
                self._future.result(timeout=5)
            except Exception:
                pass

    async def _run(self) -> None:
        try:
            from bleak import BleakScanner  # noqa: F401
        except ImportError:
            self.status = "unavailable (bleak 미설치 — uv sync 후 재시작)"
            print(f"[jacketble] {self.status}")
            return

        try:
            await self._scan_forever()
        except Exception as e:  # 어댑터 없음/권한 등
            self.status = f"error: {e}"
            print(f"[jacketble] 스캔 종료: {e}")

    async def _scan_forever(self) -> None:
        from bleak import BleakScanner

        kwargs = {"detection_callback": self._on_adv}
        if BLE_ADAPTER:
            kwargs["adapter"] = BLE_ADAPTER

        while self._running:
            try:
                scanner = BleakScanner(**kwargs)
                await scanner.start()
                try:
                    self.status = f"scanning ({BLE_ADAPTER or 'default'})"
                    print(f"[jacketble] BLE 스캔 시작 (adapter={BLE_ADAPTER or 'default'})")
                    while self._running:
                        await asyncio.sleep(0.5)
                finally:
                    await scanner.stop()
                return
            except Exception as e:
                # 어댑터가 아직 없거나 일시 오류 — 10초 후 재시도
                self.status = f"retrying: {e}"
                print(f"[jacketble] 스캔 실패, 10초 후 재시도: {e}")
                for _ in range(20):
                    if not self._running:
                        return
                    await asyncio.sleep(0.5)

    # ── 광고 수신 ────────────────────────────────────────────────────────
    def _on_adv(self, device, adv) -> None:
        payload = adv.manufacturer_data.get(BLE_COMPANY_ID)
        if not payload or len(payload) < 9 or payload[:2] != MAGIC:
            return
        if payload[2] != PROTO_VERSION:
            return

        device_id = f"jacket-{payload[3]}"
        flags = payload[4]
        fall_count = payload[6]
        fall_mag = payload[7] / 10.0
        batt_mv = payload[8] * 20
        worn = bool(flags & FLAG_WORN)
        low_batt = bool(flags & FLAG_LOW_BATT) or (
            0 < batt_mv < JACKET_BATT_WARN_MV
        )
        now = time.time()

        with self._lock:
            prev = self._seen.get(device_id)
            first = prev is None
            if first:
                prev = {
                    "worn": None,
                    "fall_count": fall_count,
                    "last_ping": 0.0,
                    "batt_warned": False,
                }
                self._seen[device_id] = prev

            worn_changed = prev["worn"] != worn
            # 낙하 카운터 증가분 (uint8 랩어라운드 포함)
            new_falls = (fall_count - prev["fall_count"]) % 256 if not first else 0
            do_ping = worn and now - prev["last_ping"] >= PING_MIN_INTERVAL
            prev["worn"] = worn
            prev["fall_count"] = fall_count
            if do_ping:
                prev["last_ping"] = now
            # 착용 상태에서 교체요망이면 착용 세션당 1회 경고 (탈의 시 리셋)
            if not worn:
                prev["batt_warned"] = False
            warn_batt = worn and low_batt and not prev["batt_warned"]
            if warn_batt:
                prev["batt_warned"] = True
            prev.update(
                batt_mv=batt_mv,
                water=bool(flags & FLAG_WATER),
                strobe=bool(flags & FLAG_STROBE),
                low_batt=low_batt,
                rssi=adv.rssi,
                last_seen=now,
                address=device.address,
            )

        # 레지스트리 반영은 락 밖에서 (콜백 체인이 길 수 있음)
        if worn_changed:
            self._registry.set_wearing(device_id, worn)
        if new_falls:
            self._registry.fall(device_id, fall_mag if fall_mag > 0 else 3.0)
            self._registry.ping(device_id)  # 낙하 직후 광고 = 아직 생존
        elif do_ping:
            self._registry.ping(device_id)
        if warn_batt and self._on_low_batt:
            try:
                self._on_low_batt(device_id, batt_mv)
            except Exception as e:
                print(f"[jacketble] on_low_batt 콜백 오류: {e}")

    def sim_battery(self, device_id: str, mv: int) -> None:
        """시뮬레이터용: BLE 수신 없이 배터리 값을 주입 (UI 표시/경고 시연)."""
        with self._lock:
            d = self._seen.setdefault(
                device_id,
                {"worn": None, "fall_count": 0, "last_ping": 0.0,
                 "batt_warned": False},
            )
            d["batt_mv"] = mv
            d["low_batt"] = 0 < mv < JACKET_BATT_WARN_MV

    # ── 조회 ────────────────────────────────────────────────────────────
    def battery_info(self, device_id: str) -> dict | None:
        """장치의 배터리 상태 {mv, low} — BLE 수신 이력이 없으면 None."""
        with self._lock:
            d = self._seen.get(device_id)
            if not d or d.get("batt_mv") is None:
                return None
            return {"mv": d["batt_mv"], "low": bool(d.get("low_batt"))}

    def snapshot(self) -> dict:
        with self._lock:
            devices = {
                dev: {
                    "battery_mv": d.get("batt_mv"),
                    "water": d.get("water"),
                    "strobe": d.get("strobe"),
                    "low_batt": d.get("low_batt"),
                    "rssi": d.get("rssi"),
                    "seconds_ago": (
                        round(time.time() - d["last_seen"], 1)
                        if d.get("last_seen")
                        else None
                    ),
                }
                for dev, d in self._seen.items()
            }
        return {"status": self.status, "devices": devices}
