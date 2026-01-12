from __future__ import annotations

from sqlmodel import Session

from acgn_assistant.core.config import get_settings
from acgn_assistant.services.deepseek_client import DeepSeekClient, DeepSeekConfig
from acgn_assistant.services.agent_orchestrator import run_acgn_agent
from acgn_assistant.services.memory_context import build_user_memory_context


def generate_reply(
    *,
    session: Session,
    user_id: str,
    user_text: str,
    emotion_label: str | None,
    is_crisis: bool,
    deep_think: bool = False,
) -> str:
    # 说明：对话引擎为“ACGN 咨询 Agent”。
    # 若编排层失败，回退到单轮 LLM/规则逻辑，避免接口中断。

    if is_crisis:
        return (
            "我不能提供盗版下载、破解、激活码或绕过付费的内容。\n\n"
            "如果你愿意，我可以改为帮你：\n"
            "- 介绍作品剧情/角色（不剧透）\n"
            "- 推荐同类型作品\n"
            "- 提供正规购买/游玩渠道的方向（如 Steam / DLsite 等）\n\n"
            "你想了解哪一部作品？"
        )

    try:
        return run_acgn_agent(
            session=session,
            user_id=user_id,
            user_text=user_text,
            emotion_label=emotion_label,
        )
    except Exception:
        # 编排失败则回退
        pass

    settings = get_settings()

    memory_ctx = build_user_memory_context(session=session, user_id=user_id)
    if memory_ctx:
        user_prompt = f"【背景信息（系统记忆，供参考）】\n{memory_ctx}\n\n【用户输入】\n{user_text}"
    else:
        user_prompt = user_text

    # 提示词工程：按需求直接硬编码在 Python 文件中
    system_prompt = (
        "你是一个 ACGN 咨询助手（中文输出）。你擅长把作品信息整理成结构化条目：简介、世界观/设定、主要角色/阵容、"
        "看点与风格、媒介信息（动画/漫画/轻小说/游戏等）、衍生与入坑顺序，并可给出同类推荐。\n"
        "边界与合规：不提供盗版下载、破解、激活码或绕过付费的内容。\n"
        "默认不剧透；如用户明确要求剧透，先给‘剧透警告’再展开。\n"
        "如果用户问题缺少关键上下文（例如作品名歧义/媒介/平台/是否要剧透），先问 1-2 个澄清问题。"
    )

    if deep_think:
        # UX: provide a slightly more detailed public rationale without exposing chain-of-thought.
        system_prompt += (
            "\n\n当开启‘深度思考’时：请在回复末尾追加一个小节，标题为【思考摘要】。"
            "\n要求：最多 8 条要点；以‘可公开、可验证’的理由链形式表达（例如依据/对照/排除/权衡），"
            "可以列出关键步骤或决策点；只写高层依据/假设/不确定点；"
            "不要输出详细推理链、逐步内心独白、隐藏过程或逐 token 思维；用中文，简洁但信息密度高。"
        )

    if settings.deepseek_api_key:
        try:
            model = settings.deepseek_deep_think_model if deep_think else settings.deepseek_model
            client = DeepSeekClient(
                DeepSeekConfig(
                    api_key=settings.deepseek_api_key,
                    base_url=settings.deepseek_base_url,
                    model=model,
                )
            )
            return client.chat(system=system_prompt, user=user_prompt)
        except Exception:
            # 失败时回退到规则引擎（避免对话中断）
            pass

    return (
        "我可以帮你整理 ACGN 作品信息与同类推荐（默认不剧透）。\n\n"
        "请告诉我：\n"
        "1) 作品名（或你想了解的术语/概念）\n"
        "2) 你想重点了解：简介/设定/角色/看点/媒介信息/入坑顺序/同类推荐\n"
        "3) 是否接受轻微剧透（不要/可以）\n"
    )
