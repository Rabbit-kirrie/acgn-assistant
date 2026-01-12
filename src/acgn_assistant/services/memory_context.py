from __future__ import annotations

import json

from sqlmodel import Session, select

from acgn_assistant.models.memory import MemoryItem
from acgn_assistant.models.user_profile import UserProfile


def build_user_memory_context(*, session: Session, user_id: str) -> str:
    """构建可注入提示词的“用户记忆上下文”。

    原则：短、脱敏、可执行；避免把用户原始长文本全部塞进 prompt。
    """

    parts: list[str] = []

    prof = session.exec(select(UserProfile).where(UserProfile.user_id == user_id)).first()
    if prof:
        if prof.display_name:
            parts.append(f"用户称呼/昵称：{prof.display_name}")

        # preferences 只取很小一部分 key，避免 prompt 膨胀
        try:
            prefs = json.loads(prof.preferences_json or "{}")
        except Exception:
            prefs = {}

        preferred_tags = prefs.get("preferred_tags") if isinstance(prefs, dict) else None
        if isinstance(preferred_tags, list) and preferred_tags:
            parts.append("偏好标签：" + "、".join(str(x) for x in preferred_tags[:8]))

    # 长期记忆（最新 N 条）
    mems = session.exec(
        select(MemoryItem)
        .where(MemoryItem.user_id == user_id)
        .where(MemoryItem.deleted_at.is_(None))
        .order_by(MemoryItem.updated_at.desc())
        .limit(5)
    ).all()
    if mems:
        items = [f"- [{m.kind}] {m.title}：{m.content}" for m in mems]
        parts.append("长期记忆（最新）：\n" + "\n".join(items))

    if not parts:
        return ""

    return "\n".join(parts)
