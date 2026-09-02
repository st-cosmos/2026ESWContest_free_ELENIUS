"""데모 관제 서버 전송 계층.

HTTP(기존 Wi-Fi)와 LoRa UART(E220 투명 전송)를 같은 get/post 인터페이스로
감싼다. LoRa 프로토콜은 UTF-8 JSON 1줄 요청/응답이다.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
import urllib.error
import urllib.request
from typing import Protocol


class DemoTransport(Protocol):
    def post(self, path: str, payload: dict) -> None:
        ...

    def get(self, path: str) -> dict | None:
        ...

    def close(self) -> None:
        ...


class HttpDemoTransport:
    def __init__(self, base_url: str, timeout: float = 2.0):
        # 윈도우에서 'localhost' 는 ::1 을 먼저 시도하다 IPv4 로 폴백하며 요청마다
        # 약 2초가 새는 경우가 있다. 데모 서버는 IPv4(0.0.0.0)로 열리므로 바로 지정한다.
        self._base = base_url.rstrip("/").replace("//localhost:", "//127.0.0.1:")
        self._timeout = timeout

    def post(self, path: str, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self._base + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=self._timeout).close()
        except (urllib.error.URLError, OSError, ValueError):
            pass

    def get(self, path: str) -> dict | None:
        try:
            with urllib.request.urlopen(self._base + path, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
            return None

    def close(self) -> None:
        return


class LoraDemoTransport:
    """E220-900T22D 투명 UART용 요청/응답 전송.

    한 번에 하나의 요청만 보내고 같은 id를 가진 응답을 기다린다. LoRa 링크가
    끊기거나 응답이 없어도 None/무시로 끝내 V-PASS 본체 동작에 영향을 주지 않는다.
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 9600,
        timeout: float = 2.0,
        retries: int = 1,
    ):
        self._port = port
        self._baudrate = baudrate
        self._timeout = timeout
        self._retries = max(1, retries)
        self._lock = threading.Lock()
        self._serial = None

    def _ensure_open(self):
        if self._serial is not None and self._serial.is_open:
            return self._serial
        import serial

        self._serial = serial.Serial(
            self._port,
            self._baudrate,
            timeout=0.2,
            write_timeout=self._timeout,
        )
        return self._serial

    def _close_serial(self) -> None:
        ser = self._serial
        self._serial = None
        if ser is not None:
            try:
                ser.close()
            except OSError:
                pass

    def _request(self, message: dict) -> dict | None:
        req_id = uuid.uuid4().hex
        packet = {"v": 1, "id": req_id, **message}
        raw = (json.dumps(packet, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
            "utf-8"
        )

        with self._lock:
            for _ in range(self._retries):
                try:
                    ser = self._ensure_open()
                    ser.reset_input_buffer()
                    ser.write(raw)
                    ser.flush()
                    deadline = time.time() + self._timeout
                    while time.time() < deadline:
                        line = ser.readline()
                        if not line:
                            continue
                        try:
                            response = json.loads(line.decode("utf-8").strip())
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            continue
                        if response.get("id") == req_id:
                            return response
                except Exception:
                    self._close_serial()
            return None

    def post(self, path: str, payload: dict) -> None:
        self._request({"op": "post", "path": path, "payload": payload})

    def get(self, path: str) -> dict | None:
        response = self._request({"op": "get", "path": path})
        if not response or not response.get("ok"):
            return None
        data = response.get("data")
        return data if isinstance(data, dict) else None

    def close(self) -> None:
        with self._lock:
            self._close_serial()
