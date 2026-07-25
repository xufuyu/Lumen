---
kind: logging_system
name: 后端日志系统 — Python 标准 logging 模块
category: logging_system
scope:
    - '**'
source_files:
    - backend/main.py
    - backend/database.py
    - backend/services/processor.py
    - backend/routers/process.py
---

该项目的日志系统基于 Python 标准库 `logging` 模块，采用统一的模块级 logger 模式，未引入第三方日志框架（如 loguru、structlog 等）。

**系统与初始化**
- 在 `backend/main.py` 中通过 `logging.basicConfig(level=logging.INFO)` 全局配置根日志器，设置默认级别为 INFO。
- 每个模块通过 `logger = logging.getLogger(__name__)` 获取与模块名同名的子 logger，遵循 Python logging 的命名空间约定。
- 未配置自定义 Formatter、Handler 或 RotatingFileHandler，所有输出默认写入标准错误流（stderr），由运行环境（uvicorn）接管。

**使用模式与约定**
- 各模块（routers、services、database）均按相同模式声明 logger：`import logging` + `logger = logging.getLogger(__name__)`。
- 日志级别使用：`logger.info()` 记录正常流程信息（如数据库迁移、处理计数），`logger.warning()` 记录可恢复异常（如 LLM 指定任务 ID 不存在），`logger.exception()` 捕获并记录完整堆栈（用于 try/except 中的异常分支）。
- 结构化字段通过字符串格式化嵌入消息体，例如 `[processor] LLM 指定更新任务 #{id}: {title!r} → {status}`，而非 JSON 结构化日志。
- 未实现请求级别的 trace_id、用户标识自动注入，但可通过依赖注入的 `uid`、`lang` 参数手动拼入日志消息。

**架构决策**
- 日志配置集中放在应用入口 `main.py`，其他模块仅消费 logger，不重复配置 basicConfig。
- 未实现日志分级输出（如 debug/info/warning/error 分离到不同文件），也未集成外部日志收集服务（ELK、CloudWatch 等）。
- 前端（Vue 3）未使用专用日志库，调试主要依赖浏览器控制台，无统一的前端日志采集方案。

**约束与限制**
- 日志级别固定为 INFO，无法通过环境变量动态调整。
- 无日志轮转机制，长时间运行的生产环境可能产生大体积 stderr 输出。
- 未对敏感字段（如用户数据、LLM 输入输出）做脱敏处理。