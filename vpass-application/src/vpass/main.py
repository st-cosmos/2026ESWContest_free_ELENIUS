"""Smart V-PASS 실행 엔트리포인트.

  uv run vpass                # 서버 시작 + 브라우저 자동 열기
  uv run vpass --no-browser   # 서버만 시작
  uv run vpass --kiosk        # 라즈베리파이 키오스크(chromium 전체화면)
"""

from __future__ import annotations

import argparse
import subprocess
import threading
import time
import webbrowser

import uvicorn

from .config import IS_RASPBERRY_PI


def _open_ui(url: str, kiosk: bool) -> None:
    time.sleep(1.5)
    if kiosk:
        for browser in ("chromium-browser", "chromium"):
            try:
                subprocess.Popen(
                    [browser, "--kiosk", "--noerrdialogs",
                     "--disable-session-crashed-bubble",
                     # GNOME Keyring 미사용 → 'Choose password for new keyring' 방지
                     "--password-store=basic", url]
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
    args = parser.parse_args()

    kiosk = args.kiosk or IS_RASPBERRY_PI
    if not args.no_browser:
        threading.Thread(
            target=_open_ui, args=(f"http://localhost:{args.port}", kiosk), daemon=True
        ).start()

    print("=" * 62)
    print("  Smart V-PASS — 어선 안전 관리 시스템")
    print(f"  접속 주소: http://localhost:{args.port}")
    print(f"  플랫폼: {'Raspberry Pi' if IS_RASPBERRY_PI else 'Desktop (개발 모드)'}")
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
