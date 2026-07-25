---
kind: error_handling
name: FastAPI 后端错误处理体系：中间件限流 + HTTPException + WebSocket 异常透传
category: error_handling
scope:
    - '**'
source_files:
    - backend/main.py
    - backend/security.py
    - backend/database.py
    - backend/routers/asr.py
    - backend/routers/query.py
    - backend/routers/records.py
    - backend/routers/tasks.py
    - backend/routers/timeline.py
    - backend/routers/merge.py
    - backend/routers/export.py
---

## 1. 系统/框架
- 后端基于 **FastAPI**，统一通过 `fastapi.HTTPException` 抛出业务错误，由 FastAPI 自动序列化为 JSON 响应。
- 安全与限流通过自定义 **Starlette `BaseHTTPMiddleware`**（`SecurityMiddleware`）实现，在请求进入路由前拦截并返回 429。
- WebSocket 端点（ASR 实时语音识别）使用 `websockets` 库，异常通过 try/except 捕获后向前端发送 `{type: "error", message: ...}` 消息。
- 数据库层使用 SQLAlchemy async engine，迁移脚本对 `ALTER TABLE` 失败以 `except Exception: pass` 吞掉重复列错误。

## 2. 关键文件与位置
- `backend/main.py` — FastAPI 应用入口，注册 CORS、SecurityMiddleware 与各 router。
- `backend/security.py` — 速率限制中间件、SQL 注入白名单校验、用户 ID 格式校验，集中抛出 `HTTPException(400/429)`。
- `backend/database.py` — 异步 Session 管理、表初始化与迁移，`get_db()` 依赖提供 session 上下文。
- `backend/routers/*.py` — 各业务路由统一通过 `raise HTTPException(status_code, detail=...)` 返回错误；`routers/asr.py` 是 WS 错误处理的核心。
- `backend/config.py` — 配置项加载，包含 TLS/CA 策略，间接影响连接类异常。

## 3. 架构与约定
- **REST API 错误**：所有路由函数遇到参数非法、资源不存在、业务校验失败等场景，直接 `raise HTTPException(status_code, detail=...)`。常见状态码：
  - `400`：参数校验失败（如 query 为空、merge action 未知）。
  - `404`：记录/任务/事件不存在。
  - `500`：内部处理异常（如 query 处理失败）。
  - `429`：由 SecurityMiddleware 的速率限制触发，返回带 `retry_after` 和 `demo` 标志的 JSON。
- **WebSocket 错误**：`asr.py` 中上游 ASR 服务返回的 `error` 事件会被映射为用户友好提示并通过 `{"type":"error","message":...}` 下发；连接断开、超时、网络异常等均通过 try/except 捕获后记录日志并尝试通知前端，最后在 `finally` 中确保关闭 relay_ws、cancel task、close frontend。
- **输入校验与安全**：`security.sanitize_user_id` 对 X-User-ID 做正则校验，不合法直接抛 400；`validate_table_name` 用白名单防止 SQL 注入；路径归一化用于按资源类型限速。
- **国际化错误消息**：通过 `database.pick(lang, zh, en)` 根据 `X-User-Language` 头选择中文或英文错误描述，保持前后端 i18n 一致。
- **无全局异常处理器**：代码中未定义 `@app.exception_handler`，全部依赖 FastAPI 默认的 HTTPException 处理逻辑。

## 4. 约定与约束
- **REST 路由**：必须使用 `raise HTTPException(...)` 表达错误，禁止返回裸字符串或 None 作为错误信号。
- **WS 路由**：所有外部 I/O（`frontend.send_json`、`relay_ws.send/close`）必须包裹 try/except，确保即使发送失败也不中断主流程；最终一律在 finally 中清理资源。
- **速率限制**：AI 调用、写操作、读操作分别有独立阈值，超过阈值返回 429 并附带 `Retry-After` 头部；演示版本强制返回 `demo: True` 标识。
- **数据库迁移**：`init_db` 中对已存在列的 `ALTER TABLE` 使用 `except Exception: pass` 容忍重复执行，保证幂等。
- **日志**：所有异常路径均通过 `logger.error/warning/info` 记录，便于排查；WS 错误同时向前端推送可理解的消息。
- **TLS/SSL**：通过 `config.relay_ssl_context()` 控制 websockets 连接验证策略（INSECURE > CA_BUNDLE > 系统 CA），避免自签证书导致连接异常。

## 5. 缺失与局限
- 没有统一的错误码枚举或自定义异常基类，错误语义分散在各路由中。
- 未定义全局 `exception_handler` 来统一格式化错误响应体结构（如增加 code/message 字段）。
- 部分 `except Exception: pass` 过于宽泛（如 database 迁移、WS 发送失败），可能掩盖真实问题。