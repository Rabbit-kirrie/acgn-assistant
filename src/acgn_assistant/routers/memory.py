from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from acgn_assistant.db import get_session
from acgn_assistant.models.memory import MemoryItem, MemoryItemCreate, MemoryItemUpdate
from acgn_assistant.routers.deps import get_current_user
from acgn_assistant.core.time import utcnow

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("", response_model=list[MemoryItem])
def list_memory(
    kind: str | None = None,
    limit: int = 50,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    stmt = select(MemoryItem).where(MemoryItem.user_id == user.id).where(MemoryItem.deleted_at.is_(None))
    if kind:
        stmt = stmt.where(MemoryItem.kind == kind)
    stmt = stmt.order_by(MemoryItem.updated_at.desc())
    limit = max(1, min(int(limit), 200))
    return list(session.exec(stmt.limit(limit)))


@router.post("", response_model=MemoryItem)
def create_memory(
    payload: MemoryItemCreate,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    item = MemoryItem(
        user_id=user.id,
        kind=(payload.kind or "fact").strip() or "fact",
        title=payload.title.strip(),
        content=payload.content.strip(),
        confidence=payload.confidence,
        updated_at=utcnow(),
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.put("/{memory_id}", response_model=MemoryItem)
def update_memory(
    memory_id: str,
    payload: MemoryItemUpdate,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    item = session.get(MemoryItem, memory_id)
    if not item or item.user_id != user.id or item.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记忆不存在")

    if payload.kind is not None:
        item.kind = (payload.kind or "fact").strip() or "fact"
    if payload.title is not None:
        item.title = payload.title.strip()
    if payload.content is not None:
        item.content = payload.content.strip()
    if payload.confidence is not None:
        item.confidence = payload.confidence

    item.updated_at = utcnow()
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.delete("/{memory_id}")
def soft_delete_memory(
    memory_id: str,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    item = session.get(MemoryItem, memory_id)
    if not item or item.user_id != user.id or item.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记忆不存在")

    item.deleted_at = utcnow()
    item.updated_at = utcnow()
    session.add(item)
    session.commit()
    return {"deleted": True}
