from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from acgn_assistant.db import get_session
from acgn_assistant.models.user import UserPublic, UserUpdate
from acgn_assistant.routers.deps import get_current_user

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserPublic)
def me(user=Depends(get_current_user)):
    return user


@router.put("/me", response_model=UserPublic)
def update_me(
    payload: UserUpdate,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    if payload.username is not None:
        user.username = payload.username

    session.add(user)
    session.commit()
    session.refresh(user)
    return user
