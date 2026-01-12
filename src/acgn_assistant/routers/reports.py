from __future__ import annotations

from collections import Counter
from datetime import date, datetime

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from acgn_assistant.db import get_session
from acgn_assistant.models.conversation import Conversation, Message
from acgn_assistant.models.memory import MemoryItem
from acgn_assistant.models.report import MonthlyReport
from acgn_assistant.routers.deps import get_current_user
from acgn_assistant.core.time import utcnow

router = APIRouter(prefix="/reports", tags=["reports"])


def _month_range(d: date) -> tuple[date, date]:
    start = date(d.year, d.month, 1)
    if d.month == 12:
        end = date(d.year + 1, 1, 1)
    else:
        end = date(d.year, d.month + 1, 1)
    return start, end


def _week_range(d: date) -> tuple[date, date]:
    # ISO week, Monday as start
    start = d
    while start.weekday() != 0:
        start = date.fromordinal(start.toordinal() - 1)
    end = date.fromordinal(start.toordinal() + 7)
    return start, end


def _top_keywords(texts: list[str], *, limit: int = 6) -> list[str]:
    # Extremely lightweight, language-agnostic keyword bucketing.
    # This is for weekly/monthly placeholder reports only.
    buckets = {
        "剧情": ["剧情", "展开", "反转", "伏笔", "设定", "世界观"],
        "角色": ["角色", "女主", "男主", "人设", "cp", "恋爱"],
        "动画": ["动画", "番", "追番", "op", "ed", "ova", "剧场版"],
        "漫画": ["漫画", "分镜", "连载", "话", "章节"],
        "轻小说": ["轻小说", "轻改", "文库", "卷"],
        "画风": ["画风", "立绘", "原画", "cg"],
        "音乐": ["音乐", "bgm", "配乐", "op", "ed"],
        "配音": ["配音", "声优", "cv"],
        "系统": ["系统", "ui", "选项", "快进", "回看", "存档"],
        "纯爱": ["纯爱"],
        "致郁": ["致郁", "刀", "胃痛"],
        "电波": ["电波"],
        "猎奇": ["猎奇", "重口"],
        "NTR": ["ntr", "牛头人"],
        "R18": ["r18", "h scene", "hscene", "黄油"],
    }

    counter: Counter[str] = Counter()
    lowered = [t.lower() for t in texts if t]
    for label, keys in buckets.items():
        hits = 0
        for t in lowered:
            if any(k in t for k in keys):
                hits += 1
        if hits:
            counter[label] = hits
    return [k for k, _ in counter.most_common(limit)]


