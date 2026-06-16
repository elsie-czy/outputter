# 阿里云 ECS 最小化上线清单（v1.0）

适用范围：
- 项目：`personal-supertool`
- 部署方式：优先 `Docker Compose`（可选 Nginx 反代）
- 目标：快速、安全、可回滚地上线一个可用版本

---

## 1. 资源准备

- ECS：`2C4G` 起步（轻负载可 `2C2G`）
- 系统盘：`>= 40GB`
- 数据盘（可选）：用于 `logs/outputs`
- 固定公网 IP：建议开通
- 域名：建议准备（如 `tool.example.com`）

---

## 2. 安全组与网络

最小放行规则（入方向）：
- `22/tcp`：仅你的办公 IP（不要对全网开放）
- `80/tcp`：全网（HTTP 验证/跳转）
- `443/tcp`：全网（HTTPS）
- `8101/tcp`：默认不要开放（仅内网或临时调试）

出方向：
- 默认放行（项目需要访问飞书/模型/即梦 API）

---

## 3. 服务器基线加固

```bash
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y git curl ca-certificates nginx \
  docker.io docker-compose-plugin
sudo timedatectl set-timezone Asia/Shanghai
sudo usermod -aG docker $USER
```

建议：
- 新建普通用户部署，不用 root 直接跑服务
- 启用 `ufw`（可选）并仅放行 22/80/443

---

## 4. 项目部署（Compose）

```bash
cd /opt
git clone <YOUR_GIT_REPO_URL> personal-supertool
cd /opt/personal-supertool

# 配置 .env（填真实密钥）
nano .env

docker compose build
docker compose up -d web
docker compose ps
```

可选：
```bash
# 启动异步生图 worker
docker compose --profile worker up -d image-worker
```

---

## 5. Nginx 反代（80/443）

目标：
- 对外只暴露 Nginx
- 应用容器走本机 `127.0.0.1:8101`

示例配置：
```nginx
server {
  listen 80;
  server_name tool.example.com;

  location / {
    proxy_pass http://127.0.0.1:8101;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}
```

---

## 6. HTTPS（Let’s Encrypt）

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d tool.example.com
```

验证自动续期：
```bash
sudo certbot renew --dry-run
```

---

## 7. 上线前验收

- Web 可访问：
  - `https://tool.example.com/?tab=overview`
  - `https://tool.example.com/?tab=prescreen`
- 飞书联通：
  - 能正常读取/写入目标表
- 初筛抓取：
  - 能发起任务，右侧状态有 `queued/running/done`
- 日志正常：
  - `docker compose logs -f web`
  - `docker compose logs -f image-worker`（如启用）

---

## 8. 备份与回滚

必须备份：
- `.env`
- `logs/`
- `outputs/`
- `data/`

建议策略：
- 每日凌晨备份到 OSS 或另一台机器（至少保留 7 天）
- 每次升级前打 git tag

快速回滚（代码）：
```bash
cd /opt/personal-supertool
git checkout <LAST_GOOD_TAG_OR_COMMIT>
docker compose build
docker compose up -d web
```

---

## 9. 日常运维检查（5 分钟）

每天检查：
- `docker compose ps`：容器是否 `Up`
- `docker compose logs --since=24h web | rg -n "ERROR|Traceback"`
- 磁盘：`df -h`（防止 `logs/outputs` 占满）
- 证书：`sudo certbot certificates`

每周检查：
- `.env` 是否有变更、是否需要轮换密钥
- 飞书字段结构是否变更（有变更需同步脚本映射）

---

## 10. 常见故障速查

- 页面 502/504：
  - 看 Nginx `error.log`
  - 看 `docker compose logs web`
- 页面 500：
  - 优先看 `web` 容器日志堆栈
- 抓取任务无响应：
  - 检查 `logs/prescreen_web_jobs.jsonl` 是否写入
- 写飞书失败：
  - 检查 `.env` 飞书配置与字段类型匹配
- 外网无法访问：
  - 检查安全组、Nginx、域名解析是否指向正确 ECS IP

