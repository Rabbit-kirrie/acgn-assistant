from fastapi.testclient import TestClient
import pytest

from acgn_assistant.main import create_app


def test_register_login_conversation_flow(tmp_path, monkeypatch):
    # 使用临时 sqlite 文件
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")

    app = create_app()
    with TestClient(app) as client:
        r = client.post("/auth/register/request", json={"email": "a@qq.com"})
        assert r.status_code == 200
        payload = r.json()
        assert "debug_code" in payload
        code = payload["debug_code"]

        r = client.post(
            "/auth/register/confirm",
            json={"email": "a@qq.com", "code": code, "username": "alice", "password": "pass1234"},
        )
        assert r.status_code == 200
        token = r.json()["access_token"]

        # Password reset flow (request code -> confirm -> login with new password)
        r = client.post("/auth/password-reset/request", json={"email": "a@qq.com"})
        assert r.status_code == 200
        payload = r.json()
        assert "debug_code" in payload
        code = payload["debug_code"]

        r = client.post(
            "/auth/password-reset/confirm",
            json={"email": "a@qq.com", "code": code, "new_password": "pass5678"},
        )
        assert r.status_code == 200

        r = client.post(
            "/auth/login",
            data={"username": "a@qq.com", "password": "pass5678"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 200

        headers = {"Authorization": f"Bearer {token}"}

        r = client.put("/users/me", json={"username": "alice2"}, headers=headers)
        assert r.status_code == 200
        assert r.json()["username"] == "alice2"

        r = client.post("/conversations", json={"title": "test"}, headers=headers)
        assert r.status_code == 200
        convo_id = r.json()["id"]

        r = client.post(
            f"/conversations/{convo_id}/messages",
            json={"content": "我喜欢热血少年漫，想要类似推荐"},
            headers=headers,
        )
        assert r.status_code == 200
        msgs = r.json()
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"

        r = client.get("/memory?limit=10", headers=headers)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        assert len(items) >= 1


def test_admin_can_view_other_users_conversations(tmp_path, monkeypatch):
    db_path = tmp_path / "test_admin.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    # Create an admin user at startup.
    monkeypatch.setenv("ADMIN_EMAIL", "admin@qq.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "adminpass123")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")

    app = create_app()
    with TestClient(app) as client:
        # Create a normal user and a conversation with messages.
        r = client.post("/auth/register/request", json={"email": "u1@qq.com"})
        code = r.json()["debug_code"]
        r = client.post(
            "/auth/register/confirm",
            json={"email": "u1@qq.com", "code": code, "username": "u1", "password": "pass1234"},
        )
        user_token = r.json()["access_token"]
        user_headers = {"Authorization": f"Bearer {user_token}"}

        r = client.post("/conversations", json={"title": "hello"}, headers=user_headers)
        convo_id = r.json()["id"]
        r = client.post(
            f"/conversations/{convo_id}/messages",
            json={"content": "test message"},
            headers=user_headers,
        )
        assert r.status_code == 200

        # Login as admin.
        r = client.post(
            "/auth/login",
            data={"username": "admin@qq.com", "password": "adminpass123"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 200
        admin_token = r.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # Create another user and promote to admin.
        r = client.post("/auth/register/request", json={"email": "u2@qq.com"})
        code = r.json()["debug_code"]
        r = client.post(
            "/auth/register/confirm",
            json={"email": "u2@qq.com", "code": code, "username": "u2", "password": "pass1234"},
        )
        assert r.status_code == 200

        r = client.get("/admin/users", headers=admin_headers)
        assert r.status_code == 200
        users = r.json()
        admin_user = next((u for u in users if u["email"] == "admin@qq.com"), None)
        u2 = next((u for u in users if u["email"] == "u2@qq.com"), None)
        assert admin_user is not None
        assert u2 is not None

        r = client.put(
            f"/admin/users/{u2['id']}",
            json={"is_admin": True},
            headers=admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["is_admin"] is True

        # Login as the second admin.
        r = client.post(
            "/auth/login",
            data={"username": "u2@qq.com", "password": "pass1234"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 200
        u2_admin_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        # A non-super admin cannot promote/demote admins.
        r = client.post("/auth/register/request", json={"email": "u3@qq.com"})
        code = r.json()["debug_code"]
        r = client.post(
            "/auth/register/confirm",
            json={"email": "u3@qq.com", "code": code, "username": "u3", "password": "pass1234"},
        )
        assert r.status_code == 200

        r = client.get("/admin/users", headers=admin_headers)
        assert r.status_code == 200
        users = r.json()
        u3 = next((u for u in users if u["email"] == "u3@qq.com"), None)
        assert u3 is not None

        r = client.put(
            f"/admin/users/{u3['id']}",
            json={"is_admin": True},
            headers=u2_admin_headers,
        )
        assert r.status_code == 403

        # Super admin can promote.
        r = client.put(
            f"/admin/users/{u3['id']}",
            json={"is_admin": True},
            headers=admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["is_admin"] is True

        r = client.get("/admin/conversations", headers=admin_headers)
        assert r.status_code == 200
        convos = r.json()
        assert any(c["id"] == convo_id for c in convos)

        r = client.get(f"/admin/conversations/{convo_id}/messages", headers=admin_headers)
        assert r.status_code == 200
        msgs = r.json()
        assert len(msgs) >= 2

        # Admin can disable a user account.
        r = client.get("/admin/users", headers=admin_headers)
        assert r.status_code == 200
        users = r.json()
        u1 = next((u for u in users if u["email"] == "u1@qq.com"), None)
        assert u1 is not None
        u1_id = u1["id"]

        r = client.put(
            f"/admin/users/{u1_id}",
            json={"is_active": False},
            headers=admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["is_active"] is False

        # The bootstrap admin cannot be disabled or demoted by another admin.
        r = client.put(
            f"/admin/users/{admin_user['id']}",
            json={"is_active": False},
            headers=u2_admin_headers,
        )
        assert r.status_code == 400

        r = client.put(
            f"/admin/users/{admin_user['id']}",
            json={"is_admin": False},
            headers=u2_admin_headers,
        )
        assert r.status_code == 403

        # Super admin can view audit logs and should see the promotion.
        r = client.get("/admin/audit-logs", headers=admin_headers)
        assert r.status_code == 200
        logs = r.json()
        assert any((it.get("action") == "admin_user.promote_admin" and it.get("target_email") == "u3@qq.com") for it in logs)

        # Only super admin can delete an account.
        r = client.delete(f"/admin/users/{u1_id}", headers=u2_admin_headers)
        assert r.status_code == 403

        r = client.delete(f"/admin/users/{u1_id}", headers=admin_headers)
        assert r.status_code == 204

        # Disabled user's existing token is rejected.
        r = client.get("/users/me", headers=user_headers)
        assert r.status_code == 401

        # Disabled user cannot login again.
        r = client.post(
            "/auth/login",
            data={"username": "u1@qq.com", "password": "pass1234"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code in (401, 403)


def test_config_requires_smtp_when_debug_disabled(tmp_path, monkeypatch):
    db_path = tmp_path / "test_cfg.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")

    # Force disable debug return code and clear SMTP via env overrides.
    monkeypatch.setenv("EMAIL_DEBUG_RETURN_CODE", "false")
    monkeypatch.setenv("SMTP_HOST", "")
    monkeypatch.setenv("SMTP_USERNAME", "")
    monkeypatch.setenv("SMTP_PASSWORD", "")
    monkeypatch.setenv("SMTP_FROM", "")

    with pytest.raises(RuntimeError):
        create_app()
