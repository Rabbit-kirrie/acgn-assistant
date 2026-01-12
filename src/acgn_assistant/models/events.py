from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlmodel import Field, SQLModel

from acgn_assistant.core.time import utcnow


class UserResourceEvent(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    user_id: str = Field(index=True, foreign_key="user.id")
    resource_id: str = Field(index=True, foreign_key="resource.id")

    # recommended/viewed/saved
    event_type: str = Field(index=True)

    created_at: datetime = Field(default_factory=utcnow)


class UserResourceEventCreate(SQLModel):
    resource_id: str
    # recommended/viewed/saved/dismissed
    event_type: str
