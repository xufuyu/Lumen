---
kind: build_system
name: 构建与部署系统 — Vite + FastAPI + GitHub Actions + systemd/nginx
category: build_system
scope:
    - '**'
source_files:
    - .github/workflows/deploy.yml
    - deploy.sh
    - frontend/package.json
    - frontend/vite.config.ts
    - backend/requirements.txt
---

本项目采用“前端静态构建 + 后端 Python 包”的简单直出模式，通过一个统一的 `deploy.sh` 脚本和 `.github/workflows/deploy.yml` CI 流水线完成从源码到生产服务器的完整发布流程。核心思路是：在本地或 CI 中分别构建前端（Vite）和打包后端（Python），生成 `deploy/` 目录，再通过 SSH + rsync 推送到目标服务器，由远端脚本安装依赖、生成 systemd 单元、配置 nginx 反向代理并启动服务。

**1. 使用的工具与框架**
- 前端：Vue 3 + TypeScript + Vite 8，使用 `vue-tsc -b && vite build` 进行类型检查与产物构建，输出至 `frontend/dist`；CI 与本地脚本将产物复制到 `deploy/static`。
- 后端：FastAPI + Uvicorn，依赖通过 `requirements.txt` 管理，运行于 Python venv 中。
- 部署：GitHub Actions（Ubuntu runner）+ SSH 密钥认证 + rsync 增量同步；生产环境使用 systemd 管理进程、nginx 作为反向代理与静态资源服务器。
- 本地手动部署：`deploy.sh` 复用 CI 逻辑，支持通过环境变量注入 CA 证书、替换中继域名等。

**2. 关键文件与位置**
- `.github/workflows/deploy.yml`：完整的 CI 部署流水线，包含 Secret 校验、前端构建、后端打包、域名替换、CA 证书注入、.env 生成、SSH/rsync 上传、远端安装与重启、健康检查等步骤。
- `deploy.sh`：本地一键部署脚本，参数化 `DEPLOY_HOST`、`DEPLOY_USER`、`RELAY_CA_PEM_FILE` 等，逻辑与 CI 保持一致。
- `frontend/package.json`：定义 `dev`、`build`、`preview` 三个 npm script，构建命令为 `vue-tsc -b && vite build`。
- `frontend/vite.config.ts`：开发时代理 `/api` 到 `http://localhost:8000`，启用 WebSocket 转发。
- `backend/requirements.txt`：声明 FastAPI、Uvicorn、SQLAlchemy、Pydantic、httpx、python-dotenv、aiosqlite、websockets 等依赖。
- `deploy/backend/` 与 `deploy/static/`：CI 与本地脚本生成的部署产物目录。

**3. 架构与约定**
- **构建产物分离**：前端静态资源输出到 `deploy/static`，后端代码复制后清理 `__pycache__`、`.pyc` 与 `.env`，避免泄露敏感信息。
- **域名/主机名替换**：通过 `grep -rl` 搜索 `advx.fzxufuyu.eu.org` 并在所有文件中替换为 `RELAY_HOST`，确保部署目标可动态切换。
- **证书与配置注入**：CA 证书从 GitHub Secrets 或环境变量注入到 `deploy/backend/certs/relay-ca.pem`；`.env` 由脚本动态生成，包含 RELAY_BASE_URL、DATABASE_URL、MODEL_PRO/FLASH 等运行时变量。
- **幂等部署**：远端脚本先检查 `/opt/lumen` 是否存在，首次才安装系统依赖、创建用户与目录；venv 仅在不存在时创建，之后仅升级 pip 与依赖。
- **服务管理**：systemd 单元固定以 `lumen` 用户运行，WorkingDirectory 指向 `/opt/lumen/backend`，EnvironmentFile 指向 `/opt/lumen/.env`，只允许读写 `/opt/lumen/data`。
- **反向代理**：nginx 同时处理 HTTP→HTTPS 跳转（有证书时）、静态资源缓存、API 代理、WebSocket 升级（`/api/asr/ws` 与 `/api/ws/` 长连接超时设为 3600s）以及 SPA 回退到 `index.html`。

**4. 约定与约束**
- 构建必须在 Node 22 环境下执行（CI 中 `setup-node@v4` 指定 `node-version: '22'`）。
- 依赖安装使用 `npm ci --prefer-offline --no-audit --no-fund`，禁止网络审计与基金提示，保证 CI 稳定。
- 后端依赖安装设置 `PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1` 环境变量，兼容 PyO3 ABI3。
- 部署前必须提供 `RELAY_HOST`、`DEPLOY_HOST`、`DEPLOY_USER`、`DEPLOY_SSH_KEY`、`RELAY_CA_PEM` 五个 Secret，否则 CI 直接失败。
- 生产环境数据库路径固定为 `/opt/lumen/data/adventurex.db`，通过 SQLite + aiosqlite 异步访问。
- 健康检查通过 `curl -sf http://127.0.0.1:8000/api/health` 验证后端存活，nginx 有证书时使用 `-sfk` 跳过证书校验。
- 部署完成后自动清理 `/tmp/lumen-deploy` 与本地 `deploy/` 目录，避免残留敏感文件。