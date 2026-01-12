from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from acgn_assistant.db import get_session
from acgn_assistant.models.admin_audit_log import AdminAuditLog
from acgn_assistant.routers.deps import get_current_super_admin_user

router = APIRouter(prefix="/admin/audit-logs", tags=["admin"])


@router.get("", response_model=list[AdminAuditLog])
def list_audit_logs(
    *,
    session: Session = Depends(get_session),
    _super_admin=Depends(get_current_super_admin_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10_000),
    action: str | None = None,
    actor_user_id: str | None = None,
    target_user_id: str | None = None,
):
    stmt = select(AdminAuditLog)
    if action:
        stmt = stmt.where(AdminAuditLog.action == action)
    if actor_user_id:
        stmt = stmt.where(AdminAuditLog.actor_user_id == actor_user_id)
    if target_user_id:
        stmt = stmt.where(AdminAuditLog.target_user_id == target_user_id)

    stmt = stmt.order_by(AdminAuditLog.created_at.desc()).offset(offset).limit(limit)
    return list(session.exec(stmt))
