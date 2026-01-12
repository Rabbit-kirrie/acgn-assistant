from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Allow keeping secrets in .env.local (not committed) while .env can stay non-sensitive.
    # NOTE: tests set PYTEST_RUNNING=1 to avoid reading local .env/.env.local.
    model_config = SettingsConfigDict(
        env_file=None if os.environ.get("PYTEST_RUNNING") else (".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "dev"
    app_name: str = "ACGN咨询助手-API"
    database_url: str = "sqlite:///./app.db"

    jwt_secret: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 120

    crisis_help_text: str = (
        "本服务不提供盗版下载、破解、激活码或绕过付费的内容；如需我可以提供 ACGN 作品信息与正规购买渠道方向。"
    )

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    deepseek_deep_think_model: str = "deepseek-reasoner"

    # Web search (optional). Recommended provider: serper
    web_search_provider: str = ""  # e.g. "serper"
    web_search_api_key: str = ""  # provider API key
    web_search_timeout_seconds: float = 12.0

    admin_email: str = ""
    admin_password: str = ""
    admin_username: str = "admin"

    # SMTP / Email (for password reset codes)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "ACGN咨询助手 <no-reply@localhost>"
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    smtp_timeout_seconds: int = 15

    # Password reset
    password_reset_code_minutes: int = 10
    password_reset_resend_seconds: int = 60

    # Registration email verification
    register_code_minutes: int = 10
    register_resend_seconds: int = 60

    # Dev/Test convenience: return reset code in API response (never enable in prod)
    email_debug_return_code: bool = True


def _validate_settings(s: Settings) -> None:
    # Security: avoid shipping with the default secret outside dev.
    if (not s.jwt_secret) or (s.jwt_secret.strip() == "change-me-in-prod"):
        if str(s.env).lower() != "dev":
            raise RuntimeError("JWT_SECRET 未配置或仍为默认值；请在 .env 中设置随机强密码")

    # Email: if debug return code is disabled, SMTP must be configured.
    if not bool(s.email_debug_return_code):
        missing: list[str] = []
        if not str(s.smtp_host).strip():
            missing.append("SMTP_HOST")
        if not int(getattr(s, "smtp_port", 0) or 0):
            missing.append("SMTP_PORT")
        if not str(s.smtp_username).strip():
            missing.append("SMTP_USERNAME")
        if not str(s.smtp_password).strip():
            missing.append("SMTP_PASSWORD")
        if not str(s.smtp_from).strip():
            missing.append("SMTP_FROM")

        if missing:
            raise RuntimeError(
                "EMAIL_DEBUG_RETURN_CODE=false 时必须配置 SMTP：缺少 " + ", ".join(missing)
            )

        if bool(s.smtp_use_tls) and bool(s.smtp_use_ssl):
            raise RuntimeError("SMTP_USE_TLS 与 SMTP_USE_SSL 不能同时为 true")


def get_settings() -> Settings:
    # 注意：测试/不同环境如需切换 env，可在调用前设置环境变量。
    # 兼容：在部分 Windows/解释器组合下，pydantic-settings 的 env_file 读取可能不稳定。
    # 这里用 python-dotenv 读取 .env/.env.local，但只把“非空值”写入环境变量，
    # 避免 .env 中的空占位符（例如 SMTP_USERNAME=）污染环境导致校验失败。
    # 另外：pytest 下不注入 dotenv 文件，保证测试不受本机 .env.local 影响。
    try:
        if not os.environ.get("PYTEST_RUNNING"):
            from dotenv import dotenv_values

            def _inject_non_empty(path: str, *, allow_override_empty: bool) -> None:
                vals = dotenv_values(path)
                for k, v in (vals or {}).items():
                    if k is None:
                        continue
                    if v is None:
                        continue
                    vv = str(v)
                    if not vv.strip():
                        continue
                    cur = os.environ.get(k)
                    if cur is None:
                        os.environ[k] = vv
                    elif allow_override_empty and str(cur).strip() == "":
                        os.environ[k] = vv

            # .env: only fill missing keys
            _inject_non_empty(".env", allow_override_empty=False)
            # .env.local: fill missing keys and replace empty placeholders
            _inject_non_empty(".env.local", allow_override_empty=True)
    except Exception:
        pass

    settings = Settings()

    # Postgres driver selection:
    # We ship psycopg3 (`psycopg`), so normalize plain postgres URLs to
    # `postgresql+psycopg://...` to avoid SQLAlchemy defaulting to psycopg2.
    db_url = str(getattr(settings, "database_url", "") or "").strip()
    if db_url and ("+" not in db_url.split("://", 1)[0]):
        if db_url.startswith("postgresql://"):
            settings.database_url = "postgresql+psycopg://" + db_url[len("postgresql://") :]
        elif db_url.startswith("postgres://"):
            settings.database_url = "postgresql+psycopg://" + db_url[len("postgres://") :]

    # Vercel Functions 的文件系统除 /tmp 外通常不可写；默认 ./app.db 会失败。
    # 若用户未显式设置 DATABASE_URL，则在 Vercel 上将 SQLite 文件改到 /tmp。
    if (os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV")):
        db = str(getattr(settings, "database_url", "") or "")
        if db.strip() == "sqlite:///./app.db":
            settings.database_url = "sqlite:////tmp/app.db"

    _validate_settings(settings)
    return settings
