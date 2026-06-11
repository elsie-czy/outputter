# 云端部署手册（v1.0）

本文档用于把 `personal-supertool` 部署到一台云服务器上，以便远程访问 Web、并按需执行主流程/生图 worker/初筛抓取。

约定：
- 操作系统：Ubuntu 22.04（其他 Linux 发行版类似）
- 目录：`/opt/personal-supertool`
- Web：建议用 `gunicorn + nginx`（不要用 Flask 自带 dev server）
- 进程：建议用 `systemd` 托管
- 密钥：全部放在服务器的 `.env` 文件中，切勿写进仓库/文档

两种部署方式：
- 方式 A：`gunicorn + systemd + nginx`（传统方式）
- 方式 B：`Docker Compose`（推荐，一键拉起，便于后续升级）

阿里云 ECS 专用最小化上线清单：
- 见 `docs/ALIYUN_ECS_CHECKLIST.md`

---

## 1. 服务器准备

### 1.1 安装系统依赖
```bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates \
  python3 python3-venv python3-pip \
  nginx
```

如采用 Docker Compose，再安装：
```bash
sudo apt-get install -y docker.io docker-compose-plugin
sudo usermod -aG docker $USER
# 重新登录后生效
```

### 1.2 创建目录与用户（可选）
```bash
sudo mkdir -p /opt/personal-supertool
sudo chown -R $USER:$USER /opt/personal-supertool
```

---

## 2. 拉取代码与安装依赖

```bash
cd /opt
git clone <YOUR_GIT_REPO_URL> personal-supertool
cd /opt/personal-supertool

python3 -m venv .venv
./.venv/bin/pip install -U pip
./.venv/bin/pip install -r requirements.txt
```

说明：
- `requirements.txt` 已包含 `gunicorn`（用于生产 Web）

如果你只走 Docker Compose，可跳过本节中的 venv 安装。

---

## 3. 配置 `.env`

### 3.1 放置环境变量文件
```bash
cd /opt/personal-supertool
cp .env .env.local.bak 2>/dev/null || true
nano .env
```

### 3.2 必须配置（按你实际飞书/模型/即梦填写）
以下仅列“关键字段名”，不要把密钥写进文档：
- 飞书：
  - `FEISHU_APP_ID`
  - `FEISHU_APP_SECRET`
  - `FEISHU_APP_TOKEN`
  - `FEISHU_MAIN_TABLE_ID`
  - `FEISHU_TOPIC_PRESCREEN_TABLE_ID`
- Web：
  - `WEB_PORT=8101`
  - `WEB_HOST=0.0.0.0`（云端必须，允许外网访问；本地开发可用 127.0.0.1）
- 模型（国内）：
  - `MODEL_PROVIDER=qwen`
  - `QWEN_API_KEY`
  - `QWEN_BASE_URLS`（DashScope compatible-mode）
  - `QWEN_MODEL=qwen-plus`（或你选择的模型）
- 即梦生图（如启用）：
  - `IMAGE_GEN_ENABLED=true`
  - `IMAGE_GEN_ASYNC=true`（推荐，主流程只入队）
  - `JIMENG_BASE_URL` / `JIMENG_ACCESS_KEY_ID` / `JIMENG_SECRET_ACCESS_KEY` 等

---

## 4. Docker Compose 一键部署（推荐）

项目已提供：
- `Dockerfile`
- `docker-compose.yml`
- `.dockerignore`

### 4.1 构建镜像
```bash
cd /opt/personal-supertool
docker compose build
```

### 4.2 启动 Web 服务
```bash
docker compose up -d web
docker compose ps
```

访问：
```text
http://<你的云服务器公网IP>:8101/?tab=overview
```

### 4.3 启动生图 worker（可选）
```bash
docker compose --profile worker up -d image-worker
```

### 4.4 单次执行主流程（可选）
```bash
docker compose --profile run-once run --rm deconstruct-runner
```

