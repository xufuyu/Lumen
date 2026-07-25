---
kind: dependency_management
name: 依赖管理 — Python requirements.txt + npm lockfile
category: dependency_management
scope:
    - '**'
source_files:
    - backend/requirements.txt
    - frontend/package.json
    - frontend/package-lock.json
    - .github/workflows/deploy.yml
---

本仓库采用前后端分离的依赖管理模式：后端使用 Python 的 `requirements.txt` 声明依赖，前端使用 npm 的 `package.json` + `package-lock.json` 锁定版本，CI/CD 通过 GitHub Actions 在部署时安装依赖。

**1. 系统/工具**
- 后端：pip + `requirements.txt`，无虚拟环境文件（`.venv`）提交到仓库，但 CI 中会创建并使用 `.venv/bin/pip`。
- 前端：npm（lockfileVersion 3），使用 `package-lock.json` 锁定完整依赖树。
- CI：GitHub Actions（`.github/workflows/deploy.yml`）负责构建与依赖安装。

**2. 关键文件**
- `backend/requirements.txt`：后端 Python 依赖清单（FastAPI、Uvicorn、SQLAlchemy、Pydantic、httpx、python-dotenv、aiosqlite、websockets）。
- `frontend/package.json`：前端依赖声明（Vue 3、vue-i18n、Vite、TypeScript、Tailwind 等）。
- `frontend/package-lock.json`：前端依赖锁定文件（包含所有子依赖的精确版本与 integrity hash）。
- `.github/workflows/deploy.yml`：CI 中执行 `npm ci --prefer-offline --no-audit --no-fund` 和 `pip install -r backend/requirements.txt`。

**3. 架构与约定**
- 后端依赖以 `>=` 指定最低版本（如 `fastapi>=0.115.0`），未使用 `pip freeze` 生成锁文件，也未使用 Poetry/Pipenv。
- 前端依赖使用 `^` 和 `~` 语义化版本控制，并通过 `package-lock.json` 保证可重复构建。
- 根目录存在一个空的 `package-lock.json`（lockfileVersion 3，packages 为空），可能是早期初始化遗留，实际生效的是 `frontend/package-lock.json`。
- 未使用私有 PyPI 源或 npm registry 镜像配置，依赖均从官方源下载。

**4. 约定与约束**
- 后端依赖更新需修改 `requirements.txt`，当前未使用固定版本号，可能存在构建不一致风险。
- 前端依赖通过 `npm ci` 安装，确保与 `package-lock.json` 严格一致。
- CI 中禁用审计与 fund 提示（`--no-audit --no-fund`），加速流水线。
- 未发现 vendoring、私有仓库代理或依赖扫描策略。