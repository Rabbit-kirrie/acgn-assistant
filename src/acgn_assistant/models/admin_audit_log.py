from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from sqlmodel import Field, SQLModel

from acgn_assistant.core.time import utcnow


class AdminAuditLog(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)

    created_at: datetime = Field(default_factory=utcnow, index=True)

    actor_user_id: str = Field(index=True)
    actor_email: str = Field(index=True)

    action: str = Field(index=True)

    target_user_id: Optional[str] = Field(default=None, index=True)
    target_email: Optional[str] = Field(default=None, index=True)

    ip: Optional[str] = None
    user_agent: Optional[str] = None

    details_json: Optional[str] = None

    @staticmethod
    def encode_details(details: Any) -> Optional[str]:
        if details is None:
            return None
        try:
            return json.dumps(details, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            return None
