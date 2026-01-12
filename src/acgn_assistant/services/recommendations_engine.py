from __future__ import annotations

import json
from collections import Counter
from datetime import timedelta

from sqlmodel import Session, select

from acgn_assistant.core.time import utcnow
from acgn_assistant.models.events import UserResourceEvent
from acgn_assistant.models.resource import Resource, ResourceTagLink, Tag
from acgn_assistant.models.user_profile import UserProfile


def _load_preferred_tags(session: Session, user_id: str) -> list[str]:
    prof = session.exec(select(UserProfile).where(UserProfile.user_id == user_id)).first()
    if not prof:
        return []
    try:
        prefs = json.loads(prof.preferences_json or "{}")
    except Exception:
        prefs = {}
    if not isinstance(prefs, dict):
        return []
    tags = prefs.get("preferred_tags")
    if not isinstance(tags, list):
        return []
    out: list[str] = []
    for t in tags:
        s = str(t).strip()
        if s:
            out.append(s)
    return out[:10]


def _top_saved_tags(session: Session, user_id: str, *, days: int = 90, limit: int = 5) -> list[str]:
    since = utcnow() - timedelta(days=days)
    rows = session.exec(
        select(Tag.name)
        .join(ResourceTagLink, ResourceTagLink.tag_id == Tag.id)
        .join(Resource, Resource.id == ResourceTagLink.resource_id)
        .join(UserResourceEvent, UserResourceEvent.resource_id == Resource.id)
        .where(UserResourceEvent.user_id == user_id)
        .where(UserResourceEvent.event_type == "saved")
        .where(UserResourceEvent.created_at >= since)
        .where(Resource.deleted_at.is_(None))
        .where(Resource.is_active.is_(True))
    ).all()
    names = [r[0] for r in rows if r and r[0]]
    if not names:
        return []
    return [n for n, _c in Counter(names).most_common(max(1, min(limit, 20)))]


def _recent_dismissed_resource_ids(session: Session, user_id: str, *, days: int = 30) -> set[str]:
    since = utcnow() - timedelta(days=days)
    rows = session.exec(
        select(UserResourceEvent.resource_id)
        .where(UserResourceEvent.user_id == user_id)
        .where(UserResourceEvent.event_type == "dismissed")
        .where(UserResourceEvent.created_at >= since)
    ).all()
    return {r[0] for r in rows if r and r[0]}


def recommend_resources(
    *,
    session: Session,
    user_id: str,
    limit: int = 5,
    days: int = 7,
) -> dict:
    """按用户偏好 + 收藏行为推荐资源，并记录 recommended 事件。"""

    limit = max(1, min(int(limit), 20))
    days = max(1, min(int(days), 365))

    preferred_tags = _load_preferred_tags(session, user_id)
    saved_tags = _top_saved_tags(session, user_id)

    tags: list[str] = []
    tags.extend(preferred_tags)
    tags.extend(saved_tags)

    # 没有任何标签时，给一个极小的默认集合，避免空 in_()。
    if not tags:
        tags = ["剧情", "角色", "动画", "漫画", "轻小说", "游戏"]

    # 去重保序
    dedup: list[str] = []
    seen: set[str] = set()
    for t in tags:
        if t not in seen:
            seen.add(t)
            dedup.append(t)
    tags = dedup[:15]

    dismissed_ids = _recent_dismissed_resource_ids(session, user_id)

    stmt = (
        select(Resource)
        .distinct()
        .join(ResourceTagLink, ResourceTagLink.resource_id == Resource.id)
        .join(Tag, Tag.id == ResourceTagLink.tag_id)
        .where(Resource.deleted_at.is_(None))
        .where(Resource.is_active.is_(True))
        .where(Tag.name.in_(tags))
        .order_by(Resource.created_at.desc())
    )
    if dismissed_ids:
        stmt = stmt.where(Resource.id.notin_(dismissed_ids))

    resources = list(session.exec(stmt))
    picked = resources[:limit]

    for r in picked:
        session.add(UserResourceEvent(user_id=user_id, resource_id=r.id, event_type="recommended"))
    session.commit()

    based_on: list[str] = []
    if preferred_tags:
        based_on.append("profile.preferred_tags")
    if saved_tags:
        based_on.append("events.saved")
    if not based_on:
        based_on.append("default")

    return {"based_on": based_on, "tags": tags, "items": picked}
