from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlmodel import Field, SQLModel

from acgn_assistant.core.time import utcnow


class Resource(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)

    # article/audio/exercise
    resource_type: str = Field(index=True)
    title: str = Field(index=True)

    # url 与 content 二选一或都存在（例如 url 指向文章，content 存简要摘要）
    url: Optional[str] = None
    content: Optional[str] = None

    is_active: bool = Field(default=True, index=True)

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    deleted_at: Optional[datetime] = Field(default=None, index=True)


class Tag(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    name: str = Field(index=True, unique=True)


class ResourceTagLink(SQLModel, table=True):
    # M:N 关联表
    resource_id: str = Field(primary_key=True, foreign_key="resource.id")
    tag_id: str = Field(primary_key=True, foreign_key="tag.id")


class ResourceCreate(SQLModel):
    resource_type: str
    title: str
    url: Optional[str] = None
    content: Optional[str] = None
    tag_names: list[str] = []


class ResourceUpdate(SQLModel):
    resource_type: Optional[str] = None
    title: Optional[str] = None
    url: Optional[str] = None
    content: Optional[str] = None
    is_active: Optional[bool] = None
    tag_names: Optional[list[str]] = None
