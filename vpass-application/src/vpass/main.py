"""Smart V-PASS 실행 엔트리포인트.

  uv run vpass                # 서버 시작 + 브라우저 자동 열기
  uv run vpass --no-browser   # 서버만 시작
  uv run vpass --kiosk        # 라즈베리파이 키오스크(chromium 전체화면)
  uv run vpass --reset        # 이전 운항·승선 기록을 지우고 시작
  uv run vpass --reset-all    # 등록 선원·어선 정보까지 전부 지우고 시작
"""

from __future__ import annotations

import argparse
import subprocess
import threading
import time
import webbrowser

import uvicorn

from . import config
from .reset import reset_data


def _open_ui(url: str, kiosk: bool) -> None:
    time.sleep(1.5)
    if kiosk:
        for browser in ("chromium-browser", "chromium"):
            try:
                subprocess.Popen(
                    [browser, "--kiosk", "--noerrdialogs",
                     "--disable-session-crashed-bubble",
                     # GNOME Keyring 미사용 → 'Choose password for new keyring' 방지
                     "--password-store=basic",
                     # 사운드 효과: 사용자 입력 없이도 오디오 자동재생 허용
                     "--autoplay-policy=no-user-gesture-required",
                     # XWayland 로 띄워야 fcitx 한글 입력이 된다. Wayland 네이티브로
                     # 뜨면 chromium 은 text-input 프로토콜만 쓰는데 fcitx4 는 그걸
                     # 제공하지 않아 GTK_IM_MODULE 설정과 무관하게 영문만 입력된다.
                     "--ozone-platform=x11", url]
                )
                return
            except FileNotFoundError:
                continue
    webbrowser.open(url)


def main() -> None:
    parser = argparse.ArgumentParser(description="Smart V-PASS 어선 안전 관리 시스템")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="브라우저를 열지 않음")
    parser.add_argument("--kiosk", action="store_true",
                        help="chromium 키오스크 모드로 UI 열기 (라즈베리파이)")
    parser.add_argument("--reset", action="store_true",
                        help="이전 운항·승선 기록을 지우고 시작 "
                             "(재시작 후에도 '운항 중'으로 남는 상태 초기화)")
    parser.add_argument("--reset-all", action="store_true",
                        help="등록 선원·얼굴 사진·어선 정보까지 모두 지우고 시작")
    parser.add_argument(
        "--demo-transport",
        choices=("auto", "http", "lora", "off"),
        default=None,
        help="데모 관제 서버 통신 방식 선택(auto/http/lora/off)",
    )
    parser.add_argument("--demo-server-url", default=None,
                        help="HTTP 데모 관제 서버 URL (예: http://localhost:8100)")
    parser.add_argument("--lora-port", default=None,
                        help="LoRa 모듈 UART 장치 경로 (예: /dev/ttyUSB0, /dev/serial0)")
    parser.add_argument("--lora-baudrate", type=int, default=None,
                        help="LoRa 모듈 UART baudrate")
    args = parser.parse_args()

    if args.demo_transport is not None:
        config.DEMO_TRANSPORT = args.demo_transport
    if args.demo_server_url is not None:
        config.DEMO_SERVER_URL = args.demo_server_url.strip() or None
    if args.lora_port is not None:
        config.LORA_PORT = args.lora_port
    if args.lora_baudrate is not None:
        config.LORA_BAUDRATE = args.lora_baudrate

    # 서버(Runtime)가 파일을 읽기 전에 지워야 한다
    if args.reset or args.reset_all:
        scope = "전체 데이터" if args.reset_all else "운항·승선 기록"
        removed = reset_data(include_registry=args.reset_all)
        detail = ", ".join(removed) if removed else "지울 데이터가 없습니다"
        print(f"[reset] {scope} 초기화 — {detail}")

    kiosk = args.kiosk or config.IS_RASPBERRY_PI
    if not args.no_browser:
        threading.Thread(
            target=_open_ui, args=(f"http://localhost:{args.port}", kiosk), daemon=True
        ).start()

    print("=" * 62)
    print("  Smart V-PASS — 어선 안전 관리 시스템")
    print(f"  접속 주소: http://localhost:{args.port}")
    print(f"  플랫폼: {'Raspberry Pi' if config.IS_RASPBERRY_PI else 'Desktop (개발 모드)'}")
    print(f"  데모 통신: {config.DEMO_TRANSPORT}")
    print("=" * 62)

    uvicorn.run(
        "vpass.server:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
