from __future__ import annotations

from fastapi import APIRouter

from acgn_assistant.core.config import get_settings

router = APIRouter(prefix="/system", tags=["system"])


BUILD_TAG = "acgn-2026-01-10"


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/info")
def info():
    s = get_settings()
    # 不返回密钥类配置
    return {
        "build_tag": BUILD_TAG,
        "app_name": s.app_name,
        "env": s.env,
        "database_url": "sqlite" if s.database_url.startswith("sqlite") else "other",
        "deepseek_configured": bool(s.deepseek_api_key),
        "deepseek_model": s.deepseek_model,
        "web_search_provider": (s.web_search_provider or "").strip(),
        "web_search_configured": bool((s.web_search_provider or "").strip() and (s.web_search_api_key or "").strip()),
    }