### 4.5 查看日志
```bash
docker compose logs -f web
docker compose logs -f image-worker
```

### 4.6 停止/升级
```bash
docker compose down
git pull
docker compose build
docker compose up -d web
```

持久化说明（已在 compose 挂载）：
- `./logs -> /app/logs`
- `./outputs -> /app/outputs`
- `./data -> /app/data`

---

## 5. 启动 Web（传统方式：gunicorn + systemd）

### 4.1 直接手动验证（先跑通再上 systemd）
```bash
cd /opt/personal-supertool
export PYTHONDONTWRITEBYTECODE=1
source .env

./.venv/bin/gunicorn -w 2 -b 0.0.0.0:${WEB_PORT:-8101} scripts.web_app:app
```

访问：
```text
http://<你的云服务器公网IP>:8101/?tab=overview
```

### 4.2 systemd 服务（常驻）
创建 unit：
```bash
sudo tee /etc/systemd/system/personal-supertool-web.service >/dev/null <<'EOF'
[Unit]
Description=personal-supertool web (gunicorn)
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/personal-supertool
Environment=PYTHONDONTWRITEBYTECODE=1
EnvironmentFile=/opt/personal-supertool/.env
ExecStart=/opt/personal-supertool/.venv/bin/gunicorn -w 2 -b 0.0.0.0:${WEB_PORT} scripts.web_app:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
```

启动：
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now personal-supertool-web
sudo systemctl status personal-supertool-web --no-pager
```

日志：
```bash
journalctl -u personal-supertool-web -n 200 --no-pager
```

---

## 6. Nginx 反向代理（建议）

目标：
- 外网只开放 80/443
- 内网转发到 `127.0.0.1:8101`

示例（HTTP，建议你后续加 HTTPS）：
```bash
sudo tee /etc/nginx/sites-available/personal-supertool >/dev/null <<'EOF'
server {
  listen 80;
  server_name _;

  location / {
    proxy_pass http://127.0.0.1:8101;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}
EOF

sudo ln -sf /etc/nginx/sites-available/personal-supertool /etc/nginx/sites-enabled/personal-supertool
sudo nginx -t
sudo systemctl reload nginx
```

---

## 7. 主流程/worker（按需运行）

### 6.1 主流程（手动或定时任务）
```bash
cd /opt/personal-supertool
export PYTHONDONTWRITEBYTECODE=1
source .env
./.venv/bin/python scripts/deconstruct_daily.py
```

### 6.2 生图 worker（异步回填，建议常驻）
```bash
cd /opt/personal-supertool
export PYTHONDONTWRITEBYTECODE=1
source .env
./.venv/bin/python scripts/jimeng_worker.py jobs
```

可选：将 worker 也做成 systemd（常驻消费队列）。

---

## 8. 数据与持久化

建议把以下目录视为“需要持久化备份”的数据：
- `logs/`：运行记录、队列、回填结果
- `outputs/`：生成的 md/报告等
- `.env`：配置（注意保密）

若你后续做容器化（Docker），需要把上述目录挂载为 volume。

---

## 9. 常见故障排查（云端）

- Web 能启动但外网打不开：
  - 确认 `WEB_HOST=0.0.0.0`
  - 云安全组放行 80/443（或临时放行 8101）
  - 本机防火墙（如 ufw）放行端口
- Docker 容器启动失败：
  - `docker compose logs web` 查看详细报错
  - 确认 `.env` 中必须字段已配置（飞书/模型）
  - 确认端口不冲突（`8101` 未被占用）
- 飞书写入失败：
  - 优先看 `logs/*errors*.jsonl` 与 `journalctl -u personal-supertool-web`
  - 检查飞书字段类型（Number/Select）是否匹配
- 生图慢/失败：
  - 优先开启 `IMAGE_GEN_ASYNC=true`
  - 风控时建议降低并发、加 sleep、提示词英文化并避免文字水印
