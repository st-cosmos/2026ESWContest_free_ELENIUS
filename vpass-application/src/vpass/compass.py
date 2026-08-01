"""QMC5883L 지자계(나침반) 읽기.

상위 ``test-gps`` 프로젝트의 QMC5883L 읽기/저역통과 필터만 가져왔다.
요청대로 회전 보정 기록/저장(calibration) 흐름은 포함하지 않는다. 필요한 고정
offset/scale 값은 환경변수로 주입해 런타임에서 생성한다.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class CompassHeading:
    heading_deg: Optional[float] = None
    updated_at: Optional[str] = None
    connected: bool = False
    error: Optional[str] = None

    @property
    def valid(self) -> bool:
        return self.heading_deg is not None


class Qmc5883lReader:
    """I2C QMC5883L에서 침로를 지속적으로 읽는다."""

    ADDRESS = 0x0D

    def __init__(
        self,
        bus_number: int,
        declination_deg: float = 0.0,
        x_offset: float = 0.0,
        y_offset: float = 0.0,
        x_scale: float = 1.0,
        y_scale: float = 1.0,
        heading_alpha: float = 0.25,
        stale_after_sec: float = 5.0,
    ) -> None:
        if not 0 < heading_alpha <= 1:
            raise ValueError("heading_alpha must be greater than 0 and no greater than 1")

        self.bus_number = bus_number
        self.declination_deg = declination_deg
        self.x_offset = x_offset
        self.y_offset = y_offset
        self.x_scale = x_scale
        self.y_scale = y_scale
        self.heading_alpha = heading_alpha
        self.stale_after_sec = stale_after_sec

        self._heading = CompassHeading()
        self._last_heading_ts: float | None = None
        self._filtered_sin: Optional[float] = None
        self._filtered_cos: Optional[float] = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def snapshot(self) -> dict:
        with self._lock:
            data = asdict(self._heading)
            last_heading_ts = self._last_heading_ts
        fresh = (
            last_heading_ts is not None
            and time.monotonic() - last_heading_ts <= self.stale_after_sec
        )
        data["valid"] = bool(data["heading_deg"] is not None)
        data["fresh"] = bool(data["valid"] and fresh)
        return data

    @staticmethod
    def _signed_16(low: int, high: int) -> int:
        value = low | (high << 8)  # QMC5883L 값은 little-endian.
        return value - 65536 if value >= 32768 else value

    def _low_pass_heading(self, heading: float) -> float:
        """원형 지수 저역통과 필터. alpha=1이면 필터링 없음."""
        angle = math.radians(heading)
        new_sin, new_cos = math.sin(angle), math.cos(angle)
        if self._filtered_sin is None or self._filtered_cos is None:
            self._filtered_sin, self._filtered_cos = new_sin, new_cos
        else:
            alpha = self.heading_alpha
            self._filtered_sin = alpha * new_sin + (1 - alpha) * self._filtered_sin
            self._filtered_cos = alpha * new_cos + (1 - alpha) * self._filtered_cos
        return math.degrees(math.atan2(self._filtered_sin, self._filtered_cos)) % 360

    def _publish_heading(self, heading: float) -> None:
        filtered_heading = self._low_pass_heading(heading)
        with self._lock:
            self._heading.heading_deg = filtered_heading
            self._heading.updated_at = time.strftime("%Y-%m-%d %H:%M:%S")
            self._heading.connected = True
            self._heading.error = None
            self._last_heading_ts = time.monotonic()

    def _run(self) -> None:
        try:
            from smbus2 import SMBus  # type: ignore
        except ImportError as error:
            with self._lock:
                self._heading.connected = False
                self._heading.error = f"smbus2 미설치: {error}"
            return

        while not self._stop.is_set():
            try:
                with SMBus(self.bus_number) as bus:
                    # Continuous mode, 200 Hz, ±8 G range, 512 oversampling.
                    bus.write_byte_data(self.ADDRESS, 0x09, 0x1D)
                    with self._lock:
                        self._heading.connected = True
                        self._heading.error = None
                    print(
                        f"[compass] QMC5883L connected: I2C bus {self.bus_number}, "
                        f"address 0x{self.ADDRESS:02X}"
                    )
                    while not self._stop.is_set():
                        values = bus.read_i2c_block_data(self.ADDRESS, 0x00, 6)
                        raw_x = self._signed_16(values[0], values[1])
                        raw_y = self._signed_16(values[2], values[3])
                        x = (raw_x - self.x_offset) * self.x_scale
                        y = (raw_y - self.y_offset) * self.y_scale
                        if x or y:
                            heading = (
                                math.degrees(math.atan2(y, x)) + self.declination_deg
                            ) % 360
                            self._publish_heading(heading)
                        time.sleep(0.1)
            except OSError as error:
                with self._lock:
                    self._heading.connected = False
                    self._heading.error = str(error)
                print(f"[compass] QMC5883L error: {error}; retrying in 3 seconds")
                self._stop.wait(3)
