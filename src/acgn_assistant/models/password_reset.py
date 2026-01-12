from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Field, SQLModel

from acgn_assistant.core.time import utcnow


class PasswordResetCode(SQLModel, table=True):
    __tablename__ = "password_reset_codes"

    id: Optional[int] = Field(default=None, primary_key=True)

    email: str = Field(index=True)

    code_salt: str
    code_hash: str

    # SQLite stores naive datetimes by default; keep this table consistent
    # by storing naive UTC timestamps.
    created_at: datetime = Field(default_factory=lambda: utcnow().replace(tzinfo=None))
    expires_at: datetime = Field(index=True)
    used_at: Optional[datetime] = Field(default=None, index=True)

    @classmethod
    def new_expiry(cls, minutes: int) -> datetime:
        return utcnow().replace(tzinfo=None) + timedelta(minutes=minutes)
