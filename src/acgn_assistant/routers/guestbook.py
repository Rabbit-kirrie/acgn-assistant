from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import aliased
from sqlmodel import Session, select

from acgn_assistant.core.time import utcnow
from acgn_assistant.db import get_session
from acgn_assistant.models.guestbook import (
    GuestbookMessage,
    GuestbookMessageCreate,
    GuestbookReplyInboxItem,
    GuestbookMessagePublic,
)
from acgn_assistant.models.user import User
from acgn_assistant.routers.deps import get_current_user

router = APIRouter(prefix="/guestbook", tags=["guestbook"])


def _parse_after_dt(v: str | None) -> datetime | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        # Accept common ISO-8601 formats, including trailing 'Z'.
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


@router.get("/inbox", response_model=list[GuestbookReplyInboxItem])
def list_reply_inbox(
    *,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    after: str | None = None,
    limit: int = 20,
):
    """Returns replies to the current user's guestbook messages.

    Intended for lightweight client polling to show 'new replies' indicators.
    """

    limit = max(1, min(50, int(limit)))
    after_dt = _parse_after_dt(after)

    Parent = aliased(GuestbookMessage)
    stmt = (
        select(GuestbookMessage, Parent)
        .join(Parent, GuestbookMessage.parent_id == Parent.id)
        .where(GuestbookMessage.deleted_at.is_(None))
        .where(Parent.deleted_at.is_(None))
        .where(Parent.user_id == user.id)
        .where(GuestbookMessage.user_id != user.id)
        .order_by(GuestbookMessage.created_at.asc())
        .limit(limit)
    )
    if after_dt is not None:
        stmt = stmt.where(GuestbookMessage.created_at > after_dt)

    rows = session.exec(stmt).all()

    items: list[GuestbookReplyInboxItem] = []
    for reply, parent in rows:
        if not reply.parent_id:
            continue
        items.append(
            GuestbookReplyInboxItem(
                id=reply.id,
                parent_id=reply.parent_id,
                created_at=reply.created_at,
                username=reply.username,
                content=reply.content,
                parent_user_id=parent.user_id,
                parent_username=parent.username,
                parent_content=parent.content,
            )
        )
    return items


@router.get("", response_model=list[GuestbookMessagePublic])
def list_messages(
    *,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    limit: int = 50,
    offset: int = 0,
):
    limit = max(1, min(200, int(limit)))
    offset = max(0, min(10_000, int(offset)))

    # Only paginate top-level messages; replies are included under their parent.
    parents = session.exec(
        select(GuestbookMessage)
        .where(GuestbookMessage.deleted_at.is_(None))
        .where(GuestbookMessage.parent_id.is_(None))
        .order_by(GuestbookMessage.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    parent_ids = [it.id for it in parents]
    is_admin = bool(getattr(user, "is_admin", False))

    # Fetch all descendants of the paged top-level messages.
    # We do it iteratively to keep compatibility with SQLite without relying on recursive CTE.
    replies_by_parent: dict[str, list[GuestbookMessage]] = {}
    to_fetch = list(parent_ids)
    fetched_ids: set[str] = set(parent_ids)
    max_nodes = 2000  # safety cap to avoid pathological loads
    total_nodes = len(parent_ids)

    while to_fetch and total_nodes < max_nodes:
        batch = to_fetch[:500]
        to_fetch = to_fetch[500:]

        replies = session.exec(
            select(GuestbookMessage)
            .where(GuestbookMessage.deleted_at.is_(None))
            .where(GuestbookMessage.parent_id.in_(batch))
            .order_by(GuestbookMessage.created_at.asc())
        ).all()

        new_ids: list[str] = []
        for r in replies:
            if not r.parent_id:
                continue
            replies_by_parent.setdefault(r.parent_id, []).append(r)
            if r.id not in fetched_ids:
                fetched_ids.add(r.id)
                new_ids.append(r.id)

        total_nodes += len(new_ids)
        to_fetch.extend(new_ids)

    # Build a node map for quick attachment.
    nodes: dict[str, GuestbookMessagePublic] = {}
    for p in parents:
        nodes[p.id] = GuestbookMessagePublic(
            id=p.id,
            parent_id=None,
            user_id=p.user_id,
            username=p.username,
            content=p.content,
            created_at=p.created_at,
            can_delete=is_admin or (p.user_id == user.id),
            replies=[],
        )

    # Create public nodes for all replies.
    for parent_id, rs in replies_by_parent.items():
        for r in rs:
            nodes[r.id] = GuestbookMessagePublic(
                id=r.id,
                parent_id=r.parent_id,
                user_id=r.user_id,
                username=r.username,
                content=r.content,
                created_at=r.created_at,
                can_delete=is_admin or (r.user_id == user.id),
                replies=[],
            )

    # Attach replies (already ordered by created_at asc per parent because of query ordering).
    for parent_id, rs in replies_by_parent.items():
        parent_node = nodes.get(parent_id)
        if not parent_node:
            continue
        for r in rs:
            child_node = nodes.get(r.id)
            if child_node:
                parent_node.replies.append(child_node)

    # Return top-level nodes in the original order.
    return [nodes[it.id] for it in parents if it.id in nodes]


@router.post("", response_model=GuestbookMessagePublic)
def create_message(
    payload: GuestbookMessageCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    content = (payload.content or "").strip()
    if not content:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="内容不能为空")

    parent_id = (payload.parent_id or "").strip() or None
    if parent_id is not None:
        parent = session.get(GuestbookMessage, parent_id)
        if not parent or parent.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="要回复的留言不存在")

    msg = GuestbookMessage(
        parent_id=parent_id,
        user_id=user.id,
        username=user.username,
        email=user.email,
        content=content,
    )
    session.add(msg)
    session.commit()
    session.refresh(msg)

    return GuestbookMessagePublic(
        id=msg.id,
        parent_id=msg.parent_id,
        user_id=msg.user_id,
        username=msg.username,
        content=msg.content,
        created_at=msg.created_at,
        can_delete=True,
        replies=[],
    )


@router.delete("/{message_id}")
def delete_message(
    message_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    msg = session.get(GuestbookMessage, message_id)
    if not msg or msg.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="留言不存在")

    is_admin = bool(getattr(user, "is_admin", False))
    if not (is_admin or msg.user_id == user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权限删除")

    msg.deleted_at = utcnow()
    session.add(msg)
    session.commit()
    return {"detail": "ok"}
