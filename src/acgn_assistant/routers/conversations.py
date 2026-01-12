from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
import json
from time import perf_counter
from typing import Iterator
from sqlmodel import Session, select

from acgn_assistant.db import get_session
from acgn_assistant.models.conversation import (
    Conversation,
    ConversationCreate,
    ConversationUpdate,
    Message,
    MessageCreate,
)
from acgn_assistant.routers.deps import get_current_user
from acgn_assistant.services.chat_engine import generate_reply
from acgn_assistant.services.guardrails import detect_crisis
from acgn_assistant.services.memory_writer import extract_memory_drafts, upsert_memory_drafts
from acgn_assistant.core.time import utcnow

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=Conversation)
def create_conversation(
    payload: ConversationCreate,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    convo = Conversation(user_id=user.id, title=payload.title)
    session.add(convo)
    session.commit()
    session.refresh(convo)
    return convo


@router.get("", response_model=list[Conversation])
def list_conversations(session: Session = Depends(get_session), user=Depends(get_current_user)):
    return list(
        session.exec(
            select(Conversation)
            .where(Conversation.user_id == user.id)
            .where(Conversation.deleted_at.is_(None))
            .order_by(Conversation.created_at.desc())
        )
    )


@router.patch("/{conversation_id}", response_model=Conversation)
def update_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    convo = _get_conversation_or_404(session, user.id, conversation_id)

    if payload.title is not None:
        convo.title = (payload.title or "").strip() or None
        convo.updated_at = utcnow()

    session.add(convo)
    session.commit()
    session.refresh(convo)
    return convo


def _get_conversation_or_404(session: Session, user_id: str, conversation_id: str) -> Conversation:
    convo = session.exec(select(Conversation).where(Conversation.id == conversation_id)).first()
    if not convo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    if convo.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权限访问该会话")
    if getattr(convo, "deleted_at", None) is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return convo


@router.get("/{conversation_id}/messages", response_model=list[Message])
def list_messages(
    conversation_id: str,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    _get_conversation_or_404(session, user.id, conversation_id)
    return list(
        session.exec(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .where(Message.deleted_at.is_(None))
            .order_by(Message.created_at.asc())
        )
    )


@router.delete("/{conversation_id}")
def soft_delete_conversation(
    conversation_id: str,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    convo = _get_conversation_or_404(session, user.id, conversation_id)
    convo.deleted_at = utcnow()
    convo.updated_at = utcnow()
    session.add(convo)
    session.commit()
    return {"deleted": True}


@router.delete("/{conversation_id}/messages/{message_id}")
def soft_delete_message(
    conversation_id: str,
    message_id: str,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    _get_conversation_or_404(session, user.id, conversation_id)
    msg = session.get(Message, message_id)
    if not msg or msg.conversation_id != conversation_id or msg.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="消息不存在")
    msg.deleted_at = utcnow()
    session.add(msg)
    session.commit()
    return {"deleted": True}


@router.post("/{conversation_id}/messages", response_model=list[Message])
def add_message(
    conversation_id: str,
    payload: MessageCreate,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    _get_conversation_or_404(session, user.id, conversation_id)

    crisis = detect_crisis(payload.content)

    # Optional: augment LLM input with web search results, without changing stored user content.
    llm_user_text = payload.content
    try:
        from acgn_assistant.core.config import get_settings
        from acgn_assistant.services.web_search import format_search_context, search_serper

        settings = get_settings()
        want_web = bool(getattr(payload, "web_search", False))
        provider = (getattr(settings, "web_search_provider", "") or "").strip().lower()
        api_key = (getattr(settings, "web_search_api_key", "") or "").strip()
        if want_web and (not crisis.is_crisis) and provider and api_key:
            query = (getattr(payload, "web_search_query", None) or payload.content or "").strip()
            if provider == "serper":
                results = search_serper(
                    api_key=api_key,
                    query=query,
                    limit=5,
                    timeout_seconds=float(getattr(settings, "web_search_timeout_seconds", 12.0) or 12.0),
                )
                ctx = format_search_context(results)
                if ctx:
                    llm_user_text = f"{payload.content}\n\n{ctx}"
    except Exception:
        # Web search is best-effort; never break chat.
        pass

    user_msg = Message(
        conversation_id=conversation_id,
        role="user",
        content=payload.content,
        is_crisis=crisis.is_crisis,
    )
    session.add(user_msg)

    # 轻量写入长期记忆（保守抽取）；即使后续对话生成失败，也尽量不丢信息
    try:
        drafts = extract_memory_drafts(user_text=payload.content, emotion_label=None)
        upsert_memory_drafts(session=session, user_id=user.id, drafts=drafts)
    except Exception:
        # 记忆写入失败不影响主流程
        pass

    assistant_text = generate_reply(
        session=session,
        user_id=user.id,
        user_text=llm_user_text,
        emotion_label=None,
        is_crisis=crisis.is_crisis,
        deep_think=bool(getattr(payload, "deep_think", False)),
    )
    assistant_msg = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=assistant_text,
        is_crisis=crisis.is_crisis,
    )
    session.add(assistant_msg)

    session.commit()
    session.refresh(user_msg)
    session.refresh(assistant_msg)

    return [user_msg, assistant_msg]


@router.post("/{conversation_id}/messages/stream")
def add_message_stream(
    conversation_id: str,
    payload: MessageCreate,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    """SSE 流式返回 assistant 的文本增量。

    - 先落库 user message + 情绪记录 + 轻量记忆
    - 再边生成边推送（text/event-stream）
    - 结束后落库 assistant message
    """

    _get_conversation_or_404(session, user.id, conversation_id)

    crisis = detect_crisis(payload.content)

    # Optional: augment LLM input with web search results, without changing stored user content.
    llm_user_text = payload.content
    web_used = 0

    user_msg = Message(
        conversation_id=conversation_id,
        role="user",
        content=payload.content,
        is_crisis=crisis.is_crisis,
    )
    session.add(user_msg)

    try:
        drafts = extract_memory_drafts(user_text=payload.content, emotion_label=None)
        upsert_memory_drafts(session=session, user_id=user.id, drafts=drafts)
    except Exception:
        pass

    session.commit()
    session.refresh(user_msg)

    from acgn_assistant.core.config import get_settings
    from acgn_assistant.services.agent_prompts import SUPPORTIVE_LISTENER_SYSTEM
    from acgn_assistant.services.deepseek_client import DeepSeekClient, DeepSeekConfig

    settings = get_settings()
    client: DeepSeekClient | None = None
    deep_think = bool(getattr(payload, "deep_think", False))
    want_web = bool(getattr(payload, "web_search", False))
    provider = (getattr(settings, "web_search_provider", "") or "").strip().lower()
    web_configured = bool(provider and (getattr(settings, "web_search_api_key", "") or "").strip())

    if want_web and web_configured and (not crisis.is_crisis):
        try:
            from acgn_assistant.services.web_search import format_search_context, search_serper

            query = (getattr(payload, "web_search_query", None) or payload.content or "").strip()
            if provider == "serper":
                results = search_serper(
                    api_key=(getattr(settings, "web_search_api_key", "") or "").strip(),
                    query=query,
                    limit=5,
                    timeout_seconds=float(getattr(settings, "web_search_timeout_seconds", 12.0) or 12.0),
                )
                web_used = len(results)
                ctx = format_search_context(results)
                if ctx:
                    llm_user_text = f"{payload.content}\n\n{ctx}"
        except Exception:
            web_used = 0
    used_model = ""
    if settings.deepseek_api_key:
        model = settings.deepseek_deep_think_model if deep_think else settings.deepseek_model
        used_model = model
        client = DeepSeekClient(
            DeepSeekConfig(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                model=model,
            )
        )
    else:
        used_model = "fallback"

    def _sse_event(event: str, data_obj) -> str:
        return f"event: {event}\n" + f"data: {json.dumps(data_obj, ensure_ascii=False)}\n\n"

    def gen() -> Iterator[bytes]:
        assistant_accum: list[str] = []
        t0 = perf_counter()
        try:
            yield _sse_event(
                "meta",
                {
                    "conversation_id": conversation_id,
                    "user_message_id": user_msg.id,
                    "deep_think": deep_think,
                    "model": used_model,
                    "web_search": {
                        "enabled": want_web,
                        "configured": web_configured,
                        "results": web_used,
                        "provider": provider,
                    },
                },
            ).encode("utf-8")

            if client is not None:
                system_prompt = SUPPORTIVE_LISTENER_SYSTEM
                if deep_think:
                    system_prompt += (
                        "\n\n当开启‘深度思考’时：请在回复末尾追加一个小节，标题为【思考摘要】。"
                        "\n要求：最多 8 条要点；以‘可公开、可验证’的理由链形式表达（例如依据/对照/排除/权衡），"
                        "可以列出关键步骤或决策点；只写高层依据/假设/不确定点；"
                        "不要输出详细推理链、逐步内心独白、隐藏过程或逐 token 思维；用中文，简洁但信息密度高。"
                    )

                for chunk in client.chat_stream(system=system_prompt, user=llm_user_text):
                    assistant_accum.append(chunk)
                    yield _sse_event("delta", {"content": chunk}).encode("utf-8")
            else:
                # Fallback: DeepSeek not configured. Generate a normal reply (may use orchestrator
                # or rule-based fallback) and stream it as one delta event.
                assistant_text = generate_reply(
                    session=session,
                    user_id=user.id,
                    user_text=llm_user_text,
                    emotion_label=None,
                    is_crisis=crisis.is_crisis,
                    deep_think=bool(getattr(payload, "deep_think", False)),
                )
                assistant_accum.append(assistant_text)
                yield _sse_event("delta", {"content": assistant_text}).encode("utf-8")

            assistant_text = "".join(assistant_accum).strip()
            assistant_msg = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=assistant_text,
                is_crisis=crisis.is_crisis,
            )
            session.add(assistant_msg)
            session.commit()
            session.refresh(assistant_msg)

            yield _sse_event(
                "done",
                {
                    "assistant_message_id": assistant_msg.id,
                    "assistant_content": assistant_text,
                    "duration_ms": int((perf_counter() - t0) * 1000),
                    "deep_think": deep_think,
                    "model": used_model,
                },
            ).encode("utf-8")
        except Exception as e:
            yield _sse_event("error", {"detail": str(e)}).encode("utf-8")

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
