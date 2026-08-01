"""NEO-6M 등 NMEA GPS 수신기 읽기.

상위 ``test-gps`` 프로젝트에서 검증한 NMEA 파싱 로직을 앱용 모듈로 분리했다.
지도/Flask 데모 코드는 제외하고, 백그라운드 스레드에서 최신 fix 상태만 유지한다.
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class GpsFix:
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude_m: Optional[float] = None
    satellites: Optional[int] = None
    speed_kn: float = 0.0
    course_deg: Optional[float] = None
    updated_at: Optional[str] = None
    connected: bool = False
    error: Optional[str] = None

    @property
    def valid(self) -> bool:
        return self.latitude is not None and self.longitude is not None


class NmeaGpsReader:
    """UART로 들어오는 NMEA 문장을 읽어 최신 위치/속도 상태를 만든다."""

    def __init__(self, port: str, baudrate: int, stale_after_sec: float = 10.0) -> None:
        self.port = port
        self.baudrate = baudrate
        self.stale_after_sec = stale_after_sec
        self._fix = GpsFix()
        self._last_fix_ts: float | None = None
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
            data = asdict(self._fix)
            last_fix_ts = self._last_fix_ts
        fresh = (
            last_fix_ts is not None
            and time.monotonic() - last_fix_ts <= self.stale_after_sec
        )
        data["valid"] = bool(data["latitude"] is not None and data["longitude"] is not None)
        data["fresh"] = bool(data["valid"] and fresh)
        return data

    @staticmethod
    def _coordinate(value: str, hemisphere: str) -> float:
        """NMEA ddmm.mmmm / dddmm.mmmm 좌표를 십진수 도 단위로 변환한다."""
        if not value or not hemisphere:
            raise ValueError("empty coordinate")
        degrees_length = 2 if hemisphere in ("N", "S") else 3
        degrees = float(value[:degrees_length])
        minutes = float(value[degrees_length:])
        coordinate = degrees + minutes / 60
        return -coordinate if hemisphere in ("S", "W") else coordinate

    @staticmethod
    def _checksum_ok(sentence: str) -> tuple[bool, str]:
        if not sentence.startswith("$"):
            return False, ""
        body, separator, checksum = sentence[1:].partition("*")
        if not separator:
            return True, body
        try:
            calculated = 0
            for character in body:
                calculated ^= ord(character)
            return calculated == int(checksum[:2], 16), body
        except ValueError:
            return False, body

    def update_from_nmea(self, sentence: str) -> None:
        """테스트와 재사용이 쉽도록 단일 NMEA 문장 처리를 공개 메서드로 둔다."""
        ok, body = self._checksum_ok(sentence.strip())
        if not ok:
            return

        fields = body.split(",")
        message_type = fields[0][-3:]
        latitude = longitude = None
        altitude = satellites = course = None
        speed_kn: float | None = None

        try:
            if message_type == "RMC" and len(fields) >= 9 and fields[2] == "A":
                latitude = self._coordinate(fields[3], fields[4])
                longitude = self._coordinate(fields[5], fields[6])
                speed_kn = float(fields[7]) if fields[7] else 0.0
                course = float(fields[8]) if fields[8] else None
            elif message_type == "GGA" and len(fields) >= 10 and fields[6] != "0":
                latitude = self._coordinate(fields[2], fields[3])
                longitude = self._coordinate(fields[4], fields[5])
                satellites = int(fields[7]) if fields[7] else None
                altitude = float(fields[9]) if fields[9] else None
            else:
                return
        except (ValueError, IndexError):
            return

        with self._lock:
            self._fix.latitude = latitude
            self._fix.longitude = longitude
            self._fix.updated_at = time.strftime("%Y-%m-%d %H:%M:%S")
            self._fix.connected = True
            self._fix.error = None
            if altitude is not None:
                self._fix.altitude_m = altitude
            if satellites is not None:
                self._fix.satellites = satellites
            if speed_kn is not None:
                self._fix.speed_kn = speed_kn
            if course is not None:
                self._fix.course_deg = course
            self._last_fix_ts = time.monotonic()

    def _run(self) -> None:
        try:
            import serial  # type: ignore
        except ImportError as error:
            with self._lock:
                self._fix.connected = False
                self._fix.error = f"pyserial 미설치: {error}"
            return

        while not self._stop.is_set():
            try:
                with serial.Serial(self.port, self.baudrate, timeout=1) as connection:
                    with self._lock:
                        self._fix.connected = True
                        self._fix.error = None
                    print(f"[gps] connected: {self.port} ({self.baudrate} bps)")
                    while not self._stop.is_set():
                        sentence = (
                            connection.readline()
                            .decode("ascii", errors="ignore")
                            .strip()
                        )
                        if sentence:
                            self.update_from_nmea(sentence)
            except Exception as error:
                with self._lock:
                    self._fix.connected = False
                    self._fix.error = str(error)
                print(f"[gps] connection error: {error}; retrying in 3 seconds")
                self._stop.wait(3)
