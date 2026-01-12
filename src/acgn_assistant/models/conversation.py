from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlmodel import Field, SQLModel

from acgn_assistant.core.time import utcnow


class Conversation(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    user_id: str = Field(index=True)
    title: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    deleted_at: Optional[datetime] = Field(default=None, index=True)


class Message(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    conversation_id: str = Field(index=True)
    role: str = Field(index=True)  # user/assistant/system
    content: str
    is_crisis: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow)
    deleted_at: Optional[datetime] = Field(default=None, index=True)


class ConversationCreate(SQLModel):
    title: Optional[str] = None


class ConversationUpdate(SQLModel):
    title: Optional[str] = None


class MessageCreate(SQLModel):
    content: str
    deep_think: bool = False
    web_search: bool = False
    web_search_query: str | None = None
