"""Smart V-PASS 데모 관제 서버 실행 엔트리포인트.

  uv run demo-server                # 서버 시작 + 브라우저 자동 열기
  uv run demo-server --no-browser   # 서버만 시작
"""

from __future__ import annotations

import argparse
import threading
import time
import webbrowser

import uvicorn

from .config import DEFAULT_PORT


def _open_ui(url: str) -> None:
    time.sleep(1.5)
    webbrowser.open(url)


def main() -> None:
    parser = argparse.ArgumentParser(description="Smart V-PASS 데모 관제 서버")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true", help="브라우저를 열지 않음")
    args = parser.parse_args()

    if not args.no_browser:
        threading.Thread(
            target=_open_ui, args=(f"http://localhost:{args.port}",), daemon=True
        ).start()

    print("=" * 62)
    print("  Smart V-PASS — 데모 관제 서버")
    print(f"  접속 주소: http://localhost:{args.port}")
    print(f"  API 문서:  http://localhost:{args.port}/docs")
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
