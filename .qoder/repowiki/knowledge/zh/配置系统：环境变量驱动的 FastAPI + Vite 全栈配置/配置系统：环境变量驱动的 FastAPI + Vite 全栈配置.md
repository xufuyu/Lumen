---
kind: configuration_system
name: 配置系统：环境变量驱动的 FastAPI + Vite 全栈配置
category: configuration_system
scope:
    - '**'
source_files:
    - backend/config.py
    - backend/main.py
    - backend/database.py
    - frontend/vite.config.ts
    - deploy.sh
---

本项目的配置系统以**环境变量为核心**，后端通过 Python `os.getenv` 集中加载，前端通过 Vite 构建时代理与部署脚本注入，形成“开发-构建-部署”三层配置流。

### 1. 后端配置（FastAPI）
- **统一入口**：`backend/config.py` 集中定义所有运行时配置项，包括数据库连接、LLM 中继地址、ASR WebSocket 地址、TLS 策略、模型选择、温度参数、自动处理开关等。
- **加载方式**：全部使用 `os.getenv("KEY", default)` 从环境变量读取，未设置时使用合理默认值（如 SQLite 路径、relay 地址、api_key 等）。
- **TLS 策略**：提供 `httpx_verify()` 和 `relay_ssl_context()` 两个辅助函数，按优先级 `INSECURE > CA_BUNDLE > 系统 CA` 决定 httpx 和 websockets 的 TLS 验证行为，支持自签证书、IP 直连跳过校验等场景。
- **CORS 配置**：在 `main.py` 中通过 `CORS_ORIGINS` 环境变量动态设置允许来源，默认 `*`。
- **启动初始化**：`lifespan` 钩子在应用启动时确保 `data/` 目录存在并调用 `init_db()` 创建表结构。

### 2. 前端配置（Vite + Vue）
- **开发代理**：`vite.config.ts` 硬编码将 `/api` 请求代理到 `http://localhost:8000`，无需额外环境变量。
- **构建产物**：前端静态资源通过 `npm run build` 输出到 `dist/`，由部署脚本复制到 `deploy/static/`。
- **类型声明**：`src/env.d.ts` 仅包含 Vue 模块类型声明，无运行时环境变量引用。

### 3. 部署与注入（deploy.sh）
- **构建阶段**：先构建前端，再复制后端代码并清理 `__pycache__` 和 `.env`。
- **域名替换**：使用 `sed` 将硬编码的 `advx.fzxufuyu.eu.org` 替换为 `RELAY_HOST` 环境变量指定的目标主机。
- **CA 证书注入**：将本地 `RELAY_CA_PEM_FILE` 指向的 PEM 文件复制到 `deploy/backend/certs/relay-ca.pem`。
- **.env 生成**：动态生成 `lumen.env`，包含所有必需的环境变量（RELAY_BASE_URL、RELAY_API_KEY、DATABASE_URL 等），权限设为 `600`。
- **Systemd 服务**：远端通过 `EnvironmentFile=/opt/lumen/.env` 加载环境变量，以 `lumen` 用户运行，限制只读 `/opt/lumen/data`。

### 4. 约定与约束
- **所有后端配置必须通过环境变量注入**，禁止在代码中硬编码敏感信息。
- **TLS 安全优先**：默认使用系统 CA 验证，仅在明确设置 `RELAY_TLS_INSECURE=true` 时才跳过校验。
- **数据库路径**：默认位于 `backend/../data/adventurex.db`，可通过 `DATABASE_URL` 覆盖。
- **CORS 默认开放**：未设置 `CORS_ORIGINS` 时允许所有来源，生产环境应显式指定。
- **用户标识**：通过 `X-User-ID` 和 `X-User-Language` 请求头传递，后端有默认回退值（`default` 和 `zh-CN`）。