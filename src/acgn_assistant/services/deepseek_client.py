from __future__ import annotations

from dataclasses import dataclass
import json
from collections.abc import Iterator

import httpx


@dataclass(frozen=True)
class DeepSeekConfig:
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    timeout_seconds: float = 30.0


class DeepSeekClient:
    """DeepSeek（OpenAI 兼容）Chat Completions 简易客户端。

    说明：不引入额外 SDK，直接用 HTTP 调用，便于 Docker/部署。
    """

    def __init__(self, config: DeepSeekConfig) -> None:
        self._config = config

    def is_configured(self) -> bool:
        return bool(self._config.api_key)

    def chat(self, *, system: str, user: str) -> str:
        if not self.is_configured():
            raise RuntimeError("DeepSeek 未配置：请设置 DEEPSEEK_API_KEY")

        url = self._config.base_url.rstrip("/") + "/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self._config.api_key}"}
        payload = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.7,
        }

        # 默认不读取系统代理环境变量，避免本机代理导致 502 等问题
        with httpx.Client(timeout=self._config.timeout_seconds, trust_env=False) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        # OpenAI 兼容格式：choices[0].message.content
        return data["choices"][0]["message"]["content"]

    def chat_stream(self, *, system: str, user: str) -> Iterator[str]:
        """流式聊天：返回一个迭代器，逐段产出 assistant 的内容增量。"""

        if not self.is_configured():
            raise RuntimeError("DeepSeek 未配置：请设置 DEEPSEEK_API_KEY")

        url = self._config.base_url.rstrip("/") + "/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self._config.api_key}"}
        payload = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.7,
            "stream": True,
        }

        # OpenAI 兼容 SSE：逐行 data: {...}，以 data: [DONE] 结束
        with httpx.Client(timeout=self._config.timeout_seconds, trust_env=False) as client:
            with client.stream("POST", url, json=payload, headers=headers) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    if isinstance(line, bytes):
                        line = line.decode("utf-8", errors="ignore")
                    s = line.strip()
                    if not s:
                        continue
                    if s.startswith(":"):
                        # 注释/心跳
                        continue
                    if not s.startswith("data:"):
                        continue
                    data = s[len("data:") :].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except Exception:
                        continue

                    try:
                        choice0 = (obj.get("choices") or [None])[0] or {}
                        delta = choice0.get("delta") or {}
                        chunk = delta.get("content")
                        if chunk:
                            yield str(chunk)
                            continue
                        # 兼容少数实现：直接在 message.content 里
                        msg = choice0.get("message") or {}
                        chunk2 = msg.get("content")
                        if chunk2:
                            yield str(chunk2)
                    except Exception:
                        continue
