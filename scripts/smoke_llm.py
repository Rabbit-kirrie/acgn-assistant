from __future__ import annotations

import argparse
import sys
import uuid

import httpx


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Smoke test for verifying the assistant is using an LLM path (DeepSeek). "
            "It sends a message that asks the assistant to echo a unique marker; "
            "rule-based fallbacks typically won't follow this instruction."
        )
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=45.0)
    args = parser.parse_args(argv)

    base = args.base_url.rstrip("/")
    marker = f"<LLMTEST:{uuid.uuid4().hex[:10]}>"

    message = (
        "做一个连通性测试：\n"
        "1) 请用中文只回答一句话：‘已收到’。\n"
        "2) 并在这句话末尾原样追加这个标记（不要改动任何字符）："
        f"{marker}"
    )

    with httpx.Client(trust_env=False, timeout=args.timeout) as client:
        health = client.get(f"{base}/system/health")
        health.raise_for_status()

        suffix = uuid.uuid4().hex[:8]
        email = f"llm_{suffix}@qq.com"

        req = client.post(f"{base}/auth/register/request", json={"email": email})
        req.raise_for_status()
        req_json = req.json()
        code = (req_json.get("debug_code") or "").strip()
        if not code:
            print("Registration code was sent to email:", email)
            code = input("Enter the 6-digit code from your inbox: ").strip()

        reg = client.post(
            f"{base}/auth/register/confirm",
            json={"email": email, "code": code, "username": f"llm_{suffix}", "password": "pass1234"},
        )
        reg.raise_for_status()
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        convo = client.post(f"{base}/conversations", headers=headers, json={"title": f"llm-{suffix}"})
        convo.raise_for_status()
        convo_id = convo.json()["id"]

        msgs = client.post(
            f"{base}/conversations/{convo_id}/messages",
            headers=headers,
            json={"content": message},
        )
        msgs.raise_for_status()
        msgs_json = msgs.json()

        assistant_text = ""
        try:
            assistant_text = msgs_json[1].get("content") or ""
        except Exception:
            assistant_text = ""

    print("base_url=", base)
    print("marker=", marker)
    print("assistant_reply=", assistant_text)

    if marker in assistant_text:
        print("OK: marker echoed; likely LLM path")
        return 0

    print("FAIL: marker not found; likely fallback or instruction ignored")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
