# ACGN咨询助手（后端）

一个用于“咨询 ACGN 作品信息/术语解释/同类推荐”的后端 Demo：用户/对话/（可选）资源推荐/记忆（用户偏好）。

> 说明：本项目不提供盗版下载、破解、激活码或绕过付费的内容；可提示正规购买渠道方向。

## 运行（pip）

### 一键启动（推荐）

已提供一键启动脚本（会自动设置 `ENV=dev`、`PYTHONPATH=src` 并启动 uvicorn）：

```powershell
cd E:\Demo3Test
powershell -ExecutionPolicy Bypass -File .\scripts\start_dev.ps1
```

如果 8000 端口经常被占用，可以用“自动释放端口”（会尝试停止占用该端口的进程）：

```powershell
cd E:\Demo3Test
powershell -ExecutionPolicy Bypass -File .\scripts\start_dev.ps1 -KillPortUsers
```

或者换个端口：

```powershell
cd E:\Demo3Test
powershell -ExecutionPolicy Bypass -File .\scripts\start_dev.ps1 -Port 8010
```

（如果你已经在 PowerShell 里打开了项目根目录，也可以直接运行：`./scripts/start_dev.ps1`）

```powershell
cd E:\Demo3Test
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:ENV="dev"
$env:PYTHONPATH="${PWD}\\src"
Copy-Item .env.example .env -Force
uvicorn acgn_assistant.main:app --reload --port 8000
```

提示：默认关闭 FastAPI 内置文档（`/docs`、`/redoc`、`/openapi.json`）。

前端 HTML（联调页）：`http://127.0.0.1:8000/`

独立认证页面：
- 登录：`http://127.0.0.1:8000/login`
- 注册：`http://127.0.0.1:8000/register`
- 忘记密码（邮箱验证码重置）：`http://127.0.0.1:8000/forgot`

### 忘记密码（SMTP 配置）

忘记密码会向 QQ 邮箱发送 6 位验证码；请在 `.env` 中配置 SMTP：

```dotenv
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM=ACGN咨询助手 <no-reply@your-domain>
SMTP_USE_TLS=true
SMTP_USE_SSL=false
```

说明：在 `ENV!=prod` 的环境下，为便于本地联调，接口响应会额外返回 `debug_code`（生产环境请务必关闭/不要使用）。

## 端到端 Smoke（推荐）

先按上面的方式启动服务（建议 `--reload`），然后在另一个终端运行：

```powershell
cd E:\Demo3Test
$env:PYTHONPATH="${PWD}\\src"
./.venv/Scripts/python.exe scripts/smoke_e2e.py
```

如果出现超时（LLM + 记忆写入可能更慢），可提高超时时间：

```powershell
./.venv/Scripts/python.exe scripts/smoke_e2e.py --timeout 90
```

脚本会执行：注册 → 新建会话 → 发消息 → 拉取 `/memory`，并验证是否至少写入 1 条自动记忆。

说明：脚本内部默认 `trust_env=False`，避免 Windows 上环境代理变量导致 `502 Bad Gateway`。

### 验证 DeepSeek/LLM 是否生效

如果你想确认回复确实走了 DeepSeek（而不是规则回退），可以运行：

```powershell
cd E:\Demo3Test
./.venv/Scripts/python.exe scripts/smoke_llm.py
```

它会要求助手在回复中原样回显一个随机标记；若标记出现，通常意味着 LLM 路径已生效。

## Windows 终端中文（推荐 pwsh）

如果你用 PowerShell 5.1 跑 `Invoke-RestMethod`，有时会出现中文请求/输出乱码（例如 `????`）。
推荐改用 PowerShell 7（`pwsh`）并设置 UTF-8：

```powershell
# 在 pwsh 里执行一次（当前会话生效）
$OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::InputEncoding  = [System.Text.UTF8Encoding]::new()
```

然后再运行你的 API 调用命令（例如 `Invoke-RestMethod ...`），中文内容通常就能正常显示。

## 运行（uv，可选）

如果你想用 uv 管理依赖：

```powershell
cd E:\Demo3Test
pip install uv
uv venv
.\.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt
$env:PYTHONPATH="${PWD}\\src"
Copy-Item .env.example .env -Force
uvicorn acgn_assistant.main:app --reload --port 8000
```

## 模块

- 用户管理：注册/登录、个人信息
- 对话管理：创建会话、消息、历史记录（含 SSE 流式）
- 记忆：自动抽取偏好/避雷/关注作品等（低敏）并可查询
- 资源库与推荐：资源条目 + 标签 + 行为事件（view/saved/dismissed）+ 推荐
- 周报/月报：基于对话与记忆的占位报告

