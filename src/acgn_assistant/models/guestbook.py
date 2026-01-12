from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field as PydField
from sqlmodel import Field, SQLModel

from acgn_assistant.core.time import utcnow


class GuestbookMessage(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)

    parent_id: Optional[str] = Field(default=None, index=True)

    user_id: str = Field(index=True)
    username: str = Field(index=True)
    email: str = Field(index=True)

    content: str

    created_at: datetime = Field(default_factory=utcnow, index=True)
    deleted_at: Optional[datetime] = Field(default=None, index=True)


class GuestbookMessageCreate(BaseModel):
    content: str = PydField(min_length=1, max_length=800)
    parent_id: Optional[str] = None


class GuestbookMessagePublic(BaseModel):
    id: str
    parent_id: Optional[str] = None
    user_id: str
    username: str
    content: str
    created_at: datetime
    can_delete: bool = False
    replies: list["GuestbookMessagePublic"] = []


class GuestbookReplyInboxItem(BaseModel):
    id: str
    parent_id: str
    created_at: datetime
    username: str
    content: str

    parent_user_id: str
    parent_username: str
    parent_content: str


GuestbookMessagePublic.model_rebuild()
