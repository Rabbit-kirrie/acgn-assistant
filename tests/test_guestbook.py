from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from acgn_assistant.main import create_app


def _register_and_get_token(client: TestClient, *, email: str, username: str, password: str) -> str:
    r = client.post("/auth/register/request", json={"email": email})
    assert r.status_code == 200
    code = r.json()["debug_code"]
    r = client.post(
        "/auth/register/confirm",
        json={"email": email, "code": code, "username": username, "password": password},
    )
    assert r.status_code == 200
    return r.json()["access_token"]


def test_guestbook_create_list_delete_permissions(tmp_path, monkeypatch):
    db_path = tmp_path / "test_guestbook.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")

    app = create_app()
    with TestClient(app) as client:
        token_a = _register_and_get_token(client, email="a@qq.com", username="a", password="pass1234")
        headers_a = {"Authorization": f"Bearer {token_a}"}

        # user A creates a message
        r = client.post("/guestbook", headers=headers_a, json={"content": "hello from A"})
        assert r.status_code == 200
        msg_a = r.json()
        assert msg_a["content"] == "hello from A"

        # user A sees it in list
        r = client.get("/guestbook", headers=headers_a, params={"limit": 50})
        assert r.status_code == 200
        items = r.json()
        assert any(it["id"] == msg_a["id"] for it in items)

        # user B cannot delete A's message
        token_b = _register_and_get_token(client, email="b@qq.com", username="b", password="pass1234")
        headers_b = {"Authorization": f"Bearer {token_b}"}
        r = client.delete(f"/guestbook/{msg_a['id']}", headers=headers_b)
        assert r.status_code == 403

        # user A can delete own message
        r = client.delete(f"/guestbook/{msg_a['id']}", headers=headers_a)
        assert r.status_code == 200

        # message no longer appears in list
        r = client.get("/guestbook", headers=headers_a, params={"limit": 50})
        assert r.status_code == 200
        items = r.json()
        assert all(it["id"] != msg_a["id"] for it in items)


def test_guestbook_admin_can_delete_others(tmp_path, monkeypatch):
    db_path = tmp_path / "test_guestbook_admin.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    # Bootstrap admin
    monkeypatch.setenv("ADMIN_EMAIL", "admin@qq.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "adminpass123")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")

    app = create_app()
    with TestClient(app) as client:
        token_user = _register_and_get_token(client, email="c@qq.com", username="c", password="pass1234")
        headers_user = {"Authorization": f"Bearer {token_user}"}

        r = client.post("/guestbook", headers=headers_user, json={"content": "hello"})
        assert r.status_code == 200
        msg = r.json()

        # Login as admin
        r = client.post(
            "/auth/login",
            data={"username": "admin@qq.com", "password": "adminpass123"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 200
        admin_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = client.delete(f"/guestbook/{msg['id']}", headers=admin_headers)
        assert r.status_code == 200

        # ensure it's gone
        r = client.get("/guestbook", headers=headers_user, params={"limit": 50})
        assert r.status_code == 200
        assert all(it["id"] != msg["id"] for it in r.json())


def test_guestbook_can_reply_one_level(tmp_path, monkeypatch):
    db_path = tmp_path / "test_guestbook_reply.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")

    app = create_app()
    with TestClient(app) as client:
        token_a = _register_and_get_token(client, email="r1@qq.com", username="r1", password="pass1234")
        token_b = _register_and_get_token(client, email="r2@qq.com", username="r2", password="pass1234")
        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        r = client.post("/guestbook", headers=headers_a, json={"content": "parent"})
        assert r.status_code == 200
        parent = r.json()

        r = client.post(
            "/guestbook",
            headers=headers_b,
            json={"content": "reply", "parent_id": parent["id"]},
        )
        assert r.status_code == 200
        reply = r.json()
        assert reply["parent_id"] == parent["id"]

        r = client.get("/guestbook", headers=headers_a, params={"limit": 50})
        assert r.status_code == 200
        items = r.json()
        parent_item = next((it for it in items if it["id"] == parent["id"]), None)
        assert parent_item is not None
        assert isinstance(parent_item.get("replies"), list)
        assert any(it["id"] == reply["id"] for it in parent_item["replies"])


def test_guestbook_can_reply_to_reply(tmp_path, monkeypatch):
    db_path = tmp_path / "test_guestbook_reply2.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")

    app = create_app()
    with TestClient(app) as client:
        token_a = _register_and_get_token(client, email="rr1@qq.com", username="rr1", password="pass1234")
        token_b = _register_and_get_token(client, email="rr2@qq.com", username="rr2", password="pass1234")
        token_c = _register_and_get_token(client, email="rr3@qq.com", username="rr3", password="pass1234")
        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}
        headers_c = {"Authorization": f"Bearer {token_c}"}

        r = client.post("/guestbook", headers=headers_a, json={"content": "parent"})
        assert r.status_code == 200
        parent = r.json()

        r = client.post(
            "/guestbook",
            headers=headers_b,
            json={"content": "reply1", "parent_id": parent["id"]},
        )
        assert r.status_code == 200
        reply1 = r.json()

        r = client.post(
            "/guestbook",
            headers=headers_c,
            json={"content": "reply2", "parent_id": reply1["id"]},
        )
        assert r.status_code == 200
        reply2 = r.json()

        r = client.get("/guestbook", headers=headers_a, params={"limit": 50})
        assert r.status_code == 200
        items = r.json()

        def find(node, target_id: str):
            if not node:
                return None
            if node.get("id") == target_id:
                return node
            for ch in (node.get("replies") or []):
                got = find(ch, target_id)
                if got:
                    return got
            return None

        top = next((it for it in items if it["id"] == parent["id"]), None)
        assert top is not None
        node_reply1 = find(top, reply1["id"])
        assert node_reply1 is not None
        node_reply2 = find(top, reply2["id"])
        assert node_reply2 is not None
        assert node_reply2["parent_id"] == reply1["id"]


def test_guestbook_reply_inbox(tmp_path, monkeypatch):
    db_path = tmp_path / "test_guestbook_inbox.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")

    app = create_app()
    with TestClient(app) as client:
        token_a = _register_and_get_token(client, email="ia@qq.com", username="ia", password="pass1234")
        token_b = _register_and_get_token(client, email="ib@qq.com", username="ib", password="pass1234")
        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        r = client.post("/guestbook", headers=headers_a, json={"content": "parent from A"})
        assert r.status_code == 200
        parent = r.json()

        # Cursor before the reply is created
        after_pre = datetime.now(timezone.utc).isoformat()

        r = client.post(
            "/guestbook",
            headers=headers_b,
            json={"content": "reply from B", "parent_id": parent["id"]},
        )
        assert r.status_code == 200
        reply = r.json()

        # A should see B's reply in inbox
        r = client.get("/guestbook/inbox", headers=headers_a, params={"after": after_pre, "limit": 50})
        assert r.status_code == 200
        items = r.json()
        assert any(it["id"] == reply["id"] for it in items)

        # B should NOT see replies to A's message
        r = client.get("/guestbook/inbox", headers=headers_b, params={"after": after_pre, "limit": 50})
        assert r.status_code == 200
        assert all(it["id"] != reply["id"] for it in r.json())

        # Self-replies should not be counted
        r = client.post(
            "/guestbook",
            headers=headers_a,
            json={"content": "self reply", "parent_id": parent["id"]},
        )
        assert r.status_code == 200
        self_reply = r.json()
        r = client.get("/guestbook/inbox", headers=headers_a, params={"after": after_pre, "limit": 50})
        assert r.status_code == 200
        assert all(it["id"] != self_reply["id"] for it in r.json())