## 系统功能

- 健康检查：`GET /system/health`
- 配置概览（脱敏）：`GET /system/info`
- 管理员初始化：设置 `.env` 中 `ADMIN_EMAIL/ADMIN_PASSWORD/ADMIN_USERNAME`，服务启动时自动创建/提升管理员

## 管理端（管理员权限）

- 用户管理 CRUD：`/admin/users`

## 技术架构（分层）

- Model：`src/acgn_assistant/models`（SQLModel + SQLite）
- View：`src/acgn_assistant/views`（HTML）
- Controller：`src/acgn_assistant/controllers`（FastAPI 路由）
- 大模型：DeepSeek（OpenAI 兼容 HTTP 调用）
- 提示词工程：提示词硬编码在 `src/acgn_assistant/services/chat_engine.py`

## Docker 部署

```powershell
cd E:\Demo3Test
docker compose up --build
```

然后访问：
- `http://127.0.0.1:8000/`（HTML联调页）
- 内置 API 文档默认关闭（`/docs`、`/redoc`、`/openapi.json`）

## 国内可访问部署（不依赖 Vercel）

如果你的目标是“国内用户普遍可用（不需要 VPN）”，更推荐部署到国内云服务器，并配合自定义域名 + HTTPS。

仓库已提供一套生产 Compose（Postgres + Caddy HTTPS 反代），见：

- deploy/README.md

核心要点：

- 大陆地域服务器通常需要域名备案（ICP）。
- 不做备案可以选香港/新加坡服务器，但国内稳定性无法保证。

## Vercel 公网部署（Python Functions）

本项目已补齐 Vercel 入口与路由：
- `api/index.py`：Vercel Function 入口（导出 ASGI `app`）
- `vercel.json`：将所有路径转发到该函数（支持 `/`、`/login`、`/static/*`、API 路由等）

### 重要注意：数据库

Vercel 的函数运行环境通常只有 `/tmp` 可写，且是“临时的”（实例重启会丢数据）。

- 推荐：在 Vercel 环境变量里配置 `DATABASE_URL` 指向公网数据库（例如 Postgres）。
- 不配置也能跑：若你不设置 `DATABASE_URL`，部署到 Vercel 时会自动使用 `sqlite:////tmp/app.db`（数据不持久，仅适合演示）。

### 部署步骤（最少配置）

1) 把仓库推到 GitHub

2) 在 Vercel 导入该仓库并部署

3) 在 Vercel Project Settings → Environment Variables 配置（至少）：
- `ENV=prod`
- `JWT_SECRET=...`（请用随机强密码；否则在 `ENV!=dev` 会启动失败）

可选：
- `DEEPSEEK_API_KEY=...`（不配会走回退路径/规则）
- `WEB_SEARCH_PROVIDER=serper`、`WEB_SEARCH_API_KEY=...`（启用“联网搜索”开关）
- `DATABASE_URL=...`（强烈建议）

### 本地验证（模拟 Vercel 行为，可选）

你可以在本机临时模拟一下：

```powershell
$env:VERCEL='1'
$env:ENV='prod'
$env:JWT_SECRET='your-strong-secret'
uvicorn api.index:app --port 8000
```

然后访问：`http://127.0.0.1:8000/`

## 下一步可迭代

- 更丰富的 ACGN 推荐策略（偏好 + 行为事件 + 资源库扩展）
- 增加资源采集/同步（例如官方资讯源、榜单、作品数据库）
- 更完善的隐私合规：数据最小化、加密、审计、保留期

## SQLite 轻量迁移（已启用）

项目启动时会在 `init_db()` 后对 SQLite 执行轻量迁移：
- 自动为旧版 `app.db` 补齐新增列（例如 `deleted_at/updated_at`）
- 自动创建软删除相关索引（`CREATE INDEX IF NOT EXISTS`）

说明：这是“只增不改”的迁移（仅 `ADD COLUMN`），用于保持历史数据库可继续运行。

### 历史表结构兼容说明

如果你复用旧的 `app.db`（例如来自早期“心灵伴侣/心理健康”Demo），其中可能存在一些当前业务不再使用、但仍为 `NOT NULL` 的遗留列。
为保证注册/写档案等流程在老库上仍能正常插入数据，本项目会在模型层保留这些列并提供默认值。

例如：`userprofile.goals_json`、`userprofile.health_summary`。

如果你不需要兼容旧库，建议直接删除本地的 `app.db` 让应用自动创建全新数据库。
