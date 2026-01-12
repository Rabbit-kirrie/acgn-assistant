from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from acgn_assistant.db import get_session
from acgn_assistant.models.user_profile import UserProfile, UserProfileUpdate
from acgn_assistant.routers.deps import get_current_user
from acgn_assistant.core.time import utcnow

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=UserProfile)
def get_profile(session: Session = Depends(get_session), user=Depends(get_current_user)):
    prof = session.exec(select(UserProfile).where(UserProfile.user_id == user.id)).first()
    if not prof:
        prof = UserProfile(user_id=user.id)
        session.add(prof)
        session.commit()
        session.refresh(prof)
    return prof


@router.put("", response_model=UserProfile)
def update_profile(
    payload: UserProfileUpdate,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    prof = session.exec(select(UserProfile).where(UserProfile.user_id == user.id)).first()
    if not prof:
        prof = UserProfile(user_id=user.id)
        session.add(prof)

    if payload.display_name is not None:
        prof.display_name = payload.display_name
    if payload.preferences is not None:
        prof.preferences_json = json.dumps(payload.preferences, ensure_ascii=False)
    prof.updated_at = utcnow()

    session.add(prof)
    session.commit()
    session.refresh(prof)
    return prof
