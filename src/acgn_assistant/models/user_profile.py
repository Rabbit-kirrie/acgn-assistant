from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

from acgn_assistant.core.time import utcnow


class UserProfile(SQLModel, table=True):
    # 1:1：每个用户一个档案
    user_id: str = Field(primary_key=True, foreign_key="user.id")

    display_name: Optional[str] = None
    preferences_json: str = Field(default="{}")

    # Legacy columns kept for backward compatibility with existing SQLite schemas.
    # They are not used by the ACGN assistant, but must remain non-null to allow inserts.
    goals_json: str = Field(default="[]")
    health_summary: str = Field(default="")

    updated_at: datetime = Field(default_factory=utcnow)


class UserProfileUpdate(SQLModel):
    display_name: Optional[str] = None
    preferences: Optional[dict] = None
