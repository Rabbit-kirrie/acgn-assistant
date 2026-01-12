from __future__ import annotations

from fastapi import Request
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from acgn_assistant.core.config import get_settings
from acgn_assistant.core.security import hash_password
from acgn_assistant.db import get_session
from acgn_assistant.models.admin_audit_log import AdminAuditLog
from acgn_assistant.models.user import AdminUserUpdate, User, UserCreate, UserPublic, UserUpdate
from acgn_assistant.routers.deps import get_current_admin_user

router = APIRouter(prefix="/admin/users", tags=["admin"])


@router.get("", response_model=list[UserPublic])
def list_users(
    session: Session = Depends(get_session),
    _admin=Depends(get_current_admin_user),
):
    return list(session.exec(select(User).order_by(User.created_at.desc())))


@router.get("/{user_id}", response_model=UserPublic)
def get_user(
    user_id: str,
    session: Session = Depends(get_session),
    _admin=Depends(get_current_admin_user),
):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return user


@router.post("", response_model=UserPublic)
def create_user(
    payload: UserCreate,
    request: Request,
    session: Session = Depends(get_session),
    _admin=Depends(get_current_admin_user),
):
    exists = session.exec(select(User).where(User.email == payload.email)).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱已注册")

    user = User(
        email=payload.email,
        username=payload.username,
        hashed_password=hash_password(payload.password),
        is_admin=False,
    )
    session.add(user)
    # Audit
    try:
        admin: User = _admin
        ip = None
        ua = None
        if request is not None:
            try:
                ip = getattr(getattr(request, "client", None), "host", None)
            except Exception:
                ip = None
            try:
                ua = request.headers.get("user-agent")
            except Exception:
                ua = None

        session.add(
            AdminAuditLog(
                actor_user_id=admin.id,
                actor_email=admin.email,
                action="admin_user.create",
                target_user_id=user.id,
                target_email=user.email,
                ip=ip,
                user_agent=ua,
                details_json=AdminAuditLog.encode_details({"email": user.email, "username": user.username}),
            )
        )
    except Exception:
        # Best-effort only: do not block admin actions if audit logging fails.
        pass
    session.commit()
    session.refresh(user)
    return user


@router.put("/{user_id}", response_model=UserPublic)
def update_user(
    user_id: str,
    payload: AdminUserUpdate,
    request: Request,
    session: Session = Depends(get_session),
    _admin=Depends(get_current_admin_user),
):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    admin: User = _admin

    settings = get_settings()
    bootstrap_admin_email = (getattr(settings, "admin_email", "") or "").strip().lower()
    is_bootstrap_admin = bool(bootstrap_admin_email) and (user.email or "").strip().lower() == bootstrap_admin_email

    is_super_admin = (not bootstrap_admin_email) or ((admin.email or "").strip().lower() == bootstrap_admin_email)

    before = {
        "username": user.username,
        "is_active": bool(getattr(user, "is_active", True)),
        "is_admin": bool(getattr(user, "is_admin", False)),
    }

    if payload.username is not None:
        user.username = payload.username

    if payload.is_active is not None:
        if is_bootstrap_admin and payload.is_active is False:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能禁用最高管理员")
        if user.id == admin.id and payload.is_active is False:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能禁用自己")
        user.is_active = bool(payload.is_active)

    if payload.is_admin is not None:
        if not is_super_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要最高管理员权限")
        if is_bootstrap_admin and payload.is_admin is False:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能取消最高管理员权限")
        if user.id == admin.id and payload.is_admin is False:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能取消自己的管理员权限")

        # Prevent removing the last active admin.
        if payload.is_admin is False and getattr(user, "is_admin", False):
            active_admins = session.exec(select(User).where(User.is_admin == True).where(User.is_active == True)).all()
            if len(active_admins) <= 1:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少需要保留 1 个可用管理员")

        user.is_admin = bool(payload.is_admin)

    after = {
        "username": user.username,
        "is_active": bool(getattr(user, "is_active", True)),
        "is_admin": bool(getattr(user, "is_admin", False)),
    }

    changes: dict[str, dict[str, object]] = {}
    for k in ("username", "is_active", "is_admin"):
        if before.get(k) != after.get(k):
            changes[k] = {"from": before.get(k), "to": after.get(k)}

    # Audit (best-effort)
    if changes:
        try:
            ip = None
            ua = None
            if request is not None:
                try:
                    ip = getattr(getattr(request, "client", None), "host", None)
                except Exception:
                    ip = None
                try:
                    ua = request.headers.get("user-agent")
                except Exception:
                    ua = None

            action = "admin_user.update"
            if "is_admin" in changes:
                action = "admin_user.promote_admin" if bool(after["is_admin"]) else "admin_user.demote_admin"
            elif "is_active" in changes:
                action = "admin_user.disable" if (after["is_active"] is False) else "admin_user.enable"

            session.add(
                AdminAuditLog(
                    actor_user_id=admin.id,
                    actor_email=admin.email,
                    action=action,
                    target_user_id=user.id,
                    target_email=user.email,
                    ip=ip,
                    user_agent=ua,
                    details_json=AdminAuditLog.encode_details({"changes": changes}),
                )
            )
        except Exception:
            pass

    session.add(user)
    session.commit()
    session.refresh(user)
    return user
