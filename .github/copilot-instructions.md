# Copilot 指南（acgn_assistant / ACGN咨询助手后端）

## 快速定位
- 应用入口/装配：`src/acgn_assistant/main.py:create_app()`（默认关闭 `/docs`、`/redoc`、`/openapi.json`）
- 分层：`routers/`(JSON API) + `controllers/`(HTML UI) → `services/`(LLM/记忆/推荐编排) → `models/`(SQLModel) → `db.py`/`db_migrations.py`
- 启动生命周期：`init_db()`（create_all + SQLite 轻量迁移）+ `ensure_admin_user()`（由 `ADMIN_*` env 控制，见 `services/bootstrap.py`）

## UI 与登录态（很容易踩坑）
- 根路径 `/` 渲染 `src/acgn_assistant/views/landing.html`（见 `controllers/ui.py`）；页面会做“登录门禁”：没有 token 直接跳 `/login`
- 前端 JWT 存储 key 统一为：`localStorage['acgn_demo_token']`；landing 页会自动迁移旧 key `token`
- “退出登录”按钮会清理 `acgn_demo_token` / `token` / `is_guest` / 会话选择并跳回 `/login`

## 核心数据流：发消息/生成回复
- 同步：`POST /conversations/{id}/messages`（`routers/conversations.py`）
  1) 合规拦截：`detect_crisis()` 命中“盗版/破解/下载链接”等 → 直接拒答（`services/guardrails.py`）
  2) 轻量记忆：`extract_memory_drafts()` → `upsert_memory_drafts()`（只保存偏好/避雷/关注作品等低敏短文本；`services/memory_writer.py`）
  3) 回复生成：`generate_reply()` 优先 `run_acgn_agent()`，失败回退到 DeepSeek 单轮或规则（`services/chat_engine.py`）
- SSE：`POST /conversations/{id}/messages/stream`
  - 事件：`meta` → 多次 `delta` → `done`（异常：`error`），`text/event-stream` + JSON data（`routers/conversations.py`）
  - DeepSeek 流：`DeepSeekClient.chat_stream()`（`services/deepseek_client.py`）

## 认证/账号约定
- JWT 解析：`routers/deps.py:get_current_user()` / `get_current_admin_user()`
- 普通注册/登录：只允许 `@qq.com`（`routers/auth.py`）；游客：`POST /auth/guest`
- 忘记密码：`/auth/password-reset/*`；dev/test 下 `email_debug_return_code=true` 会在响应返回 `debug_code`（`core/config.py`）

## SQLite 与迁移（兼容旧 app.db）
- `DATABASE_URL` 默认 `sqlite:///./app.db`；测试用临时 sqlite 文件（`tests/test_basic_flow.py`）
- SQLite 引擎强制 `NullPool`（`db.py`）以避免 burst 并发下池耗尽导致 500（不要随意改回默认池）
- 迁移只允许“只增不改”：`ADD COLUMN` / `CREATE INDEX IF NOT EXISTS`（`db_migrations.py`）

## 本地开发（Windows / PowerShell）
- 启动：`$env:ENV='dev'; $env:PYTHONPATH="${PWD}\\src"; Copy-Item .env.example .env -Force; uvicorn acgn_assistant.main:app --reload --port 8000`
- 单测：`pytest -q`（覆盖注册→会话→消息→记忆写入）
- Smoke：先起服务再跑 `scripts/smoke_e2e.py`；LLM 连通性用 `scripts/smoke_llm.py`

## 网络请求关键点
- DeepSeek HTTP 调用显式 `trust_env=False`，避免 Windows 代理环境变量导致 `502`（`services/deepseek_client.py`、smoke 脚本）
