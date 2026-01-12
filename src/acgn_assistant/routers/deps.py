from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlmodel import Session, select

from acgn_assistant.core.config import get_settings
from acgn_assistant.db import get_session
from acgn_assistant.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def _is_super_admin(user: User) -> bool:
    """Return True if this user is the bootstrap super admin.

    Definition:
    - If ADMIN_EMAIL is configured: the (active) user whose email matches ADMIN_EMAIL and is_admin=True.
    - If ADMIN_EMAIL is not configured: treat any admin user as super admin to avoid lockouts.
    """

    if not getattr(user, "is_admin", False):
        return False

    settings = get_settings()
    admin_email = (getattr(settings, "admin_email", "") or "").strip().lower()
    if not admin_email:
        return True

    return (user.email or "").strip().lower() == admin_email


def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> User:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效令牌") from e

    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效令牌")

    user = session.exec(select(User).where(User.id == user_id)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    if not getattr(user, "is_active", True):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号已禁用")
    return user


def get_current_admin_user(user: User = Depends(get_current_user)) -> User:
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


def get_current_super_admin_user(user: User = Depends(get_current_user)) -> User:
    if not _is_super_admin(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要最高管理员权限")
    return user
