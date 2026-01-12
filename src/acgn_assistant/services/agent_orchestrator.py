from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sqlmodel import Session

from acgn_assistant.core.config import get_settings
from acgn_assistant.services.agent_prompts import (
    RESOURCE_EXPERT_SYSTEM,
    SUPPORTIVE_LISTENER_SYSTEM,
    TERM_EXPLAINER_SYSTEM,
)
from acgn_assistant.services.deepseek_client import DeepSeekClient, DeepSeekConfig
from acgn_assistant.services.guardrails import detect_crisis
from acgn_assistant.services.memory_context import build_user_memory_context
from acgn_assistant.services.memory_writer import extract_memory_drafts, upsert_memory_drafts
from acgn_assistant.services.recommendations_engine import recommend_resources


@dataclass(frozen=True)
class AgentDecision:
    needs_recommendations: bool = False
    needs_term_explain: bool = False
    needs_overview: bool = False
    term: str | None = None


_RESOURCE_HINTS = [
    "推荐",
    "类似",
    "同类",
    "还有",
    "安利",
    "入坑",
    "好看",
    "好玩",
    "哪里买",
    "平台",
    "追番",
    "从哪开始",
    "观看顺序",
]
_TERM_HINTS = [
    "是什么",
    "解释",
    "原理",
    "什么意思",
    "术语",
    "OP",
    "ED",
    "OVA",
    "剧场版",
    "轻改",
    "共通线",
    "个人线",
    "FD",
    "TE",
    "NE",
    "拔作",
    "纯爱",
]
_OVERVIEW_HINTS = ["整理", "总结", "速览", "一页", "设定", "世界观", "角色", "看点", "入坑"]


def _fallback_decide(user_text: str) -> AgentDecision:
    t = (user_text or "").strip()
    needs_recommendations = any(k in t for k in _RESOURCE_HINTS)
    needs_term_explain = any(k in t for k in _TERM_HINTS)
    needs_overview = any(k in t for k in _OVERVIEW_HINTS)

    term = None
    if needs_term_explain:
        term = t[:24] if t else None

    return AgentDecision(
        needs_recommendations=needs_recommendations,
        needs_term_explain=needs_term_explain,
        needs_overview=needs_overview,
        term=term,
    )


