from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from acgn_assistant.db import get_session
from acgn_assistant.models.events import UserResourceEvent, UserResourceEventCreate
from acgn_assistant.models.resource import Resource
from acgn_assistant.routers.deps import get_current_user
from acgn_assistant.services.recommendations_engine import recommend_resources

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


_ALLOWED_EVENT_TYPES = {"recommended", "viewed", "saved", "dismissed"}


@router.post("/events")
def record_event(
    payload: UserResourceEventCreate,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    et = (payload.event_type or "").strip().lower()
    if et not in _ALLOWED_EVENT_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的 event_type")

    r = session.get(Resource, payload.resource_id)
    if not r or r.deleted_at is not None or not r.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资源不存在")

    session.add(UserResourceEvent(user_id=user.id, resource_id=r.id, event_type=et))
    session.commit()
    return {"ok": True}


@router.get("")
def recommend(
    limit: int = 5,
    days: int = 7,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    return recommend_resources(session=session, user_id=user.id, limit=limit, days=days)
