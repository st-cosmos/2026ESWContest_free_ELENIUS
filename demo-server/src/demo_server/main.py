"""Smart V-PASS 데모 관제 서버 실행 엔트리포인트.

  uv run demo-server                # 서버 시작 + 브라우저 자동 열기
  uv run demo-server --no-browser   # 서버만 시작
  uv run demo-server --reset        # 이전 신고·출입항·출항 상태를 지우고 시작
  uv run demo-server --reset-all    # 시뮬레이터 항로·펜스, 기상까지 전부 지우고 시작
"""

from __future__ import annotations

import argparse
import threading
import time
import webbrowser

import uvicorn

from . import config
from .reset import reset_data


def _open_ui(url: str) -> None:
    time.sleep(1.5)
    webbrowser.open(url)


def main() -> None:
    parser = argparse.ArgumentParser(description="Smart V-PASS 데모 관제 서버")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=config.DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true", help="브라우저를 열지 않음")
    parser.add_argument("--reset", action="store_true",
                        help="이전 신고·출입항 로그·선박 목록과 시뮬레이터 출항 상태를 "
                             "지우고 시작 (항로·펜스는 유지)")
    parser.add_argument("--reset-all", action="store_true",
                        help="시뮬레이터 항로·펜스와 관할 기상까지 모두 지우고 시작")
    parser.add_argument("--lora", action="store_true",
                        help="LoRa UART로 V-PASS 단말 메시지를 수신")
    parser.add_argument("--lora-port", default=None,
                        help="LoRa 모듈 UART 장치 경로 (예: /dev/ttyUSB0, /dev/serial0)")
    parser.add_argument("--lora-baudrate", type=int, default=None,
                        help="LoRa 모듈 UART baudrate")
    args = parser.parse_args()

    if args.lora:
        config.LORA_ENABLED = True
    if args.lora_port is not None:
        config.LORA_PORT = args.lora_port
    if args.lora_baudrate is not None:
        config.LORA_BAUDRATE = args.lora_baudrate

    # 서버(Runtime)가 파일을 읽기 전에 지워야 한다
    if args.reset or args.reset_all:
        scope = "전체 데이터" if args.reset_all else "운영 데이터"
        removed = reset_data(include_setup=args.reset_all)
        detail = ", ".join(removed) if removed else "지울 데이터가 없습니다"
        print(f"[reset] {scope} 초기화 — {detail}")

    if not args.no_browser:
        threading.Thread(
            target=_open_ui, args=(f"http://localhost:{args.port}",), daemon=True
        ).start()

    print("=" * 62)
    print("  Smart V-PASS — 데모 관제 서버")
    print(f"  접속 주소: http://localhost:{args.port}")
    print(f"  API 문서:  http://localhost:{args.port}/docs")
    print(f"  LoRa 수신: {'on ' + config.LORA_PORT if config.LORA_ENABLED else 'off'}")
    print("=" * 62)

    uvicorn.run(
        "demo_server.server:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
