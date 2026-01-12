from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, SQLModel, select

from acgn_assistant.db import get_session
from acgn_assistant.models.conversation import Conversation, Message
from acgn_assistant.models.user import User
from acgn_assistant.routers.deps import get_current_admin_user


class AdminConversationPublic(SQLModel):
    id: str
    user_id: str
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    user_email: Optional[str] = None
    user_username: Optional[str] = None


router = APIRouter(prefix="/admin/conversations", tags=["admin"])


def _get_conversation_any_user_or_404(
    session: Session,
    conversation_id: str,
    *,
    include_deleted: bool,
) -> Conversation:
    convo = session.exec(select(Conversation).where(Conversation.id == conversation_id)).first()
    if not convo or (not include_deleted and convo.deleted_at is not None):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return convo


@router.get("", response_model=list[AdminConversationPublic])
def admin_list_conversations(
    session: Session = Depends(get_session),
    _admin=Depends(get_current_admin_user),
    user_id: str | None = Query(default=None, description="筛选某个用户的会话 user_id"),
    include_deleted: bool = Query(default=False, description="是否包含已删除会话"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(Conversation).order_by(Conversation.created_at.desc()).offset(offset).limit(limit)
    if user_id:
        stmt = stmt.where(Conversation.user_id == user_id)
    if not include_deleted:
        stmt = stmt.where(Conversation.deleted_at.is_(None))

    convos = list(session.exec(stmt))
    user_ids = {c.user_id for c in convos if c.user_id}

    users_by_id: dict[str, User] = {}
    if user_ids:
        users = session.exec(select(User).where(User.id.in_(list(user_ids))))
        users_by_id = {u.id: u for u in users}

    out: list[AdminConversationPublic] = []
    for c in convos:
        u = users_by_id.get(c.user_id)
        out.append(
            AdminConversationPublic(
                id=c.id,
                user_id=c.user_id,
                title=c.title,
                created_at=c.created_at,
                updated_at=c.updated_at,
                deleted_at=c.deleted_at,
                user_email=getattr(u, "email", None) if u else None,
                user_username=getattr(u, "username", None) if u else None,
            )
        )
    return out


@router.get("/{conversation_id}", response_model=AdminConversationPublic)
def admin_get_conversation(
    conversation_id: str,
    session: Session = Depends(get_session),
    _admin=Depends(get_current_admin_user),
    include_deleted: bool = Query(default=False, description="是否包含已删除会话"),
):
    convo = _get_conversation_any_user_or_404(session, conversation_id, include_deleted=include_deleted)
    user = session.exec(select(User).where(User.id == convo.user_id)).first()
    return AdminConversationPublic(
        id=convo.id,
        user_id=convo.user_id,
        title=convo.title,
        created_at=convo.created_at,
        updated_at=convo.updated_at,
        deleted_at=convo.deleted_at,
        user_email=getattr(user, "email", None) if user else None,
        user_username=getattr(user, "username", None) if user else None,
    )


@router.get("/{conversation_id}/messages", response_model=list[Message])
def admin_list_messages(
    conversation_id: str,
    session: Session = Depends(get_session),
    _admin=Depends(get_current_admin_user),
    include_deleted: bool = Query(default=False, description="是否包含已删除消息"),
):
    _get_conversation_any_user_or_404(session, conversation_id, include_deleted=True)

    stmt = select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc())
    if not include_deleted:
        stmt = stmt.where(Message.deleted_at.is_(None))
    return list(session.exec(stmt))
