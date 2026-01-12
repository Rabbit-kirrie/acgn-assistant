from __future__ import annotations

import re
from dataclasses import dataclass

from sqlmodel import Session, select

from acgn_assistant.core.time import utcnow
from acgn_assistant.models.memory import MemoryItem


@dataclass(frozen=True)
class MemoryDraft:
    kind: str
    title: str
    content: str
    confidence: float | None = None


_PREF_PATTERNS = [
    re.compile(r"(?:我喜欢|我比较喜欢|偏好|爱玩|喜欢玩)(?P<val>.{1,40})"),
    re.compile(r"(?:我不喜欢|不太喜欢|雷点|避雷)(?P<val>.{1,40})"),
]

_TITLE_PATTERNS = [
    re.compile(r"(?:想玩|想推|求推荐|有没有类似)(?P<title>.{1,30})"),
]


def extract_memory_drafts(*, user_text: str, emotion_label: str | None = None) -> list[MemoryDraft]:
    """非常保守的记忆提取：为 ACGN 咨询保留“偏好/避雷/近期关注作品或类型”等低敏信息。

    注意：避免写入过多隐私细节；不要把整段长文本塞进记忆。
    """

    t = (user_text or "").strip()
    if not t:
        return []

    drafts: list[MemoryDraft] = []

    # 偏好/雷点
    for pat in _PREF_PATTERNS:
        m = pat.search(t)
        if not m:
            continue
        val = (m.group("val") or "").strip()
        if not val:
            continue
        snippet = val
        if len(snippet) > 60:
            snippet = snippet[:60] + "…"

        if "不喜欢" in m.group(0) or "雷点" in m.group(0) or "避雷" in m.group(0):
            drafts.append(MemoryDraft(kind="pref", title="避雷/不喜欢", content=f"用户不喜欢/避雷：{snippet}", confidence=0.55))
        else:
            drafts.append(MemoryDraft(kind="pref", title="偏好/喜欢", content=f"用户偏好：{snippet}", confidence=0.55))

    # 想玩的作品/类型（非常粗略，避免保存过长）
    for pat in _TITLE_PATTERNS:
        m = pat.search(t)
        if not m:
            continue
        title = (m.group("title") or "").strip()
        if not title:
            continue
        snippet = title
        if len(snippet) > 30:
            snippet = snippet[:30] + "…"
        drafts.append(MemoryDraft(kind="fact", title="关注的作品/类型", content=f"用户近期关注：{snippet}", confidence=0.45))
        break

    # 去重：按 (kind,title) 保留第一条
    seen: set[tuple[str, str]] = set()
    out: list[MemoryDraft] = []
    for d in drafts:
        key = (d.kind, d.title)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def upsert_memory_drafts(*, session: Session, user_id: str, drafts: list[MemoryDraft]) -> int:
    """将记忆草稿写入 MemoryItem。若存在同 kind+title 的未删除记忆，则更新。"""

    if not drafts:
        return 0

    written = 0
    for d in drafts:
        kind = (d.kind or "fact").strip() or "fact"
        title = (d.title or "").strip()
        content = (d.content or "").strip()
        if not title or not content:
            continue

        existing = session.exec(
            select(MemoryItem)
            .where(MemoryItem.user_id == user_id)
            .where(MemoryItem.deleted_at.is_(None))
            .where(MemoryItem.kind == kind)
            .where(MemoryItem.title == title)
        ).first()

        if existing:
            existing.content = content
            existing.confidence = d.confidence
            existing.updated_at = utcnow()
            session.add(existing)
            written += 1
            continue

        session.add(
            MemoryItem(
                user_id=user_id,
                kind=kind,
                title=title,
                content=content,
                confidence=d.confidence,
                updated_at=utcnow(),
            )
        )
        written += 1

    if written:
        session.commit()
    return written
