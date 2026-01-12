from __future__ import annotations

import hashlib
import math
import secrets
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from acgn_assistant.core.config import get_settings
from acgn_assistant.core.security import create_access_token, hash_password, verify_password
from acgn_assistant.core.time import utcnow
from acgn_assistant.db import get_session
from acgn_assistant.models.password_reset import PasswordResetCode
from acgn_assistant.models.user import User, UserCreate
from acgn_assistant.models.user_profile import UserProfile
from acgn_assistant.models.registration_code import RegistrationCode
from acgn_assistant.services.emailer import send_email

router = APIRouter(prefix="/auth", tags=["auth"])


def _is_qq_email(email: str) -> bool:
    try:
        return str(email or "").strip().lower().endswith("@qq.com")
    except Exception:
        return False


def _make_reset_code() -> str:
    # 6-digit numeric
    return f"{secrets.randbelow(1_000_000):06d}"


def _hash_reset_code(*, salt: str, code: str) -> str:
    raw = f"{salt}:{code}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=3)


class PasswordResetConfirm(BaseModel):
    email: str = Field(min_length=3)
    code: str = Field(min_length=4, max_length=32)
    new_password: str = Field(min_length=6, max_length=128)


class RegisterCodeRequest(BaseModel):
    email: str = Field(min_length=3)


class RegisterConfirm(BaseModel):
    email: str = Field(min_length=3)
    code: str = Field(min_length=4, max_length=32)
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6, max_length=128)


def _naive_utcnow():
    # SQLite stores naive datetimes; keep comparisons consistent.
    return utcnow().replace(tzinfo=None)


def _register_confirm_impl(*, payload: RegisterConfirm, session: Session) -> dict:
    email = (payload.email or "").strip().lower()
    if not _is_qq_email(email):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="仅支持 QQ 邮箱注册（@qq.com）")

    # Verify code
    now = _naive_utcnow()
    record = session.exec(
        select(RegistrationCode)
        .where(RegistrationCode.email == email)
        .where(RegistrationCode.used_at.is_(None))
        .order_by(RegistrationCode.created_at.desc())
    ).first()

    if not record:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先获取验证码")
    if record.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码已过期")

    expected = record.code_hash
    got = _hash_reset_code(salt=record.code_salt, code=(payload.code or "").strip())
    if got != expected:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码错误")

    exists = session.exec(select(User).where(User.email == email)).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱已注册")

    username = (payload.username or "").strip() or email.split("@")[0]
    user = User(email=email, username=username, hashed_password=hash_password(payload.password))
    prof = UserProfile(user_id=user.id, display_name=username)

    record.used_at = now
    session.add(user)
    session.add(prof)
    session.add(record)
    session.commit()
    session.refresh(user)

    token = create_access_token(subject=user.id)
    return {"access_token": token, "token_type": "bearer"}


@router.post("/register")
def register(payload: RegisterConfirm, session: Session = Depends(get_session)):
    # Backward-compatible alias: registration requires email verification.
    return _register_confirm_impl(payload=payload, session=session)


@router.post("/guest")
def guest(session: Session = Depends(get_session)):
    """Create a short-lived guest user and return a JWT.

    This avoids requiring QQ email for guest mode.
    """

    rid = uuid4().hex[:10]
    email = f"guest_{rid}@guest.local"
    username = f"guest_{rid}"
    password = uuid4().hex

    user = User(email=email, username=username, hashed_password=hash_password(password), is_admin=False)
    prof = UserProfile(user_id=user.id, display_name=username)
    session.add(user)
    session.add(prof)
    session.commit()
    session.refresh(user)

    token = create_access_token(subject=user.id, extra_claims={"is_guest": True})
    return {
        "access_token": token,
        "token_type": "bearer",
        "email": email,
        "username": username,
        "is_guest": True,
    }


@router.post("/login")
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
):
    # OAuth2PasswordRequestForm 的 username 字段这里用 email
    user = session.exec(select(User).where(User.email == form.username)).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")

    if not getattr(user, "is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已禁用")

    # For normal users, only allow QQ email login.
    # Admin users may use any email configured in ENV.
    if not getattr(user, "is_admin", False) and not _is_qq_email(user.email):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="仅支持 QQ 邮箱登录（@qq.com）")

    token = create_access_token(subject=user.id)
    return {"access_token": token, "token_type": "bearer"}


