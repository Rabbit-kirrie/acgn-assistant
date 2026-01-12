from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlmodel import Field, SQLModel

from acgn_assistant.core.time import utcnow


class User(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    email: str = Field(index=True, unique=True)
    username: str = Field(index=True)
    hashed_password: str
    is_admin: bool = Field(default=False, index=True)
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=utcnow)


class UserPublic(SQLModel):
    id: str
    email: str
    username: str
    is_admin: bool
    is_active: bool
    created_at: datetime


class UserCreate(SQLModel):
    email: str
    username: str
    password: str


class UserUpdate(SQLModel):
    username: Optional[str] = None


class AdminUserUpdate(SQLModel):
    username: Optional[str] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None
