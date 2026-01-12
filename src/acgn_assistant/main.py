from __future__ import annotations

from contextlib import asynccontextmanager
import mimetypes
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from sqlmodel import Session
from acgn_assistant.core.config import get_settings
from acgn_assistant.db import get_engine, init_db
from acgn_assistant.controllers.ui import router as ui_router
from acgn_assistant.routers import (
    admin_audit,
    admin_conversations,
    admin_users,
    auth,
    conversations,
    guestbook,
    memory,
    profile,
    recommendations,
    reports,
    resources,
    system,
    users,
)
from acgn_assistant.services.bootstrap import ensure_admin_user


def create_app() -> FastAPI:
    settings = get_settings()
    
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        init_db()
        # 可选：初始化管理员（由 env ADMIN_* 控制）
        with Session(get_engine()) as session:
            ensure_admin_user(session)
        yield

    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    # Static assets (UI images, etc.)
    # Ensure Windows cursor/icon files are served with an icon MIME type.
    # Some browsers may ignore custom cursor URLs if served as application/octet-stream.
    mimetypes.add_type("image/x-icon", ".cur")
    mimetypes.add_type("image/x-icon", ".ico")
    static_dir = Path(__file__).resolve().parent / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Browsers often request /favicon.ico by default.
    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> RedirectResponse:
        png_path = static_dir / "favicon.png"
        if png_path.exists():
            return RedirectResponse(url="/static/favicon.png")
        jpg_path = static_dir / "favicon.jpg"
        if jpg_path.exists():
            return RedirectResponse(url="/static/favicon.jpg")
        return RedirectResponse(url="/static/favicon.svg")

    # 开发环境：允许本机前端（如 VS Code Live Server :5500）跨域访问 API
    if settings.env == "dev":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[
                # file:// 打开页面时浏览器会发送 Origin: null
                "null",
                "http://127.0.0.1:5500",
                "http://localhost:5500",
                "http://127.0.0.1:8000",
                "http://localhost:8000",
            ],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(conversations.router)
    app.include_router(ui_router)

    # 系统与管理端 API
    app.include_router(system.router)
    app.include_router(admin_audit.router)
    app.include_router(admin_users.router)
    app.include_router(admin_conversations.router)
    app.include_router(profile.router)
    app.include_router(resources.router)
    app.include_router(recommendations.router)
    app.include_router(reports.router)
    app.include_router(memory.router)
    app.include_router(guestbook.router)

    return app


app = create_app()