@router.post("/password-reset/request")
def password_reset_request(
    payload: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """Send a verification code to email to reset password.

    For privacy, this endpoint returns 200 even if the email is not registered.
    """

    settings = get_settings()

    # If SMTP is missing, allow dev/test only when debug_code is enabled.
    if not (settings.smtp_host or "").strip():
        if settings.env == "prod" or not settings.email_debug_return_code:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="SMTP 未配置")

    email = (payload.email or "").strip().lower()
    if not _is_qq_email(email):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="仅支持 QQ 邮箱（@qq.com）")

    user = session.exec(select(User).where(User.email == email)).first()
    if not user:
        return {"detail": "如果该邮箱已注册，验证码将发送到邮箱（有效期 10 分钟）"}

    now = _naive_utcnow()
    latest = session.exec(
        select(PasswordResetCode)
        .where(PasswordResetCode.email == email)
        .where(PasswordResetCode.used_at.is_(None))
        .order_by(PasswordResetCode.created_at.desc())
    ).first()

    if latest and latest.expires_at > now:
        delta = (now - latest.created_at).total_seconds()
        if delta < int(settings.password_reset_resend_seconds):
            wait_s = max(0, int(math.ceil(settings.password_reset_resend_seconds - delta)))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"请求过于频繁，请在 {wait_s}s 后再试",
                headers={"Retry-After": str(wait_s)},
            )

    code = _make_reset_code()
    salt = uuid4().hex
    code_hash = _hash_reset_code(salt=salt, code=code)

    record = PasswordResetCode(
        email=email,
        code_salt=salt,
        code_hash=code_hash,
        created_at=now,
        expires_at=PasswordResetCode.new_expiry(settings.password_reset_code_minutes),
        used_at=None,
    )
    session.add(record)
    session.commit()

    subject = "ACGN咨询助手 - 密码重置验证码"
    text = (
        f"你正在重置 ACGN咨询助手 的登录密码。\n\n"
        f"验证码：{code}\n"
        f"有效期：{settings.password_reset_code_minutes} 分钟\n\n"
        f"如果这不是你本人操作，请忽略此邮件。"
    )
    background_tasks.add_task(send_email, to_email=email, subject=subject, text=text)

    resp: dict = {"detail": "验证码已发送（有效期 10 分钟）"}
    if settings.env != "prod" and settings.email_debug_return_code:
        resp["debug_code"] = code
    return resp


@router.post("/password-reset/confirm")
def password_reset_confirm(payload: PasswordResetConfirm, session: Session = Depends(get_session)):
    settings = get_settings()

    email = (payload.email or "").strip().lower()
    if not _is_qq_email(email):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="仅支持 QQ 邮箱（@qq.com）")

    user = session.exec(select(User).where(User.email == email)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")

    now = _naive_utcnow()
    record = session.exec(
        select(PasswordResetCode)
        .where(PasswordResetCode.email == email)
        .where(PasswordResetCode.used_at.is_(None))
        .order_by(PasswordResetCode.created_at.desc())
    ).first()

    if not record:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码无效")
    if record.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码已过期")

    expected = record.code_hash
    got = _hash_reset_code(salt=record.code_salt, code=(payload.code or "").strip())
    if got != expected:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码错误")

    user.hashed_password = hash_password(payload.new_password)
    record.used_at = now
    session.add(user)
    session.add(record)
    session.commit()

    return {"detail": "密码已重置"}


@router.post("/register/request")
def register_request_code(
    payload: RegisterCodeRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """Send a verification code to email for registration.

    Registration is only allowed after verifying the code.
    """

    settings = get_settings()

    # If SMTP is missing, allow dev/test only when debug_code is enabled.
    if not (settings.smtp_host or "").strip():
        if settings.env == "prod" or not settings.email_debug_return_code:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="SMTP 未配置")

    email = (payload.email or "").strip().lower()
    if not _is_qq_email(email):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="仅支持 QQ 邮箱（@qq.com）")

    exists = session.exec(select(User).where(User.email == email)).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱已注册")

    now = _naive_utcnow()
    latest = session.exec(
        select(RegistrationCode)
        .where(RegistrationCode.email == email)
        .where(RegistrationCode.used_at.is_(None))
        .order_by(RegistrationCode.created_at.desc())
    ).first()

    if latest and latest.expires_at > now:
        delta = (now - latest.created_at).total_seconds()
        if delta < int(settings.register_resend_seconds):
            wait_s = max(0, int(math.ceil(settings.register_resend_seconds - delta)))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"请求过于频繁，请在 {wait_s}s 后再试",
                headers={"Retry-After": str(wait_s)},
            )

    code = _make_reset_code()
    salt = uuid4().hex
    code_hash = _hash_reset_code(salt=salt, code=code)

    record = RegistrationCode(
        email=email,
        code_salt=salt,
        code_hash=code_hash,
        created_at=now,
        expires_at=RegistrationCode.new_expiry(settings.register_code_minutes),
        used_at=None,
    )
    session.add(record)
    session.commit()

    subject = "ACGN咨询助手 - 注册验证码"
    text = (
        "你正在注册 ACGN咨询助手 账号。\n\n"
        f"验证码：{code}\n"
        f"有效期：{settings.register_code_minutes} 分钟\n\n"
        "如果这不是你本人操作，请忽略此邮件。"
    )
    background_tasks.add_task(send_email, to_email=email, subject=subject, text=text)

    resp: dict = {"detail": "验证码已发送（有效期 10 分钟）"}
    if settings.env != "prod" and settings.email_debug_return_code:
        resp["debug_code"] = code
    return resp


@router.post("/register/confirm")
def register_confirm(payload: RegisterConfirm, session: Session = Depends(get_session)):
    return _register_confirm_impl(payload=payload, session=session)
