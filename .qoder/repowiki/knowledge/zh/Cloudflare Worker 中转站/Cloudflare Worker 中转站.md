---
kind: external_dependency
name: Cloudflare Worker 中转站
slug: cloudflare-worker-relay
category: external_dependency
category_hints:
    - vendor_identity
    - migration_status
scope:
    - '**'
---

### Cloudflare Worker 中继
- **角色**：DeepSeek 和 ASR 服务的统一中转站，提供鉴权和路由功能
- **主域名**：`https://advx.fzxufuyu.eu.org`，备用域名：`https://deepseek-relay.budiansnl.workers.dev`
- **部署**：Cloudflare Worker，版本 `7f0772cc`
- **功能**：Chat 对话、ASR 语音识别、模型查询等端点
- **鉴权**：任意非空串作为 API Key（中继不严格校验）
- **迁移状态**：从原始域名迁移到 IP 直连部署，支持多域名切换
- **WAF 兼容**：需要正确设置 User-Agent 避免 Bot Fight Mode 拦截