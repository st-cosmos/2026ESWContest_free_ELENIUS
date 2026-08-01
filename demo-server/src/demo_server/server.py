"""FastAPI 앱 팩토리 + 정적 파일(React 빌드) 서빙."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import UI_DIST_DIR, ensure_dirs
from .routes import router
from .runtime import Runtime


def create_app() -> FastAPI:
    ensure_dirs()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime = Runtime()
        app.state.runtime = runtime
        runtime.start()
        try:
            yield
        finally:
            runtime.stop()

    app = FastAPI(title="Smart V-PASS Demo 관제 서버", lifespan=lifespan)
    app.include_router(router)

    # React 빌드 산출물 (ui/dist)
    if UI_DIST_DIR.exists():
        app.mount(
            "/assets",
            StaticFiles(directory=str(UI_DIST_DIR / "assets")),
            name="assets",
        )

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            candidate = UI_DIST_DIR / path
            if path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(UI_DIST_DIR / "index.html")

    else:

        @app.get("/", include_in_schema=False)
        def no_ui():
            return JSONResponse(
                {
                    "message": "UI 빌드가 없습니다. demo-server/ui 에서 "
                    "`npm install && npm run build` 를 실행해 주세요.",
                    "api_docs": "/docs",
                }
            )

    return app
