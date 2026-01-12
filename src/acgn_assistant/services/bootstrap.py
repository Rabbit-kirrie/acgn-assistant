from __future__ import annotations

from sqlmodel import Session, select

from acgn_assistant.core.config import get_settings
from acgn_assistant.core.security import hash_password
from acgn_assistant.models.user import User


def ensure_admin_user(session: Session) -> None:
    """初始化系统管理员。

    通过环境变量提供：ADMIN_EMAIL / ADMIN_PASSWORD / ADMIN_USERNAME
    若未配置则跳过。
    """

    s = get_settings()
    email = getattr(s, "admin_email", "")
    password = getattr(s, "admin_password", "")
    username = getattr(s, "admin_username", "admin")

    if not email or not password:
        return

    exists = session.exec(select(User).where(User.email == email)).first()
    if exists:
        # 若已存在，确保其管理员标记为 True
        changed = False
        if not getattr(exists, "is_admin", False):
            exists.is_admin = True
            changed = True
        if not getattr(exists, "is_active", True):
            exists.is_active = True
            changed = True
        if changed:
            session.add(exists)
            session.commit()
        return

    admin = User(
        email=email,
        username=username,
        hashed_password=hash_password(password),
        is_admin=True,
    )
    session.add(admin)
    session.commit()
