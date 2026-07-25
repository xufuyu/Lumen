---
kind: external_dependency
name: DeepSeek V4 Flash 对话模型
slug: deepseek-v4-flash
category: external_dependency
category_hints:
    - vendor_identity
    - client_constraint
scope:
    - '**'
---

### DeepSeek V4 Flash
- **角色**：项目使用的 LLM 对话模型，通过自建 Cloudflare Worker 中继转发
- **集成方式**：后端使用 httpx 直接 HTTP POST 调用 `/v1/chat/completions`，不使用 OpenAI SDK（避免 x-stainless-* 头被 WAF 拦截）
- **约束**：模型锁定为 `deepseek-v4-flash`，max_tokens ≤ 3000，思考模式强制关闭
- **鉴权**：通过 RELAY_API_KEY 环境变量注入 Authorization 头
- **部署**：Cloudflare Worker 部署，支持 HTTPS + HSTS
- **注意**：需要配置正确的 TLS 证书验证策略（RELAY_CA_BUNDLE 或 RELAY_TLS_INSECURE）