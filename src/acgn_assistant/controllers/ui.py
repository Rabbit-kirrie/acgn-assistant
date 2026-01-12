from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi import Response
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["ui"])


@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    # Avoid noisy 404s in browser devtools. This UI does not ship a favicon.
    return Response(status_code=204)


@router.get("/", response_class=HTMLResponse)
def index():
    # Root should show the login UI. Main app is served at /app.
    html_path = Path(__file__).resolve().parents[1] / "views" / "login.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@router.get("/app", response_class=HTMLResponse)
@router.get("/app/", response_class=HTMLResponse, include_in_schema=False)
def app_page():
    html_path = Path(__file__).resolve().parents[1] / "views" / "landing.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@router.get("/console", response_class=HTMLResponse)
@router.get("/console/", response_class=HTMLResponse, include_in_schema=False)
def console():
    # /console 历史兼容：此仓库目前仅保留 landing.html
    html_path = Path(__file__).resolve().parents[1] / "views" / "landing.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@router.get("/login", response_class=HTMLResponse)
@router.get("/login/", response_class=HTMLResponse, include_in_schema=False)
def login_page():
    html_path = Path(__file__).resolve().parents[1] / "views" / "login.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@router.get("/register", response_class=HTMLResponse)
@router.get("/register/", response_class=HTMLResponse, include_in_schema=False)
def register_page():
    html_path = Path(__file__).resolve().parents[1] / "views" / "register.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@router.get("/forgot", response_class=HTMLResponse)
@router.get("/forgot/", response_class=HTMLResponse, include_in_schema=False)
def forgot_page():
    html_path = Path(__file__).resolve().parents[1] / "views" / "forgot.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@router.get("/terms", response_class=HTMLResponse)
@router.get("/terms/", response_class=HTMLResponse, include_in_schema=False)
def terms_page():
    html_path = Path(__file__).resolve().parents[1] / "views" / "terms.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@router.get("/privacy", response_class=HTMLResponse)
@router.get("/privacy/", response_class=HTMLResponse, include_in_schema=False)
def privacy_page():
    html_path = Path(__file__).resolve().parents[1] / "views" / "privacy.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))