@router.post("/monthly", response_model=MonthlyReport)
def generate_monthly_report(
    year: int | None = None,
    month: int | None = None,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    today = date.today()
    y = year or today.year
    m = month or today.month
    start, end = _month_range(date(y, m, 1))

    # 对话活跃度
    convs = session.exec(
        select(Conversation.id)
        .where(Conversation.user_id == user.id)
        .where(Conversation.deleted_at.is_(None))
        .where(Conversation.created_at >= datetime.combine(start, datetime.min.time()))
        .where(Conversation.created_at < datetime.combine(end, datetime.min.time()))
    ).all()
    conv_ids = [c[0] for c in convs]

    msg_count = 0
    msg_texts: list[str] = []
    if conv_ids:
        msgs = session.exec(
            select(Message.content)
            .where(Message.conversation_id.in_(conv_ids))
            .where(Message.deleted_at.is_(None))
        ).all()
        msg_texts = [m[0] for m in msgs if m and m[0]]
        msg_count = len(msg_texts)

    # 记忆（偏好/避雷/关注作品等）
    memories = list(
        session.exec(
            select(MemoryItem)
            .where(MemoryItem.user_id == user.id)
            .where(MemoryItem.deleted_at.is_(None))
            .order_by(MemoryItem.updated_at.desc())
            .limit(8)
        )
    )
    memory_lines = []
    for m_item in memories[:5]:
        memory_lines.append(f"- [{m_item.kind}] {m_item.title}：{m_item.content}")
    memory_block = "\n".join(memory_lines) if memory_lines else "- （暂无）"

    keywords = _top_keywords(msg_texts)
    kw_text = "、".join(keywords) if keywords else "（暂无）"

    report_text = (
        f"本月 ACGN 资讯回顾（占位）（{start} ~ {end}）：\n"
        f"- 对话活跃：创建会话 {len(conv_ids)} 次，消息 {msg_count} 条。\n"
        f"- 本月关键词：{kw_text}\n"
        + "- 评测：已从本 Demo 中移除。\n"
        + "\n【记忆摘要（偏好/避雷/关注）】\n"
        + memory_block
        + "\n\n【下月建议（占位）】\n"
        + "1) 选 1 个你最在意的方向（轻松/强剧情/强演出/电波/致郁/猎奇/推理），我可以按偏好出一份清单。\n"
        + "2) 提供 1~3 部你喜欢/踩雷的作品（动画/漫画/轻小说/游戏均可），我会把偏好写进记忆并提升推荐命中率。"
    )

    rep = MonthlyReport(user_id=user.id, period_start=start, period_end=end, report_text=report_text)
    session.add(rep)
    session.commit()
    session.refresh(rep)
    return rep


@router.post("/weekly", response_model=MonthlyReport)
def generate_weekly_report(
    year: int | None = None,
    month: int | None = None,
    day: int | None = None,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    today = date.today()
    y = year or today.year
    m = month or today.month
    d = day or today.day
    start, end = _week_range(date(y, m, d))

    convs = session.exec(
        select(Conversation.id)
        .where(Conversation.user_id == user.id)
        .where(Conversation.deleted_at.is_(None))
        .where(Conversation.created_at >= datetime.combine(start, datetime.min.time()))
        .where(Conversation.created_at < datetime.combine(end, datetime.min.time()))
    ).all()
    conv_ids = [c[0] for c in convs]

    msg_texts: list[str] = []
    if conv_ids:
        msgs = session.exec(
            select(Message.content)
            .where(Message.conversation_id.in_(conv_ids))
            .where(Message.deleted_at.is_(None))
        ).all()
        msg_texts = [m2[0] for m2 in msgs if m2 and m2[0]]

    keywords = _top_keywords(msg_texts)
    kw_text = "、".join(keywords) if keywords else "（暂无）"

    memories = list(
        session.exec(
            select(MemoryItem)
            .where(MemoryItem.user_id == user.id)
            .where(MemoryItem.deleted_at.is_(None))
            .order_by(MemoryItem.updated_at.desc())
            .limit(6)
        )
    )
    memory_lines = []
    for m_item in memories[:4]:
        memory_lines.append(f"- [{m_item.kind}] {m_item.title}：{m_item.content}")
    memory_block = "\n".join(memory_lines) if memory_lines else "- （暂无）"

    report_text = (
        f"本周 ACGN 周报（占位）（{start} ~ {end}）：\n"
        f"- 本周关键词：{kw_text}\n"
        f"- 对话消息数：{len(msg_texts)}\n"
        + "\n【本周偏好/避雷摘要】\n"
        + memory_block
        + "\n\n【下周想了解（占位）】\n"
        + "- 你想要：轻松日常 / 强剧情 / 强演出 / 纯爱 / 致郁 / 电波 / 猎奇 / 推理？\n"
        + "- 你接受剧透吗？更偏好动画/漫画/轻小说/游戏哪一种？（如果是游戏，平台偏好是什么？）"
    )

    rep = MonthlyReport(user_id=user.id, period_start=start, period_end=end, report_text=report_text)
    session.add(rep)
    session.commit()
    session.refresh(rep)
    return rep


@router.get("/monthly", response_model=list[MonthlyReport])
def list_monthly_reports(session: Session = Depends(get_session), user=Depends(get_current_user)):
    return list(
        session.exec(
            select(MonthlyReport)
            .where(MonthlyReport.user_id == user.id)
            .where(MonthlyReport.deleted_at.is_(None))
            .order_by(MonthlyReport.created_at.desc())
        )
    )


@router.delete("/monthly/{report_id}")
def soft_delete_monthly_report(
    report_id: str,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    item = session.get(MonthlyReport, report_id)
    if not item or item.user_id != user.id or item.deleted_at is not None:
        return {"deleted": False}
    item.deleted_at = utcnow()
    session.add(item)
    session.commit()
    return {"deleted": True}
