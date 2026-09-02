"""LoRa UART로 들어오는 V-PASS 단말 메시지 처리.

E220-900T22D는 투명 시리얼 링크로 사용한다. 프로토콜은 UTF-8 JSON 1줄:

  요청: {"v":1,"id":"...","op":"get|post","path":"/api/...","payload":{...}}
  응답: {"v":1,"id":"...","ok":true,"data":{...}}
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse


class LoraBridge:
    def __init__(
        self,
        runtime,
        port: str,
        baudrate: int = 9600,
        timeout: float = 2.0,
    ):
        self._runtime = runtime
        self._port = port
        self._baudrate = baudrate
        self._timeout = timeout
        self._running = False
        self._thread: threading.Thread | None = None
        self._serial = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._close_serial()
        if self._thread:
            self._thread.join(timeout=2)

    def _open_serial(self):
        if self._serial is not None and self._serial.is_open:
            return self._serial
        import serial

        self._serial = serial.Serial(
            self._port,
            self._baudrate,
            timeout=0.2,
            write_timeout=self._timeout,
        )
        print(f"[lora] 수신 시작: {self._port} @ {self._baudrate}")
        return self._serial

    def _close_serial(self) -> None:
        ser = self._serial
        self._serial = None
        if ser is not None:
            try:
                ser.close()
            except OSError:
                pass

    def _loop(self) -> None:
        while self._running:
            try:
                ser = self._open_serial()
                line = ser.readline()
                if not line:
                    continue
                response = self._handle_line(line)
                if response is not None:
                    raw = (
                        json.dumps(response, ensure_ascii=False, separators=(",", ":"))
                        + "\n"
                    ).encode("utf-8")
                    ser.write(raw)
                    ser.flush()
            except Exception as e:
                print(f"[lora] 오류: {e}")
                self._close_serial()
                time.sleep(2.0)

    def _handle_line(self, line: bytes) -> dict | None:
        try:
            request = json.loads(line.decode("utf-8").strip())
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

        req_id = request.get("id")
        if not req_id:
            return None
        try:
            data = self._dispatch(request)
            return {"v": 1, "id": req_id, "ok": True, "data": data or {}}
        except Exception as e:
            return {"v": 1, "id": req_id, "ok": False, "error": str(e)}

    def _dispatch(self, request: dict) -> dict | None:
        op = request.get("op")
        path = str(request.get("path") or "")
        payload = request.get("payload") if isinstance(request.get("payload"), dict) else {}

        if op == "get":
            return self._handle_get(path)
        if op == "post":
            return self._handle_post(path, payload)
        raise ValueError("지원하지 않는 LoRa op 입니다.")

    def _handle_get(self, path: str) -> dict | None:
        if path == "/api/sim/terminal":
            return self._runtime.terminal_feed()

        prefix = "/api/weather/"
        if path.startswith(prefix):
            region = urllib.parse.unquote(path[len(prefix):])
            weather = self._runtime.weather.get(region)
            if weather is None:
                raise ValueError("관할 기상을 찾을 수 없습니다.")
            return weather

        raise ValueError(f"지원하지 않는 LoRa GET 경로입니다: {path}")

    def _handle_post(self, path: str, payload: dict) -> dict | None:
        if path == "/api/ingest/vessel":
            vessel = self._runtime.vessels.upsert_live(payload)
            return {"success": True, "vessel": vessel}

        if path == "/api/ingest/report":
            report = self._runtime.ingest_report(payload)
            return {"success": True, "report": report}

        if path == "/api/ingest/port":
            entry = self._runtime.ingest_port(
                str(payload.get("kind") or ""),
                str(payload.get("vessel_name") or ""),
                str(payload.get("vessel_id") or ""),
                payload.get("time"),
            )
            return {"success": True, "entry": entry}

        raise ValueError(f"지원하지 않는 LoRa POST 경로입니다: {path}")
