from __future__ import annotations

import argparse
import sys
import uuid

import httpx


def _run(*, base_url: str, message: str, timeout: float) -> int:
    base_url = base_url.rstrip("/")

    # DeepSeek/LLM 路径可能会较慢，这里给一个更宽松的默认超时
    with httpx.Client(trust_env=False, timeout=timeout) as client:
        health = client.get(f"{base_url}/system/health")
        health.raise_for_status()

        suffix = uuid.uuid4().hex[:8]
        email = f"smoke_{suffix}@qq.com"
        username = f"smoke_{suffix}"
        password = "pass1234"

        req = client.post(f"{base_url}/auth/register/request", json={"email": email})
        req.raise_for_status()
        req_json = req.json()
        code = (req_json.get("debug_code") or "").strip()
        if not code:
            print("Registration code was sent to email.")
            code = input("Enter the 6-digit code from your inbox: ").strip()

        reg = client.post(
            f"{base_url}/auth/register/confirm",
            json={"email": email, "code": code, "username": username, "password": password},
        )
        reg.raise_for_status()
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        convo = client.post(
            f"{base_url}/conversations",
            headers=headers,
            json={"title": f"smoke-{suffix}"},
        )
        convo.raise_for_status()
        convo_id = convo.json()["id"]

        msgs = client.post(
            f"{base_url}/conversations/{convo_id}/messages",
            headers=headers,
            json={"content": message},
        )
        msgs.raise_for_status()
        msgs_json = msgs.json()

        memory = client.get(f"{base_url}/memory?limit=10", headers=headers)
        memory.raise_for_status()
        memory_json = memory.json()

        titles = []
        try:
            titles = [x.get("title") for x in memory_json]
        except Exception:
            titles = []

        print("base_url=", base_url)
        print("email=", email)
        print("messages=", len(msgs_json) if isinstance(msgs_json, list) else None)
        print("memory_count=", len(memory_json))
        print("memory_titles=", titles)

        if len(memory_json) < 1:
            print("FAIL: expected at least 1 auto memory item")
            return 2

    print("OK")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="End-to-end smoke test: register -> conversation -> message -> verify /memory auto-write."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument(
        "--message",
        default="我喜欢热血少年漫，想要类似推荐",
        help="Message sent to /conversations/{id}/messages",
    )
    args = parser.parse_args(argv)

    try:
        return _run(base_url=args.base_url, message=args.message, timeout=args.timeout)
    except httpx.HTTPError as e:
        print("HTTP ERROR:", e)
        return 1
    except Exception as e:
        print("ERROR:", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
