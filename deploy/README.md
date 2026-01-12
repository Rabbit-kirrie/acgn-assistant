# 国内可访问部署（VPS + Docker Compose）

目标：让国内用户不需要 VPN 也能稳定访问。

## 推荐方案（最稳）

- 服务器：腾讯云/阿里云/华为云等「中国大陆地域」云服务器
- 域名：你自己的域名 + ICP 备案（大陆服务器基本都需要）
- 反代与 HTTPS：Caddy 自动签证
- 数据库：同机 Postgres（本仓库已准备好 compose）

> 不做备案也能部署（比如香港/新加坡服务器），但“国内稳定性”就没法保证到你要的程度。

## 服务器准备

1) 放行安全组端口：`80`、`443`、`22`（SSH）

2) 安装 Docker + Compose（以 Ubuntu 为例）：

- `curl -fsSL https://get.docker.com | sh`
- `sudo usermod -aG docker $USER`
- 重新登录 SSH

## 部署步骤

1) 把仓库拉到服务器：

- `git clone <your_repo_url>`
- `cd <repo>`

2) 进入部署目录：

- `cd deploy`

3) 修改两个地方：

- `deploy/Caddyfile`：把 `your-domain.com` 改成你的域名并取消注释
- `deploy/docker-compose.prod.yml`：把 `JWT_SECRET`、Postgres 密码等 `change-me` 改掉

4) 配置环境变量（可选项按需填）：

在服务器上创建 `deploy/.env`（参考项目根目录 `.env.example`），至少建议设置：

- `DEEPSEEK_API_KEY=...`
- SMTP 相关（如果你要启用忘记密码）
- `ADMIN_EMAIL/ADMIN_USERNAME/ADMIN_PASSWORD`（首次启动自动创建管理员）

5) 启动：

- `docker compose -f docker-compose.prod.yml --env-file .env up -d --build`

6) 访问：

- 先访问你的域名：`https://your-domain.com/`

## 常见问题

- 证书申请失败：确认域名已解析到这台服务器公网 IP，并且 80/443 未被拦截。
- 备案问题：大陆服务器通常必须备案；备案没下来前可以先用临时测试域名/海外服务器演示。
- 数据库迁移：首次启动会自动建表；后续只做“只增不改”的轻量迁移。
