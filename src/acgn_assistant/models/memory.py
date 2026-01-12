from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlmodel import Field, SQLModel

from acgn_assistant.core.time import utcnow


class MemoryItem(SQLModel, table=True):
    """用户长期记忆（可被对话引用）。

    设计目标：
    - 支持“金鱼记忆”问题的长期修复（偏好/目标/重要事实/应对策略等）。
    - 默认软删除（deleted_at）。
    - 不强制存敏感细节：建议存“可复用的、脱敏后的摘要”。
    """

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    user_id: str = Field(index=True, foreign_key="user.id")

    # 例如：preference/goal/fact/strategy/trigger
    kind: str = Field(index=True, default="fact")

    # 简短标题便于检索/展示
    title: str = Field(index=True)

    # 脱敏后的记忆内容（短文本）
    content: str

    # 0..1（可选）：来源可信度/用户确认度
    confidence: Optional[float] = Field(default=None)

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    deleted_at: Optional[datetime] = Field(default=None, index=True)


class MemoryItemCreate(SQLModel):
    kind: str = "fact"
    title: str
    content: str
    confidence: Optional[float] = None


class MemoryItemUpdate(SQLModel):
    kind: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    confidence: Optional[float] = None