def _parse_json_object(text: str) -> dict | None:
    s = (text or "").strip()
    if not s:
        return None

    # 有些模型会额外输出解释文字；我们尽量截取首个 JSON 对象
    m = re.search(r"\{.*\}", s, flags=re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _deepseek_client_or_none() -> DeepSeekClient | None:
    settings = get_settings()
    if not settings.deepseek_api_key:
        return None
    return DeepSeekClient(
        DeepSeekConfig(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
        )
    )


def _llm_decide(user_text: str) -> AgentDecision:
    client = _deepseek_client_or_none()
    if client is None:
        return _fallback_decide(user_text)

    system = (
        "你是一个 ACGN 问题意图路由器，负责判断下一步是否需要：同类推荐、术语解释、或作品速览整理。\n"
        "输出必须是严格 JSON（不要代码块），字段："
        "{\"needs_recommendations\":bool,\"needs_term_explain\":bool,\"needs_overview\":bool,\"term\":string|null}"
    )

    raw = client.chat(system=system, user=f"用户输入：{user_text}\n请输出 JSON：")
    obj = _parse_json_object(raw) or {}

    return AgentDecision(
        needs_recommendations=bool(obj.get("needs_recommendations")),
        needs_term_explain=bool(obj.get("needs_term_explain")),
        needs_overview=bool(obj.get("needs_overview")),
        term=(str(obj.get("term")).strip() if obj.get("term") else None),
    )


def _maybe_explain_term(*, user_text: str, term: str | None) -> str | None:
    client = _deepseek_client_or_none()
    if client is None:
        return None
    prompt = f"用户问题：{user_text}\n要解释的术语/概念（如不确定可从问题中提炼）：{term or ''}"
    try:
        return client.chat(system=TERM_EXPLAINER_SYSTEM, user=prompt)
    except Exception:
        return None


def _resource_expert_pick(*, user_text: str, resources_text: str) -> str | None:
    client = _deepseek_client_or_none()
    if client is None:
        return None
    prompt = f"用户诉求：{user_text}\n\n候选资源：\n{resources_text}\n\n请挑选 2-4 条并说明用途："
    try:
        return client.chat(system=RESOURCE_EXPERT_SYSTEM, user=prompt)
    except Exception:
        return None


def _supportive_reply(*, user_prompt: str, extra: str | None) -> str:
    settings = get_settings()
    client = _deepseek_client_or_none()

    merged_user = user_prompt
    if extra:
        merged_user = f"{user_prompt}\n\n【工具/协作结果】\n{extra}"

    if client is not None:
        try:
            return client.chat(system=SUPPORTIVE_LISTENER_SYSTEM, user=merged_user)
        except Exception:
            pass

    # 无 LLM 时的保底（结构化输出，便于前端直接渲染）
    base = (
        "我可以帮你整理 ACGN 作品信息（默认不剧透）。\n\n"
        "请先告诉我：作品名（或你想查的术语/概念），以及你是否介意轻微剧透。\n\n"
        "你也可以直接按这个格式提问：\n"
        "- 作品：作品名\n"
        "- 想了解：简介/设定/角色/看点/媒介信息/入坑顺序/同类推荐\n"
        "- 剧透：不要/可以\n"
    )

    if extra:
        return base + "\n【补充信息】\n" + str(extra)
    return base


def run_acgn_agent(
    *,
    session: Session,
    user_id: str,
    user_text: str,
    emotion_label: str | None,
) -> str:
    """核心：把“感知→决策→行动→生成回复”落到一次请求中（ACGN 资讯 Agent）。"""

    # 1) 合规硬防线：命中盗版/破解请求则拒绝
    blocked = detect_crisis(user_text)
    if blocked.is_crisis:
        return (
            "我不能提供盗版下载、破解、激活码或绕过付费的内容。\n\n"
            "如果你愿意，我可以帮你：介绍作品信息（不剧透）、解释术语、推荐同类作品，或指引正规购买渠道方向。\n"
            "你想了解哪一部作品？"
        )

    # 2) 感知环境：加载记忆上下文（用户偏好/历史提及作品等）
    memory_ctx = build_user_memory_context(session=session, user_id=user_id)
    if memory_ctx:
        user_prompt = f"【背景信息（系统记忆，供参考）】\n{memory_ctx}\n\n【用户输入】\n{user_text}"
    else:
        user_prompt = user_text

    # 3) 决策：是否需要资源/知识补充/结构化整理
    decision = _llm_decide(user_text)

    # 4) 行动：推荐资源、生成知识补充内容
    extra_blocks: list[str] = []

    if decision.needs_term_explain:
        expl = _maybe_explain_term(user_text=user_text, term=decision.term)
        if expl:
            extra_blocks.append("【知识补充】\n" + expl)

    resources_text = ""
    if decision.needs_recommendations:
        rec = recommend_resources(session=session, user_id=user_id, limit=5, days=14)
        items = rec.get("items") or []
        if items:
            lines: list[str] = []
            for r in items[:5]:
                url = getattr(r, "url", None)
                lines.append(f"- {r.title}" + (f"（{url}）" if url else ""))
            resources_text = "\n".join(lines)
            picked = _resource_expert_pick(user_text=user_text, resources_text=resources_text)
            if picked:
                extra_blocks.append("【资源建议】\n" + picked)
            else:
                extra_blocks.append("【候选资源】\n" + resources_text)

    if decision.needs_overview:
        extra_blocks.append("【可选】如果你愿意，我可以把这部作品信息整理成一页速览（设定/角色/看点/入坑顺序）。")

    # 5) 写入长期记忆（保守提取）
    drafts = extract_memory_drafts(user_text=user_text, emotion_label=emotion_label)
    try:
        upsert_memory_drafts(session=session, user_id=user_id, drafts=drafts)
    except Exception:
        # 记忆写入失败不应影响对话
        pass

    extra = "\n\n".join(extra_blocks) if extra_blocks else None

    # 6) 生成最终回复
    return _supportive_reply(user_prompt=user_prompt, extra=extra)
